import logging
import json
import random
from typing import Dict, Any
import asyncio
from dotenv import load_dotenv

load_dotenv()

from shared_models import setup_logging, MessageType
from state import BrokerState
from message_queue_handler import MessageQueueHandler
from server_manager import ServerManager

# Configure logging
logger = setup_logging(__name__)
logging.getLogger("pika").setLevel(logging.WARNING)

class Broker:
    def __init__(self):
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

        logger.info(f"Broker {self.broker_id} initialized with ID: {self.broker_id}")

    async def connect(self) -> None:
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

        await self.server_manager.register()

    async def run(self):
        """Main broker loop. Keeps the broker alive after registration."""
        logger.info("Broker main loop started. Broker is running.")

        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Broker main loop cancelled.")
        except Exception as e:
            logger.error(f"Broker main loop error: {e}")

    async def cleanup_async(self):
        logger.info("Starting async cleanup...")
        self.handle_state_change('internal_state', 'shutting_down')
        self.mq_handler.cleanup()
        logger.info("Async cleanup complete.")

    def publish_to_server_input_queue(self, message_data: dict) -> bool:
        return self.mq_handler.publish(self.server_input_queue, message_data)

    async def _handle_routable_message(self, message_data: Dict[str, Any]):
        """Handles TEXT, REPLY, and SYSTEM messages that might need routing."""
        message_id = message_data.get("message_id", "Unknown")
        sender_id = message_data.get("sender_id", "unknown")
        receiver_id = message_data.get("receiver_id")
        routing_status = message_data.get("routing_status")
        text_payload = message_data.get("text_payload", "")
        message_type = message_data.get("message_type")

        logger.info(f"Incoming {message_type} message {message_id} from {sender_id} : '{text_payload[:50]}' (routing_status={routing_status})")

        target_agent_info = await self.state.get_agent_info(receiver_id) if receiver_id else None

        # If message already has a valid, online receiver, forward directly
        if receiver_id and routing_status != "error" and target_agent_info and target_agent_info.get("is_online", False):
            logger.info(f"Message {message_id} already has valid online receiver_id ({receiver_id}), forwarding directly.")
            message_data["routing_status"] = "routed"
            self.publish_to_server_input_queue(message_data)
        else:
            # Otherwise, attempt to route it
            logger.info(f"Message {message_id} needs routing (receiver: {receiver_id}, status: {routing_status}, agent_online: {target_agent_info.get('is_online', False) if target_agent_info else 'N/A'}).")
            await self.route_message(message_data)

    async def _handle_agent_status_update(self, message_data: Dict[str, Any]):
        """Handles AGENT_STATUS_UPDATE messages (unexpected in this queue)."""
        sender_id = message_data.get("sender_id", "unknown")
        logger.warning(f"Received AGENT_STATUS_UPDATE from {sender_id} in broker input queue (unexpected). Processing anyway...")
        await self.state.update_agents_from_status(message_data)

    async def _handle_error_message(self, message_data: Dict[str, Any]):
        """Handles ERROR messages by forwarding them to the server."""
        sender_id = message_data.get("sender_id", "unknown")
        logger.warning(f"Received ERROR message {message_data.get('message_id', 'N/A')} from {sender_id}. Forwarding to server.")
        if "routing_status" not in message_data:
            message_data["routing_status"] = "error"
        self.publish_to_server_input_queue(message_data)

    async def handle_message(self, message_data: Dict[str, Any]):
        """Main message handler, delegates based on message_type."""
        # Convert gRPC message to serializable format if needed (consider moving this to MQ handler if always needed)
        if hasattr(message_data, 'ListFields'):
            logger.debug("Converting gRPC message to dict")
            message_data = {k.name: v for k, v in message_data.ListFields()}

        logger.info(f"Broker received new message: {message_data.get('message_id', 'N/A')}, type: {message_data.get('message_type', 'unknown')}")
        # logger.debug(f"Full message data: {message_data}") # Optional: Log full data for debugging

        try:
            message_type = message_data.get("message_type", "unknown")

            if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                await self._handle_routable_message(message_data)
            elif message_type == MessageType.AGENT_STATUS_UPDATE:
                await self._handle_agent_status_update(message_data)
            elif message_type == MessageType.ERROR:
                await self._handle_error_message(message_data)
            else:
                sender_id = message_data.get("sender_id", "unknown")
                logger.warning(f"Received unsupported message type in broker input queue: {message_type} from {sender_id}")

        except json.JSONDecodeError:
            # This shouldn't happen if MQ handler decodes, but as a safeguard
            logger.error(f"Invalid JSON encountered in handle_message: {message_data}")
        except Exception as e:
            logger.error(f"Error processing message {message_data.get('message_id', 'N/A')}: {e}", exc_info=True)

    async def route_message(self, message_data):
        # Convert gRPC message to serializable format if needed
        if hasattr(message_data, 'ListFields'):
            message_data = {k: v for k, v in message_data.ListFields()}
            
        message_type = message_data.get("message_type")
        sender_id = message_data.get("sender_id", "unknown")
        message_id = message_data.get("message_id", "N/A")
        logger.debug(f"[DEBUG] Routing message {message_id} from {sender_id} type={message_type}")
        sender_info = await self.state.get_agent_info(sender_id)
        if sender_id.startswith("agent_") and not sender_info:
            logger.warning(f"Message from unknown agent {sender_id}. State might be stale.")
        outgoing_message = dict(message_data)
        for field in ["_broadcast", "_target_agent_id", "_client_id"]:
            if field in outgoing_message:
                outgoing_message.pop(field)
        outgoing_message["routing_status"] = "routed"
        original_text = message_data.get("text_payload", "")
        truncated_text = (original_text[:20] + '...') if len(original_text) > 20 else original_text
        all_agents = await self.state.get_all_agents()
        # Ensure all_agents is serializable before logging
        try:
            serializable_agents = json.dumps(all_agents)
        except TypeError:
            # Basic conversion for logging if direct dump fails
            serializable_agents = str(all_agents) 
            logger.warning("Could not serialize agent state directly for logging.")
        logger.info(f"All known agents from state manager: {serializable_agents}")
        for agent_id, info in all_agents.items():
            logger.debug(f"[DEBUG] Agent {agent_id}: name={info.get('name', 'unknown')}, is_online={info.get('is_online', False)}")
        online_agents = await self.state.get_online_agents(exclude_sender_id=sender_id)
        logger.info(f"Online agents available for routing (excluding sender {sender_id}): {online_agents}")
        if online_agents:
            chosen_agent_id = random.choice(online_agents)
            outgoing_message["receiver_id"] = chosen_agent_id
            logger.info(f"Routing message {message_id} from {sender_id} to agent {chosen_agent_id}")
            self.publish_to_server_input_queue(outgoing_message)
            return
        else:
            all_online_agents = await self.state.get_online_agents()
            logger.info(f"All online agents (including sender): {all_online_agents}")
            error_text = ""
            if sender_id in all_online_agents and len(all_online_agents) == 1:
                sender_info = await self.state.get_agent_info(sender_id)
                agent_name = sender_info.get("name", sender_id) if sender_info else sender_id
                error_text = f"Only the sending agent {agent_name} is online. Cannot route message."
                logger.warning(f"{error_text} Cannot route message '{truncated_text}' to another agent.")
            else:
                error_text = "No other online agents available. Routing failed."
                logger.warning(f"Could not route message '{truncated_text}' from {sender_id}: {error_text}")
            error_response = {
                "message_id": message_id,
                "message_type": MessageType.ERROR,
                "sender_id": sender_id,
                "receiver_id": "Server",
                "routing_status": "error",
                "text_payload": original_text,
                "routing_status_message": error_text
            }
            self.publish_to_server_input_queue(error_response)
            return

    def handle_state_change(self, key, value):
        self.state.set_state(key, value)
        logger.info(f"Broker state changed: {key} = {value}")
        logger.info(f"Overall state: {self.state.__repr__()}")


async def main():

    broker = Broker()
    try:
        await broker.connect()
        await broker.run()
    except asyncio.CancelledError:
        logger.info("Main function cancelled (likely during shutdown).")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}", exc_info=True)
    finally:
        await broker.cleanup_async()
        logger.info("Broker shutdown sequence complete.")

if __name__ == "__main__":
    asyncio.run(main())