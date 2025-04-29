import asyncio
import os
import signal
import sys
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

# Local imports
import agent_config
import argparse
from command_handler import CommandHandler
from decorators import log_exceptions
from llm_client import LLMClient
from message_queue_handler import MessageQueueHandler
from messaging import process_message_dict
from server_manager import ServerManager
from shared_models import setup_logging
from state import AgentState

logger = setup_logging(__name__)


class Agent:
    """Represents an autonomous agent interacting with the system."""

    def __init__(self, agent_name: Optional[str] = None):
        """Initialize the agent with a unique ID and name."""
        logger.info(f"Initializing...")

        self.agent_id, self.agent_name = agent_config.create_agent_metadata(agent_name)
        self.loop = asyncio.get_event_loop()
        self.state = AgentState(self.agent_id, self.agent_name)
        self.llm_client = LLMClient(state_updater=self.state)
        self.mq_handler = MessageQueueHandler(state_updater=self.state, message_handler=self.handle_message_wrapper, loop=self.loop)
        self.command_handler = CommandHandler(self)
        self.server_manager = ServerManager(state_updater=self.state, command_callback=self.handle_server_command_wrapper)
        self._last_status_update_time = datetime.now()
        self._shutdown_requested = False

        logger.info(f"Initialization complete")

    @log_exceptions
    async def run(self):
        """Main execution loop for the agent."""
        logger.info(f"Agent {self.agent_name} starting run loop.")
        self.setup_signal_handlers()

        # Connect to RabbitMQ
        if not self.mq_handler.connect(queue_name=self.agent_id):
            self.state.set_internal_state('error')
            return

        # Register with the server
        if not await self.server_manager.register(self.agent_id, self.agent_name):
            logger.error("Failed to register with the server. Agent may have limited functionality.")
            return

        # Start the command stream listener (if registration was successful)
        # Note: server_manager.register now starts the stream internally on success
        try:
            while not self._shutdown_requested:
                # Main agent logic loop

                await self.send_status_update_heartbeat()

                current_state = self.state.get_state('internal_state')
                if current_state == 'error':
                    logger.warning("Agent is in error state. Pausing activity.")
                    # Consider more robust error handling or recovery logic here
                    await asyncio.sleep(agent_config.AGENT_MAIN_LOOP_SLEEP * 2) # Longer sleep in error state
                elif current_state == 'paused':
                    logger.info("Agent is paused. Skipping active tasks.")
                    await asyncio.sleep(agent_config.AGENT_MAIN_LOOP_SLEEP)
                else:
                    # Normal operation placeholder
                    pass

                await asyncio.sleep(agent_config.AGENT_MAIN_LOOP_SLEEP)

        except asyncio.CancelledError:
            logger.info("Agent run loop cancelled.")
        except Exception as e:
            logger.error(f"Unhandled exception in agent run loop: {e}", exc_info=True)
            self.state.set_last_error(f"Unhandled run loop error: {e}")
            self.state.set_internal_state('error')
        finally:
            logger.info("Agent run loop finished. Initiating cleanup...")
            await self.cleanup_async()

    @log_exceptions
    def handle_server_command_wrapper(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Wraps the CommandHandler's method to fit the ServerManager callback signature."""
        # This wrapper ensures the command handler has access to the agent instance
        # and handles potential async nature if needed in the future.

        # Directly call the synchronous handler method
        result = self.command_handler.handle_server_command(command)
        logger.debug(f"Command handler result: {result}")
        return result

    @log_exceptions
    def handle_message_wrapper(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a message dictionary received from the message queue.
        """
        logger.info(f"Handling message: {message}")
        self.state.set_internal_state('busy') 

        try:
            response = process_message(
                self.llm_client,
                self.mq_handler.channel, # Pass the channel for publishing
                self.agent_id,
                message
            )
            self.state.set_internal_state('idle')
            logger.info(f"Message processed. Response: {response:!r}")
            return response

        except Exception as e:
            self.state.set_internal_state('error')
            logger.error(f"Error handling message: {e}", exc_info=True)
            self.state.set_last_error(f"Error handling message: {e}")

            return {
                "error": str(e),
                "agent_id": self.agent_id
            }

    @log_exceptions
    async def send_status_update_heartbeat(self):
        """Send periodic heartbeat status updates to the server."""
        now = datetime.now()
        if (now - self._last_status_update_time).total_seconds() >= agent_config.AGENT_STATUS_UPDATE_INTERVAL:
            logger.debug("Sending status update heartbeat...")
            full_status = self.state.get_full_status_for_update()

            if await self.server_manager.send_agent_status_update(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                last_seen=full_status.get('last_updated'), 
                metrics=full_status 
            ):
                self._last_status_update_time = now
            else:
                logger.warning("Failed to send status update.")

    @log_exceptions
    def setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            self.loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(self.shutdown(s))
            )

    @log_exceptions
    async def shutdown(self, sig: Optional[signal.Signals] = None):
        """Initiate graceful shutdown of the agent."""
        if self._shutdown_requested:
            logger.info("Shutdown already in progress.")
            return

        self._shutdown_requested = True
        if sig:
            logger.info(f"Received shutdown signal: {sig.name}. Initiating graceful shutdown...")
        else:
            logger.info("Shutdown requested programmatically. Initiating graceful shutdown...")

        self.state.set_internal_state('shutting_down')

        # Stop the main loop by cancelling its task (if run via asyncio.run)
        # Or simply let the loop condition self._shutdown_requested handle it
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        logger.info(f"Cancelling {len(tasks)} outstanding tasks.")
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug("Task cancelled successfully.")

        return

    @log_exceptions
    async def cleanup_async(self):
        """Perform asynchronous cleanup of agent resources."""

        # 1. Cleanup ServerManager (includes unregistering and closing gRPC)
        if self.server_manager:
            logger.info("Cleaning up ServerManager...")
            await self.server_manager.cleanup(self.agent_id)
            logger.info("ServerManager cleanup finished.")

        # 2. Cleanup MessageQueueHandler (closes connection, stops consumer)
        if self.mq_handler:
            logger.info("Cleaning up MessageQueueHandler...")
            self.mq_handler.cleanup()
            logger.info("MessageQueueHandler cleanup finished.")

        # 3. Cleanup LLMClient
        if self.llm_client:
            logger.info("Cleaning up LLMClient...")
            self.llm_client.cleanup()
            logger.info("LLMClient cleanup finished.")

        # Final state update
        self.state.set_internal_state('shutdown_complete') # Add a final state if needed

        logger.info(f"Asynchronous cleanup for agent {self.agent_name} complete.")


async def main(agent_name: Optional[str] = 'Name_not_provided'):
    """Entry point for running the agent."""

    agent = Agent(agent_name=agent_name)
    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, initiating shutdown...")
        # The signal handler should catch this, but as a fallback:
        if not agent._shutdown_requested:
            await agent.shutdown()
    finally:
        logger.info("Checking if event loop is running, and stopping it if necessary")
        loop = asyncio.get_event_loop()
        if loop.is_running():
            logger.info("Stopping event loop")
            loop.stop()
            logger.info("Stopped event loop")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the agent with optional name override.")
    parser.add_argument("--agent-name", type=str, help="Override the agent name (takes precedence over environment variable)")
    args = parser.parse_args()

    if args.agent_name:
        agent_name = args.agent_name
    else:
        agent_name = os.getenv("DEFAULT_AGENT_NAME", "Unknown_Agent")
    try:
        asyncio.run(main(agent_name=agent_name))
    except KeyboardInterrupt:
        logger.warning("Agent interrupted by user.")
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            logger.info("Event loop closed normally.")
        else:
            logger.error(f"RuntimeError in main execution: {e}", exc_info=True)
            sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during script execution: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Agent process finished.")
        sys.exit(0)
