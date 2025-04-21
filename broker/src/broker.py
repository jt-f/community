import logging
import threading
import json
import time
import pika
import os
import random
from datetime import datetime
from typing import Dict
import asyncio
import signal
from shared_models import setup_logging, MessageType, ResponseStatus
import grpc_client
from state import BrokerStateManager

logger = setup_logging(__name__)

# Define the broker name/ID
BROKER_ID = f"broker_{random.randint(1000, 9999)}"

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
logger.info("Pika library logging level set to WARNING.")

# Connection details
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
BROKER_INPUT_QUEUE = "broker_input_queue"
AGENT_METADATA_QUEUE = "agent_metadata_queue"
SERVER_INPUT_QUEUE = "server_input_queue"
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# Instantiate the state manager
state_manager = BrokerStateManager()

# Global flag for shutdown coordination
shutdown_event = asyncio.Event()

# --- RabbitMQ Setup and Management ---
def setup_rabbitmq_channel(queue_name, callback_function):
    """Set up a RabbitMQ channel and consumer."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT))
        channel = connection.channel()
        
        # Declare the queue, ensuring it exists
        channel.queue_declare(queue=queue_name, durable=True)
        
        # Set up the consumer
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=lambda ch, method, properties, body: callback_function(ch, method, properties, body),
            auto_ack=False
        )
        
        logger.info(f"Connected to RabbitMQ and consuming from {queue_name}")
        return channel
    except Exception as e:
        logger.error(f"Failed to set up RabbitMQ channel for {queue_name}: {e}")
        return None

def publish_to_server_input_queue(message_data: dict) -> bool:
    """Publish a message to the server's input queue."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT))
        channel = connection.channel()

        channel.queue_declare(queue=SERVER_INPUT_QUEUE, durable=True)

        logger.info(f"Publishing message to {SERVER_INPUT_QUEUE}: {message_data}")
        channel.basic_publish(
            exchange='',
            routing_key=SERVER_INPUT_QUEUE,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(
                delivery_mode=2,
            )
        )

        logger.debug(f"Published message {message_data.get('message_id', 'N/A')} to {SERVER_INPUT_QUEUE}")

        connection.close()
        return True
    except Exception as e:
        logger.error(f"Failed to publish to {SERVER_INPUT_QUEUE}: {e}")
        return False

# --- Message Handling ---
async def handle_incoming_message(channel, method, properties, body):
    """Handle incoming chat messages from the BROKER_INPUT_QUEUE."""
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        sender_id = message_data.get("sender_id", "unknown")
        receiver_id = message_data.get("receiver_id")
        routing_status = message_data.get("routing_status", "unknown")

        if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
            logger.info(f"Incoming {message_type} message {message_data.get('message_id','N/A')} from {sender_id} : '{message_data.get('text_payload','N/A')}' (routing_status={routing_status})")

            target_agent_info = await state_manager.get_agent_info(receiver_id) if receiver_id else None
            if receiver_id and routing_status != "error" and target_agent_info and target_agent_info.get("is_online", False):
                logger.info(f"Message already has valid online receiver_id ({receiver_id}), forwarding directly.")
                message_data["routing_status"] = "routed"
                publish_to_server_input_queue(message_data)
            else:
                await route_message(message_data)

            channel.basic_ack(delivery_tag=method.delivery_tag)
        elif message_type == MessageType.AGENT_STATUS_UPDATE:
            logger.warning(f"Received AGENT_STATUS_UPDATE from {sender_id} in input queue (unexpected). Processing...")
            await state_manager.update_agents_from_status(message_data)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        elif message_type == MessageType.ERROR:
            logger.warning(f"Received ERROR message from {sender_id}. Forwarding to server.")
            if "routing_status" not in message_data:
                message_data["routing_status"] = "error"
            publish_to_server_input_queue(message_data)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        else:
            logger.warning(f"Received unsupported message type in broker input queue: {message_type} from {sender_id}")
            channel.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in message: {body}")
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing incoming message: {e}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# --- Message Routing ---
async def route_message(message_data):
    """Route messages to the appropriate recipients."""
    message_type = message_data.get("message_type")
    sender_id = message_data.get("sender_id", "unknown")
    message_id = message_data.get("message_id", "N/A")
    logger.debug(f"[DEBUG] Routing message {message_id} from {sender_id} type={message_type}")

    sender_info = await state_manager.get_agent_info(sender_id)
    if sender_id.startswith("agent_") and not sender_info:
        logger.warning(f"Message from unknown agent {sender_id}. State might be stale.")

    outgoing_message = dict(message_data)

    for field in ["_broadcast", "_target_agent_id", "_client_id"]:
        if field in outgoing_message:
            outgoing_message.pop(field)

    outgoing_message["routing_status"] = "routed"

    original_text = message_data.get("text_payload", "")
    truncated_text = (original_text[:20] + '...') if len(original_text) > 20 else original_text

    all_agents = await state_manager.get_all_agents()
    logger.debug(f"[DEBUG] All known agents from state manager: {json.dumps(all_agents)}")
    for agent_id, info in all_agents.items():
        logger.debug(f"[DEBUG] Agent {agent_id}: name={info.get('name', 'unknown')}, is_online={info.get('is_online', False)}")

    online_agents = await state_manager.get_online_agents(exclude_sender_id=sender_id)

    logger.info(f"Online agents available for routing (excluding sender {sender_id}): {online_agents}")

    if online_agents:
        chosen_agent_id = random.choice(online_agents)
        outgoing_message["receiver_id"] = chosen_agent_id
        logger.info(f"Routing message {message_id} from {sender_id} to agent {chosen_agent_id}")
        publish_to_server_input_queue(outgoing_message)
        return
    else:
        all_online_agents = await state_manager.get_online_agents()
        logger.info(f"All online agents (including sender): {all_online_agents}")

        error_text = ""
        if sender_id in all_online_agents and len(all_online_agents) == 1:
            sender_info = await state_manager.get_agent_info(sender_id)
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
        publish_to_server_input_queue(error_response)
        return

