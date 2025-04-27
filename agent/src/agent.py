import argparse
import asyncio
import functools
import json
import logging
import os
import uuid
from typing import Dict, Any, Callable, Optional, Awaitable
from dotenv import load_dotenv

load_dotenv() # Load .env file early

# Local imports
from shared_models import setup_logging, MessageType
from state import AgentState
from message_queue_handler import MessageQueueHandler
from server_manager import ServerManager
from llm_client import LLMClient
from messaging import process_message_dict, publish_to_broker_input_queue
from decorators import log_exceptions
import agent_config  # Import the new config file

# Configuration: prioritize environment variables, then config file defaults
AGENT_STATUS_UPDATE_INTERVAL = int(os.getenv('AGENT_STATUS_UPDATE_INTERVAL', agent_config.AGENT_STATUS_UPDATE_INTERVAL))
AGENT_MAIN_LOOP_SLEEP = int(os.getenv('AGENT_MAIN_LOOP_SLEEP', agent_config.AGENT_MAIN_LOOP_SLEEP))

# Configure logging
logger = setup_logging(__name__)
logging.getLogger("pika").setLevel(logging.WARNING)

class Agent:
    """
    Agent orchestrates the lifecycle and communication for a single LLM agent instance.
    It manages registration with the server, message queue consumption, LLM interaction,
    and state transitions. Dependencies are injected for messaging, server, and LLM handling.
    """
    def __init__(self, agent_name: str):
        """Initialize agent with dependencies and unique identifier"""
        self.agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        self.agent_name = agent_name
        self.loop = asyncio.get_event_loop()

        # Initialize state and components
        self.state = AgentState()
        self.llm_client = LLMClient(state_update=self.handle_state_change)
        self.mq_handler = MessageQueueHandler(
            state_update=self.handle_state_change,
            message_handler=self.handle_message,
            loop=self.loop
        )
        self.server_manager = ServerManager(
            state_update=self.handle_state_change,
            command_callback=self.handle_server_command
        )

        # Configure agent-specific settings
        self.agent_queue = f"agent_{self.agent_id}_queue"
        self._shutdown_requested = False
        
        logger.info(f"Agent {self.agent_name} initialized with ID: {self.agent_id}")

    async def connect(self) -> None:
        """Connect to message queue and register with server"""
        logger.info(f"Starting agent {self.agent_name} ({self.agent_id})")
        
        # Connect to RabbitMQ
        await self._connect_to_message_queue()
        
        # Register with server
        await self.server_manager.register(agent_id=self.agent_id, agent_name=self.agent_name)
        
        # Start periodic status updates
        asyncio.create_task(self._periodic_status_update())

    async def _connect_to_message_queue(self) -> None:
        """Connect to RabbitMQ message queue"""

        mq_connected = self.mq_handler.connect(queue_name=self.agent_queue)
        if not mq_connected:
            logger.error("Failed to connect/setup RabbitMQ: aborting agent startup.")
            raise RuntimeError("RabbitMQ connection failed. Check RabbitMQ server and configuration.")
        logger.info(f"Connected to RabbitMQ queue: {self.agent_queue}")


    async def _periodic_status_update(self) -> None:
        """Send unsolicited status updates periodically to the server"""
        while not self._shutdown_requested:
            try:
                await self._send_status_update()
            except Exception as e:
                logger.error(f"Periodic status update failed: {e}")
            await asyncio.sleep(AGENT_STATUS_UPDATE_INTERVAL)

    async def run(self) -> None:
        """Main agent loop. Keeps the agent alive after registration."""
        logger.info("Agent main loop started. Agent is running.")
        try:
            # Set initial state to idle after successful startup
            self.handle_state_change('internal_state', 'idle')
            
            # Main loop - just keep the agent alive
            while not self._shutdown_requested:
                await asyncio.sleep(AGENT_MAIN_LOOP_SLEEP)
        except asyncio.CancelledError:
            logger.info("Agent main loop cancelled.")

    async def cleanup_async(self) -> None:
        """Clean up resources before shutdown"""
        logger.info("Starting async cleanup...")
        self.handle_state_change('internal_state', 'shutting_down')
        await self.server_manager.cleanup(self.agent_id)
        self.mq_handler.cleanup()
        self.llm_client.cleanup()
        logger.info("Async cleanup complete.")

    @log_exceptions
    def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming messages from the message queue"""
        logger.info(f"Handling message: {message} : sending for processing")
        return process_message_dict(self, message)

    @log_exceptions
    def handle_server_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Process commands received from the server"""
        logger.info(f"Handling command via ServerManager: {command}")
        
        command_type = command.get("type", "")
        command_id = command.get("command_id", "unknown")
        
        # Initialize result with default values
        result = {
            "success": True,
            "output": "Command acknowledged",
            "error_message": "",
            "exit_code": 0
        }
        
        # Process command based on type
        command_handlers = {
            "pause": self._handle_pause_command,
            "resume": self._handle_resume_command,
            "shutdown": self._handle_shutdown_command,
            "status": self._handle_status_command
        }
        
        handler = command_handlers.get(command_type)
        if handler:
            # All handlers now accept the command parameter for consistency
            handler_result = handler(command)
            result.update(handler_result)
        else:
            logger.warning(f"Received unknown command type: {command_type}")
            result.update({
                "success": False,
                "output": f"Unknown command type: {command_type}",
                "error_message": f"Command type {command_type} not supported",
                "exit_code": 1
            })

        logger.debug(f"Command result for {command_id}: {result}")
        return result

    def _handle_pause_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle pause command from server"""
        self.mq_handler.set_consuming(False)
        self.handle_state_change('internal_state', 'paused')
        return {"output": f"Agent {self.agent_name} paused."}

    def _handle_resume_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resume command from server"""
        if self.state.get_state('internal_state') != 'paused':
            return {
                "success": False,
                "output": f"Agent {self.agent_name} is not paused.",
                "error_message": "Cannot resume an agent that is not paused.",
                "exit_code": 1
            }
        self.mq_handler.set_consuming(True)
        self.handle_state_change('internal_state', 'idle')
        return {"output": f"Agent {self.agent_name} resumed."}

    def _handle_shutdown_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle shutdown command from server"""
        logger.info(f"Received shutdown command: {command}")
        self._shutdown_requested = True
        self.handle_state_change('internal_state', 'shutting_down')
        # Trigger cleanup and exit
        asyncio.create_task(self.cleanup_async()).add_done_callback(
            lambda _: self.loop.stop() if self.loop.is_running() else None
        )
        return {"output": f"Agent {self.agent_name} shutting down."}

    def _handle_status_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status command from server"""
        status = self.state.get_state()
        return {"output": f"Agent status: {json.dumps(status)}"}

    async def _send_status_update(self) -> None:
        """Send a gRPC status update to the server with the full agent state"""
        await self.server_manager.send_agent_status_update(
            self.agent_id,
            self.agent_name,
            self.state.get_state('last_seen') if 'last_seen' in self.state.get_state() else '',
            self.state.get_state()
        )


    def handle_state_change(self, key: str, value: Any) -> None:
        """Update agent state and trigger status update"""
        self.state.set_state(key, value)
        logger.info(f"Agent state changed: {key} = {value}")
        logger.debug(f"Overall state: {self.state.__repr__()}")
        
        # Send gRPC status update to server on every state change
        asyncio.create_task(self._send_status_update())

    def generate_response(self, incoming_message_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a response using the LLM and format it for publishing"""
        logger.info(f"Agent generating response for message: {incoming_message_dict}")
        
        # Get response from LLM
        llm_response_text = self.llm_client.generate_response(incoming_message_dict.get("text_payload", ""))
        
        # Construct response message
        response_message_dict = {
            "message_id": f"msg_{uuid.uuid4().hex[:8]}",
            "sender_id": self.agent_id,
            "message_type": MessageType.TEXT,
            "text_payload": llm_response_text,
            "original_message_id": incoming_message_dict.get("message_id", "unknown"),
            "routing_status": "pending"
        }
        
        # Publish response
        self._publish_response(response_message_dict)
        
        return response_message_dict

    def _publish_response(self, response_message_dict: Dict[str, Any]) -> None:
        """Publish response to broker input queue"""
        if self.mq_handler and self.mq_handler.channel:
            publish_to_broker_input_queue(self.mq_handler.channel, response_message_dict)
            logger.info(f"Published response message {response_message_dict['message_id']} for original message {response_message_dict['original_message_id']}")
        else:
            logger.warning(f"Cannot publish response message {response_message_dict['message_id']}: MQ channel not available.")

@log_exceptions
async def main() -> None:
    """Parse command line arguments and run the agent"""
    parser = argparse.ArgumentParser(description="Run an agent")
    parser.add_argument("--name", type=str, required=True, help="Human-readable name for this agent")
    args = parser.parse_args()
    
    agent = Agent(agent_name=args.name)
    try:
        await agent.connect()
        await agent.run()
    except asyncio.CancelledError:
        logger.info("Main function cancelled (likely during shutdown).")
    finally:
        await agent.cleanup_async()
        logger.info("Agent shutdown sequence complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Agent process terminated by user.")
    except Exception as e:
        logger.critical(f"Fatal error in agent process: {e}", exc_info=True)
        exit(1)
