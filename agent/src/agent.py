import argparse
import asyncio
import json
import logging
import uuid

# Local imports
from shared_models import setup_logging, MessageType
from state import AgentState
from message_queue_handler import MessageQueueHandler
from server_manager import ServerManager
from llm_client import LLMClient
from messaging import process_message_dict, publish_to_broker_input_queue

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

        self.agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        self.agent_name = agent_name
        self.loop = asyncio.get_event_loop() # Get the main event loop

        self.state = AgentState()
        self.llm_client = LLMClient( state_update=self.handle_state_change)
        self.mq_handler = MessageQueueHandler(
            state_update=self.handle_state_change,
            message_handler=self.handle_message,
            loop=self.loop # Pass the loop to the handler
        )
        self.server_manager = ServerManager(
            state_update=self.handle_state_change,
            command_callback=self.handle_server_command
        )

        self.agent_queue = f"agent_{self.agent_id}_queue"
        logger.info(f"Agent {self.agent_name} initialized with ID: {self.agent_id}")

    async def connect(self) -> None:
        logger.info(f"Starting agent {self.agent_name} ({self.agent_id})")
        
        # Connect to RabbitMQ synchronously and check result
        try:
            mq_connected = self.mq_handler.connect(queue_name=self.agent_queue)
            if not mq_connected:
                logger.error("Failed to connect/setup RabbitMQ: aborting agent startup.")
                raise RuntimeError("RabbitMQ connection failed. Check RabbitMQ server and configuration.")
            else:
                logger.info(f"Connected to RabbitMQ queue: {self.agent_queue}")
        except Exception as e:
            logger.error(f"RabbitMQ connection error: {e}")
            raise RuntimeError(f"RabbitMQ connection failed: {e}")

        await self.server_manager.register(agent_id=self.agent_id, agent_name=self.agent_name, command_callback=self.handle_server_command)

    async def run(self):
        """Main agent loop. Keeps the agent alive after registration."""
        logger.info("Agent main loop started. Agent is running.")
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Agent main loop cancelled.")
        except Exception as e:
            logger.error(f"Agent main loop error: {e}")

    async def cleanup_async(self):
        logger.info("Starting async cleanup...")
        self.handle_state_change('internal_state', 'shutting_down')
        await self.server_manager.cleanup(self.agent_id)
        self.mq_handler.cleanup()
        self.llm_client.cleanup()
        logger.info("Async cleanup complete.")

    def handle_message(self, message):
        logger.info(f"Handling message: {message} : sending for processing")
        # Delegate message processing to messaging.process_message_dict for DRY/SOLID
        return process_message_dict(self, message)

    def handle_server_command(self, command):
        logger.info(f"Handling command via ServerManager: {command}")
        result = { "success": True, "output": "Command acknowledged", "error_message": "", "exit_code": 0 }
        command_type = command.get("type", "")
        command_id = command.get("command_id", "unknown")

        if command_type == "pause":
            self.mq_handler.set_consuming(False)
            self.handle_state_change('internal_state', 'paused')
            result["output"] = f"Agent {self.agent_name} paused."
        elif command_type == "resume" :
            if self.state.get_state('internal_state') != 'paused':
                result["output"] = f"Agent {self.agent_name} not paused, cannot resume. Current state: {self.state.get_state('internal_state')}"
                result["success"] = False
            else:
                self.mq_handler.set_consuming(True)
                self.handle_state_change('internal_state', 'idle')
                result["output"] = f"Agent {self.agent_name} resumed."
        elif command_type == "status":
            status = self.state.get_state()
            result["output"] = f"Agent status: {json.dumps(status)}"
        else:
            logger.warning(f"Received unknown command type: {command_type}")
            result.update({ "success": False, "output": f"Unknown command type: {command_type}", "error_message": f"Command type {command_type} not supported", "exit_code": 1 })

        logger.debug(f"Command result for {command_id}: {result}")
        return result

    async def _send_status_update_on_state_change(self):
        """Send a gRPC status update to the server with the full agent state using SendAgentStatus."""
        try:
            await self.server_manager.send_agent_status_update(
                self.agent_id,
                self.agent_name,
                self.state.get_state('last_seen') if 'last_seen' in self.state.get_state() else '',
                self.state.get_state()
            )
        except Exception as e:
            logger.debug(f"Failed to send status update on state change: {e}")

    def handle_state_change(self, key, value):
        self.state.set_state(key, value)
        logger.info(f"Agent state changed: {key} = {value}")
        logger.info(f"Overall state: {self.state.__repr__()}")
        # Send gRPC status update to server on every state change
        asyncio.create_task(self._send_status_update_on_state_change())

    def generate_response(self, incoming_message_dict):
        """Generate a response using the LLM and format it for publishing."""
        logger.info(f"Agent generating response for message: {incoming_message_dict}")
        
        llm_response_text = self.llm_client.generate_response(incoming_message_dict.get("text_payload", ""))
        logger.info(f"Agent received LLM response text: {llm_response_text}")

        # Construct the full response message dictionary
        response_message_dict = {
            "message_id": f"msg_{uuid.uuid4().hex[:8]}", # Generate unique ID for the response
            "sender_id": self.agent_id,
            "message_type": MessageType.TEXT, # Specific message type
            "text_payload": llm_response_text,
            "original_message_id": incoming_message_dict.get("message_id", "unknown"), # Link to original message
            "routing_status": "pending" # Set routing status
        }
        
        logger.info(f"Constructed response message: {response_message_dict}")

        # Publish the structured response using the correct channel from mq_handler
        if self.mq_handler and self.mq_handler.channel:
            publish_to_broker_input_queue(self.mq_handler.channel, response_message_dict)
            logger.info(f"Published response message {response_message_dict['message_id']} for original message {response_message_dict['original_message_id']}")
        else:
            logger.warning(f"Cannot publish response message {response_message_dict['message_id']}: MQ channel not available.")

        return response_message_dict # Return the full structured response

async def main():
    parser = argparse.ArgumentParser(description="Run an agent")
    parser.add_argument("--name", type=str, required=True, help="Human-readable name for this agent")
    args = parser.parse_args()
    agent = Agent(agent_name=args.name)
    try:
        await agent.connect()
        await agent.run()
    except asyncio.CancelledError:
        logger.info("Main function cancelled (likely during shutdown).")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}", exc_info=True)
    finally:
        await agent.cleanup_async()
        logger.info("Agent shutdown sequence complete.")

if __name__ == "__main__":
    asyncio.run(main())
