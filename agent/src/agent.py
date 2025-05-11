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
        self.llm_client = LLMClient(state_manager=self.state)
        # Pass the async message handler wrapper to MQHandler
        self.mq_handler = MessageQueueHandler(
            state_manager=self.state,
            message_handler=self.handle_message_wrapper, # Pass the async wrapper
            loop=self.loop
        )
        self.command_handler = CommandHandler(self)
        # Pass the async command handler wrapper to ServerManager
        self.server_manager = ServerManager(
            state_manager=self.state,
            command_callback=self.handle_server_command_wrapper # Pass the async wrapper
        )
        self._last_status_update_time = datetime.now()
        self._shutdown_requested = False

        logger.info(f"Agent '{self.agent_name}' (ID: {self.agent_id}) initialized successfully.")

    @log_exceptions
    async def handle_message_wrapper(self, body: bytes):
        """Asynchronous wrapper to process messages received from the queue."""
        # Update state to busy
        await self.state.set_internal_state('busy')

        # Only log on message received
        logger.info("Message received from queue.")
        try:
            message_dict = json.loads(body.decode('utf-8'))
            # Call the actual processing function (which might involve LLM)
            await process_message(
                llm_client=self.llm_client,
                mq_channel=self.mq_handler.channel, # Provide the channel for publishing response
                agent_id=self.agent_id,
                message=message_dict
            )
            # Only log on message sent
            logger.info("Message sent to broker.")
            await self.state.set_internal_state('idle')

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
            # Directly await the async CommandHandler method for full async flow
            result = await self.command_handler.handle_server_command(command)
            logger.info("Status changed after command execution.")
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

        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            self.loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(self.shutdown(signal=s))
            )
        logger.info("Signal handlers added")

    @log_exceptions
    async def run(self):
        """Main execution loop for the agent."""
        logger.info(f"Starting run loop.")
        await self.state.set_internal_state('starting') # Added await
        self.setup_signal_handlers()

        logger.info("Connecting to gRPC Server and registering...")
        registered = await self.server_manager.register(self.agent_id, self.agent_name)
        if not registered:
            logger.critical("Failed to register with the server. Agent will exit.")
            await self.state.set_internal_state('error') # Added await
            await self.cleanup_async() # Attempt cleanup
            return # Exit if registration fails
        logger.info("Agent registered successfully with the server.")

        await self.server_manager.start_command_stream()
        await self.state.set_registration_status("registered") # Added await

        if not self.mq_handler.connect(queue_name=self.agent_id):
            logger.critical("Failed to connect to Message Queue. Agent cannot operate.")
            await self.state.set_internal_state('error') # Added await
            await self.cleanup_async() # Attempt cleanup
            return # Exit if MQ connection fails
        logger.info("Message Queue connection successful.")

        await self.state.set_internal_state('idle') # Added await # Move to idle after successful setup

        # 4. Main agent loop
        logger.info("Entering main agent loop.")
        while not self._shutdown_requested:
            try:

                # Update internal state based on component health
                # self.state.update_internal_state_based_on_components()
                #
                await asyncio.sleep(agent_config.AGENT_MAIN_LOOP_SLEEP)

            except asyncio.CancelledError:
                logger.info("Main loop cancelled, likely during shutdown.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main agent loop: {e}", exc_info=True)
                await self.state.set_internal_state('error') # Added await
                await self.state.set_last_error(f"Main loop error: {e}") # Added await
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
        await self.state.set_internal_state('shutting_down')
        if signal:
            logger.info(f"Shutdown initiated by signal {signal.name}...")
        else:
            logger.info("Shutdown initiated...")

        logger.info("Shutdown flag set. Main loop will exit and perform cleanup.")

    @log_exceptions
    async def cleanup_async(self):
        """Perform asynchronous cleanup of resources."""
        logger.info("Starting asynchronous cleanup...")
        await self.state.set_internal_state('shutting_down') # Ensure state reflects shutdown

        # 1. Stop server interactions (status updates, command stream, unregister)
        if self.server_manager:
            logger.info("Cleaning up Server Manager...")
            await self.server_manager.cleanup(self.agent_id)
            logger.info("Server Manager cleanup complete.")

        # 2. Disconnect from Message Queue
        if self.mq_handler:
            # disconnect() is synchronous but manages a thread, call directly
            logger.info("Cleaning up Message Queue Handler...")
            self.mq_handler.disconnect()
            # Set final state after disconnect completes
            await self.state.set_message_queue_status('disconnected')
            logger.info("Message Queue Handler cleanup complete.")

        # 3. Cleanup LLM Client (if needed)
        if self.llm_client:
            await self.llm_client.cleanup()

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
        await self.state.set_internal_state('shutdown') # Final state


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
