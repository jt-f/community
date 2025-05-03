"""Main module for the autonomous agent."""
import argparse
import asyncio
import logging
import json
import signal
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from dotenv import load_dotenv

import agent_config
from command_handler import CommandHandler
from decorators import log_exceptions
from llm_client import LLMClient
from message_queue_handler import MessageQueueHandler
from messaging import process_message
from server_manager import ServerManager
from shared_models import setup_logging
from state import AgentState

# Load environment variables from .env file
load_dotenv()

# Initialize logger early
setup_logging()
logger = logging.getLogger(__name__)


class Agent:
    """Represents an autonomous agent interacting with the system."""

    def __init__(self, agent_name: Optional[str] = None):
        """Initialize the agent with configuration, state, and handlers."""
        logger.info("Initializing agent...")

        self.agent_id, self.agent_name = agent_config.create_agent_metadata(agent_name)
        self.loop = asyncio.get_event_loop()
        self.state = AgentState(self.agent_id, self.agent_name)
        self.llm_client = LLMClient(state_updater=self.state)
        # Pass the async message handler wrapper to MQHandler
        self.mq_handler = MessageQueueHandler(
            state_updater=self.state,
            message_handler=self.handle_message_wrapper, # Pass the async wrapper
            loop=self.loop
        )
        self.command_handler = CommandHandler(self)
        # Pass the async command handler wrapper to ServerManager
        self.server_manager = ServerManager(
            state_updater=self.state,
            command_callback=self.handle_server_command_wrapper # Pass the async wrapper
        )
        self._last_status_update_time = datetime.now()
        self._shutdown_requested = False

        logger.info(f"Agent '{self.agent_name}' (ID: {self.agent_id}) initialized successfully.")

    @log_exceptions
    async def handle_message_wrapper(self, body: bytes):
        """Asynchronous wrapper to process messages received from the queue."""
        logger.debug(f"Received raw message body (first 100 bytes): {body[:100]}...")
        try:
            message_dict = json.loads(body.decode('utf-8'))
            logger.info(f"Processing message ID: {message_dict.get('message_id', 'N/A')}")
            # Call the actual processing function (which might involve LLM)
            await process_message(
                llm_client=self.llm_client,
                mq_channel=self.mq_handler.channel, # Provide the channel for publishing response
                agent_id=self.agent_id,
                message=message_dict
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message JSON: {e}", exc_info=True)
            # Consider how to handle undecodable messages (e.g., log, discard, move to dead-letter queue)
        except Exception as e:
            logger.error(f"Error in handle_message_wrapper: {e}", exc_info=True)
            # Handle potential errors during message processing

    @log_exceptions
    async def handle_server_command_wrapper(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Asynchronous wrapper to handle commands received from the server."""
        logger.info(f"Handling server command: {command}")
        try:
            # Delegate command handling to the synchronous CommandHandler method
            # Run synchronous code in a separate thread to avoid blocking the event loop
            result = await self.loop.run_in_executor(
                None, # Use default executor (ThreadPoolExecutor)
                self.command_handler.handle_server_command,
                command
            )
            logger.info(f"Command handling result: {result}")
            return result
        except Exception as e:
            logger.error(f"Error in handle_server_command_wrapper: {e}", exc_info=True)
            return {
                "success": False,
                "output": "Internal error handling command",
                "error_message": str(e),
                "exit_code": 1
            }

    def setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        logger.info("Setting up signal handlers...")
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            self.loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(self.shutdown(signal=s))
            )
        logger.info("Signal handlers set up.")

    @log_exceptions
    async def run(self):
        """Main execution loop for the agent."""
        logger.info(f"Agent '{self.agent_name}' starting run loop.")
        self.state.set_internal_state('starting')

        self.setup_signal_handlers()

        # 1. Connect to RabbitMQ
        logger.info("Connecting to Message Queue...")
        if not self.mq_handler.connect(queue_name=self.agent_id):
            logger.critical("Failed to connect to Message Queue. Agent cannot operate.")
            self.state.set_internal_state('error')
            await self.cleanup_async() # Attempt cleanup
            return # Exit if MQ connection fails
        logger.info("Message Queue connection successful.")

        # 2. Connect to gRPC Server and Register
        logger.info("Connecting to gRPC Server and registering...")
        registered = await self.server_manager.register(self.agent_id, self.agent_name)
        if not registered:
            logger.critical("Failed to register with the server. Agent will exit.")
            self.state.set_internal_state('error')
            await self.cleanup_async() # Attempt cleanup
            return # Exit if registration fails
        logger.info("Agent registered successfully with the server.")
        self.state.set_registration_status("registered")
        self.state.set_internal_state('idle') # Move to idle after successful setup

        # 3. Start background tasks (status updates, command stream)
        await self.server_manager.start_status_updater() # Renamed for clarity
        await self.server_manager.start_command_stream() # Start listening for commands

        # 4. Main agent loop
        logger.info("Entering main agent loop.")
        while not self._shutdown_requested:
            try:
                # Main loop logic (can be expanded later)
                # For now, it primarily relies on background tasks (MQ consumer, gRPC streams)
                # We can add periodic checks or tasks here if needed.

                # Example: Check agent health or perform periodic tasks
                # if datetime.now() - self._last_status_update_time > timedelta(minutes=5):
                #     logger.info("Performing periodic health check...")
                #     # Perform checks
                #     self._last_status_update_time = datetime.now()

                # Update internal state based on component health
                self.state.update_internal_state_based_on_components()

                await asyncio.sleep(agent_config.AGENT_MAIN_LOOP_SLEEP)

            except asyncio.CancelledError:
                logger.info("Main loop cancelled, likely during shutdown.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main agent loop: {e}", exc_info=True)
                self.state.set_internal_state('error')
                self.state.set_last_error(f"Main loop error: {e}")
                # Consider if agent should attempt recovery or shut down on main loop errors
                await asyncio.sleep(agent_config.AGENT_MAIN_LOOP_SLEEP * 2) # Longer sleep after error

        logger.info(f"Agent '{self.agent_name}' main loop finished.")
        # Final cleanup is handled after the loop exits
        await self.cleanup_async()

    @log_exceptions
    async def shutdown(self, signal: Optional[signal.Signals] = None):
        """Initiate graceful shutdown of the agent."""
        if self._shutdown_requested:
            logger.info("Shutdown already in progress.")
            return

        self._shutdown_requested = True
        self.state.set_internal_state('shutting_down')
        if signal:
            logger.info(f"Shutdown initiated by signal {signal.name}...")
        else:
            logger.info("Shutdown initiated...")

        # The actual cleanup logic will run after the main loop exits
        # We just set the flag here to break the loop

        # Optionally, cancel long-running tasks here if they don't check _shutdown_requested
        # e.g., if server_manager tasks need explicit cancellation:
        # await self.server_manager.stop_tasks()

        logger.info("Shutdown flag set. Main loop will exit and perform cleanup.")

    @log_exceptions
    async def cleanup_async(self):
        """Perform asynchronous cleanup of resources."""
        logger.info("Starting asynchronous cleanup...")
        self.state.set_internal_state('shutting_down') # Ensure state reflects shutdown

        # 1. Stop server interactions (status updates, command stream, unregister)
        if self.server_manager:
            logger.info("Cleaning up Server Manager...")
            await self.server_manager.cleanup(self.agent_id)
            logger.info("Server Manager cleanup complete.")

        # 2. Disconnect from Message Queue
        if self.mq_handler:
            logger.info("Cleaning up Message Queue Handler...")
            # disconnect() is synchronous but manages a thread, call directly
            self.mq_handler.disconnect()
            logger.info("Message Queue Handler cleanup complete.")

        # 3. Cleanup LLM Client (if needed)
        if self.llm_client:
            logger.info("Cleaning up LLM Client...")
            self.llm_client.cleanup()
            logger.info("LLM Client cleanup complete.")

        # 4. Cancel remaining asyncio tasks (important for clean exit)
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} outstanding asyncio tasks...")
            for task in tasks:
                task.cancel()
            # Wait for tasks to cancel
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Outstanding asyncio tasks cancelled.")

        logger.info("Asynchronous cleanup finished.")
        self.state.set_internal_state('shutdown') # Final state


async def main():
    """Main entry point for running the agent."""
    parser = argparse.ArgumentParser(description="Run an autonomous agent.")
    parser.add_argument("--name", type=str, help="Assign a specific name to the agent.")
    args = parser.parse_args()

    agent = None
    try:
        agent = Agent(agent_name=args.name)
        await agent.run()
    except Exception as e:
        logger.critical(f"Critical error during agent execution: {e}", exc_info=True)
        # Attempt cleanup even if initialization or run fails partially
        if agent:
            logger.info("Attempting emergency cleanup...")
            await agent.cleanup_async()
        sys.exit(1) # Exit with error code
    finally:
        logger.info("Agent process finished.")

if __name__ == "__main__":
    asyncio.run(main())