# --- gRPC Integration ---
async def request_agent_status_via_grpc():
    """Request a one-time agent status update via gRPC and update the state manager."""
    if hasattr(request_agent_status_via_grpc, '_last_request_time'):
        current_time = time.time()
        if current_time - request_agent_status_via_grpc._last_request_time < 5:
            logger.debug("Skipping manual agent status request due to rate limiting")
            return
        request_agent_status_via_grpc._last_request_time = current_time
    else:
        request_agent_status_via_grpc._last_request_time = time.time()

    try:
        grpc_host = os.getenv("GRPC_HOST", "localhost")
        grpc_port = int(os.getenv("GRPC_PORT", "50051"))

        status_update = await grpc_client.request_agent_status(
            host=grpc_host,
            port=grpc_port,
            broker_id=BROKER_ID
        )

        logger.info(f"Received manual gRPC status update response: {status_update}")

        if status_update:
            state_manager.update_agents_from_status(status_update)
        else:
            logger.error("Received None response from manual gRPC status request")

    except Exception as e:
        logger.error(f"Error requesting agent status via gRPC: {e}")
        logger.exception("Full traceback for gRPC error:")

async def register_broker_via_grpc():
    """Register the broker with the server using gRPC."""
    try:
        grpc_host = os.getenv("GRPC_HOST", "localhost")
        grpc_port = int(os.getenv("GRPC_PORT", "50051"))
        
        logger.info(f"Registering broker via gRPC with {grpc_host}:{grpc_port}")
        
        response = await grpc_client.register_broker(
            host=grpc_host,
            port=grpc_port,
            broker_id=BROKER_ID,
            broker_name="BrokerService"
        )
        
        if response.success:
            logger.info(f"Broker registered successfully with ID: {BROKER_ID}")
            return True
        else:
            logger.error(f"Broker registration failed: {response.message}")
            return False
            
    except Exception as e:
        logger.error(f"Error during broker registration via gRPC: {e}")
        return False

# --- RabbitMQ Consumer Running in Thread ---
def run_rabbitmq_consumer(channel):
    """Target function to run pika's blocking consumer in a separate thread."""
    try:
        logger.info(f"Starting RabbitMQ consumer thread for queue: {channel.consumer_tags[0] if channel.consumer_tags else 'unknown'}")
        channel.start_consuming()
    except Exception as e:
        logger.error(f"Exception in RabbitMQ consumer thread: {e}")
    finally:
        if channel and channel.is_open:
            try:
                channel.stop_consuming()
            except Exception as e:
                logger.error(f"Error stopping RabbitMQ consumer: {e}")

# --- Main Execution ---
async def main():
    """Main entry point for the broker."""
    def signal_handler():
        logger.info("Received termination signal, shutting down...")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    grpc_task = None
    try:
        if not await register_broker_via_grpc():
            logger.error("Failed to register broker with server. Exiting.")
            return

        logger.info("Requesting initial agent status...")
        await request_agent_status_via_grpc()

        grpc_host = os.getenv("GRPC_HOST", "localhost")
        grpc_port = int(os.getenv("GRPC_PORT", "50051"))
        logger.info(f"Starting gRPC client for agent status updates from {grpc_host}:{grpc_port}")
        grpc_task = asyncio.create_task(
            grpc_client.connect_to_grpc_server(
                host=grpc_host,
                port=grpc_port,
                broker_id=BROKER_ID,
                agent_status_callback=state_manager.update_agents_from_status
            )
        )

        broker_input_channel = setup_rabbitmq_channel(BROKER_INPUT_QUEUE, handle_incoming_message)
        if not broker_input_channel:
            logger.error("Failed to set up broker input channel. Exiting.")
            if grpc_task:
                grpc_task.cancel()
            return

        broker_input_thread = threading.Thread(
            target=run_rabbitmq_consumer,
            args=(broker_input_channel,)
        )
        broker_input_thread.daemon = True
        broker_input_thread.start()

        logger.info("Broker started and running...")

        while not shutdown_event.is_set():
            if grpc_task and grpc_task.done():
                try:
                    grpc_task.result()
                    logger.warning("gRPC client task finished unexpectedly without error.")
                except asyncio.CancelledError:
                    logger.info("gRPC client task was cancelled.")
                except Exception as e:
                    logger.error(f"gRPC client task failed: {e}")
                logger.error("gRPC connection lost. Shutting down broker as state updates are critical.")
                shutdown_event.set()
                break

            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
    finally:
        logger.info("Starting broker shutdown...")
        if grpc_task and not grpc_task.done():
            logger.info("Cancelling gRPC client task...")
            grpc_task.cancel()
            try:
                await grpc_task
            except asyncio.CancelledError:
                logger.info("gRPC client task successfully cancelled.")
            except Exception as e:
                logger.error(f"Error during gRPC task cancellation: {e}")

        logger.info("Broker shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())