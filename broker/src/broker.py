import logging
import json
import random
import asyncio
from typing import Dict, Any

# Third-party imports
from dotenv import load_dotenv

# Local application imports
from shared_models import setup_logging, MessageType
from state import BrokerState
from message_queue_handler import MessageQueueHandler
from server_manager import ServerManager
from decorators import log_exceptions

load_dotenv()

# Configure logging
logger = setup_logging(__name__)
logging.getLogger("pika").setLevel(logging.WARNING)


class Broker:
    """Coordinates message routing, agent state, and server communication."""

    def __init__(self):
        """Initializes the Broker, setting up ID, queues, state, and handlers."""
        self.broker_id = f"broker_{random.randint(1000, 9999)}"
        self.broker_input_queue = "broker_input_queue"
        self.server_input_queue = "server_input_queue"

        self.state = BrokerState()
        self.mq_handler = MessageQueueHandler(
            state_update=self.handle_state_change,
            message_handler=self.handle_message
        )
        self.server_manager = ServerManager(
            broker_id=self.broker_id,
            state_update=self.handle_state_change,
            command_callback=self.state.update_agents_from_status
        )

        logger.info(f"Broker {self.broker_id} initialized.")

    @log_exceptions
    async def connect(self) -> None:
        """Connects to RabbitMQ and registers with the gRPC server."""
        logger.info(f"Starting broker {self.broker_id}")

        # Connect to RabbitMQ synchronously and check result
        try:
            mq_connected = self.mq_handler.connect(queue_name=self.broker_input_queue)
            if not mq_connected:
                logger.error("Failed to connect/setup RabbitMQ: aborting broker startup.")
                raise RuntimeError("RabbitMQ connection failed. Check RabbitMQ server and configuration.")
        except Exception as e:
            logger.error(f"RabbitMQ connection error: {e}")
            raise RuntimeError(f"RabbitMQ connection failed: {e}")

        # Register with the gRPC server
        await self.server_manager.register()

    @log_exceptions
    async def run(self):
        """Main broker loop. Keeps the broker alive after connection and registration."""
        logger.info("Broker main loop started. Broker is running.")
        try:
            while True:
                # Keep the loop alive, potentially add periodic tasks here
                await asyncio.sleep(3600) # Sleep for a long time
        except asyncio.CancelledError:
            logger.info("Broker main loop cancelled.")
        finally:
            logger.info("Broker main loop finished.")

    @log_exceptions
    async def cleanup_async(self):
        """Performs asynchronous cleanup of resources."""
        logger.info("Starting async cleanup...")
        self.handle_state_change('internal_state', 'shutting_down')
        # Stop gRPC subscription first
        await self.server_manager.stop()
        # Then cleanup MQ handler
        self.mq_handler.cleanup()
        logger.info("Async cleanup complete.")

    @log_exceptions
    def publish_to_server_input_queue(self, message_data: dict) -> bool:
        """Publishes a message to the central server input queue."""
        return self.mq_handler.publish(self.server_input_queue, message_data)

    @log_exceptions
    async def _handle_routable_message(self, message_data: Dict[str, Any]):
        """Handles TEXT, REPLY, and SYSTEM messages, routing if necessary."""
        message_id = message_data.get("message_id", "Unknown")
        sender_id = message_data.get("sender_id", "unknown")
        receiver_id = message_data.get("receiver_id")
        routing_status = message_data.get("routing_status")
        text_payload = message_data.get("text_payload", "")
        message_type = message_data.get("message_type")

        logger.info(f"Incoming {message_type} message {message_id} from {sender_id}: '{text_payload[:50]}' (routing={routing_status})")

        target_agent_info = await self.state.get_agent_info(receiver_id) if receiver_id else None
        is_target_online = target_agent_info.get("is_online", False) if target_agent_info else False

        # If message already has a valid, online receiver, forward directly
        if receiver_id and routing_status != "error" and is_target_online:
            logger.info(f"Message {message_id} has valid online receiver ({receiver_id}), forwarding directly.")
            message_data["routing_status"] = "routed" # Ensure status is set
            self.publish_to_server_input_queue(message_data)
        else:
            # Otherwise, attempt to route it
            logger.info(f"Message {message_id} needs routing (receiver: {receiver_id}, status: {routing_status}, online: {is_target_online}).")
            await self.route_message(message_data)

    @log_exceptions
    async def _handle_agent_status_update(self, message_data: Dict[str, Any]):
        """Handles AGENT_STATUS_UPDATE messages (should come via gRPC, not queue)."""
        sender_id = message_data.get("sender_id", "unknown") # Should be 'Server' ideally
        logger.warning(f"Received AGENT_STATUS_UPDATE from {sender_id} in broker input queue (unexpected). Processing anyway...")
        await self.state.update_agents_from_status(message_data)

    @log_exceptions
    async def _handle_error_message(self, message_data: Dict[str, Any]):
        """Handles ERROR messages by forwarding them to the server's input queue."""
        sender_id = message_data.get("sender_id", "unknown")
        message_id = message_data.get("message_id", "N/A")
        logger.warning(f"Received ERROR message {message_id} from {sender_id}. Forwarding to server.")
        if "routing_status" not in message_data:
            message_data["routing_status"] = "error" # Ensure error status is set
        self.publish_to_server_input_queue(message_data)

    @log_exceptions
    async def handle_message(self, message_data: Dict[str, Any]):
        """Main message handler callback for RabbitMQ, delegates based on message_type."""
        # Ensure message_data is a dict (MQ handler should decode JSON)
        if not isinstance(message_data, dict):
             logger.error(f"Invalid message data type received: {type(message_data)}")
             return # Cannot process non-dict data

        message_id = message_data.get('message_id', 'N/A')
        message_type = message_data.get('message_type', 'unknown')
        logger.info(f"Broker received message: {message_id}, type: {message_type}")
        # logger.debug(f"Full message data: {message_data}") # Uncomment for detailed debugging

        try:
            if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                await self._handle_routable_message(message_data)
            elif message_type == MessageType.AGENT_STATUS_UPDATE:
                # This path is unexpected, status should come via gRPC stream
                await self._handle_agent_status_update(message_data)
            elif message_type == MessageType.ERROR:
                await self._handle_error_message(message_data)
            else:
                sender_id = message_data.get("sender_id", "unknown")
                logger.warning(f"Received unsupported message type '{message_type}' from {sender_id} in broker queue.")

        except Exception as e:
            # Catch unexpected errors during handling
            logger.error(f"Error handling message {message_id} ({message_type}): {e}", exc_info=True)
            # Optionally, send an error message back or to the server

    @log_exceptions
    async def route_message(self, message_data: Dict[str, Any]):
        """Routes a message to a suitable online agent if no receiver is specified or receiver is offline."""
        message_type = message_data.get("message_type")
        sender_id = message_data.get("sender_id", "unknown")
        message_id = message_data.get("message_id", "N/A")
        logger.debug(f"Routing message {message_id} from {sender_id} (type={message_type})")

        # Prepare the outgoing message, removing internal routing hints
        outgoing_message = message_data.copy()
        for field in ["_broadcast", "_target_agent_id", "_client_id"]:
            outgoing_message.pop(field, None)
        outgoing_message["routing_status"] = "routed" # Mark as routed

        original_text = message_data.get("text_payload", "")
        truncated_text = (original_text[:30] + '...') if len(original_text) > 30 else original_text

        # Find available online agents, excluding the sender
        online_agents = await self.state.get_online_agents(exclude_sender_id=sender_id)
        logger.info(f"Online agents available for routing (excluding sender {sender_id}): {online_agents}")

        if online_agents:
            # Choose a random online agent
            chosen_agent_id = random.choice(online_agents)
            outgoing_message["receiver_id"] = chosen_agent_id
            logger.info(f"Routing message '{truncated_text}' ({message_id}) from {sender_id} to agent {chosen_agent_id}")
            self.publish_to_server_input_queue(outgoing_message)
        else:
            # Handle case where no suitable agent is found
            all_online_agents = await self.state.get_online_agents()
            logger.warning(f"Could not route message '{truncated_text}' ({message_id}) from {sender_id}. No suitable online agents found.")
            error_text = "No other online agents available to handle the message."
            if sender_id in all_online_agents and len(all_online_agents) == 1:
                sender_info = await self.state.get_agent_info(sender_id)
                agent_name = sender_info.get("name", sender_id) if sender_info else sender_id
                error_text = f"Only you ({agent_name}) are online right now."

            # Send an error message back to the original sender via the server queue
            error_response = {
                "message_id": message_id, # Reference original message
                "message_type": MessageType.ERROR,
                "sender_id": self.broker_id, # Error originates from broker
                "receiver_id": sender_id, # Send error back to original sender
                "routing_status": "error",
                "error_details": error_text,
                "text_payload": f"Failed to route your message: {error_text}"
            }
            logger.info(f"Sending routing error back to {sender_id} for message {message_id}")
            self.publish_to_server_input_queue(error_response)

    @log_exceptions
    def handle_state_change(self, component: str, status: Any):
        """Callback to handle state changes from components (MQ, ServerManager)."""
        logger.info(f"State change reported: Component='{component}', Status='{status}'")
        # Update internal state or take actions based on component status
        asyncio.create_task(self.state.set_state(component, status))
        # Example: If MQ disconnects, maybe try to reconnect or alert
        if component == 'message_queue_status' and status == 'disconnected':
            logger.warning("Message queue disconnected. Further action may be needed.")
        elif component == 'registration_status' and status == 'failed':
            logger.error("Broker registration failed. Broker might not function correctly.")


@log_exceptions
async def main():
    """Parse command line arguments and run the broker"""
    broker = Broker()
    try:
        await broker.connect()
        await broker.run()
    except asyncio.CancelledError:
        logger.info("Main function cancelled (likely during shutdown).")
    finally:
        await broker.cleanup_async()
        logger.info("Broker shutdown sequence complete.")

if __name__ == "__main__":
    asyncio.run(main())