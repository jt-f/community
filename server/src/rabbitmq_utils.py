import logging
import json
import pika
from typing import Optional
from datetime import datetime

# Import config and state
import config
import state

logger = logging.getLogger(__name__)

def get_rabbitmq_connection() -> Optional[pika.BlockingConnection]:
    """Gets or establishes a RabbitMQ connection."""
    if state.rabbitmq_connection and state.rabbitmq_connection.is_open:
        return state.rabbitmq_connection
    
    try:
        logger.info(f"Attempting to connect to RabbitMQ at {config.RABBITMQ_HOST}:{config.RABBITMQ_PORT}")
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=config.RABBITMQ_HOST, port=config.RABBITMQ_PORT)
        )
        state.rabbitmq_connection = connection
        logger.info("Successfully connected to RabbitMQ.")
        return connection
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        state.rabbitmq_connection = None
        return None

def close_rabbitmq_connection():
    """Closes the global RabbitMQ connection if it's open."""
    if state.rabbitmq_connection and state.rabbitmq_connection.is_open:
        try:
            state.rabbitmq_connection.close()
            logger.info("RabbitMQ connection closed.")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {e}")
        finally:
            state.rabbitmq_connection = None

def publish_to_queue(queue_name: str, message_data: dict) -> bool:
    """Publish a message to a specific RabbitMQ queue."""
    channel = None
    connection = get_rabbitmq_connection()
    
    if not connection:
        logger.error(f"No RabbitMQ connection available for publishing to {queue_name}.")
        return False

    try:
        channel = connection.channel()
        # Ensure queue exists
        channel.queue_declare(queue=queue_name, durable=True)
        
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        logger.info(f"Message successfully published to {queue_name}")
        return True
    except Exception as e:
        logger.error(f"Error publishing to queue {queue_name}: {e}")
        # Invalidate connection on publish error?
        # close_rabbitmq_connection()
        return False
    finally:
        if channel and channel.is_open:
            try:
                channel.close()
            except Exception as close_exc:
                logger.error(f"Error closing RabbitMQ channel after publishing: {close_exc}")

def publish_to_incoming_queue(message_data: dict) -> bool:
    """Publish a message to the incoming messages queue."""
    return publish_to_queue(config.INCOMING_QUEUE, message_data)

def publish_to_broker_control_queue(message_data: dict) -> bool:
    """Publish a control message to the broker control queue."""
    return publish_to_queue(config.BROKER_CONTROL_QUEUE, message_data)

def publish_server_advertisement():
    """Publish server availability to the advertisement queue."""
    advertisement = {
        "message_type": "SERVER_AVAILABLE", # Consider using MessageType enum if easily accessible
        "server_id": config.SERVER_ID,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "websocket_url": config.WEBSOCKET_URL
    }
    if publish_to_queue(config.SERVER_ADVERTISEMENT_QUEUE, advertisement):
        logger.info("Published server availability advertisement")
    else:
        logger.error("Failed to publish server availability advertisement")

# Helper function to process RabbitMQ events without blocking asyncio loop
def process_rabbitmq_events():
    if state.rabbitmq_connection and state.rabbitmq_connection.is_open:
        try:
            state.rabbitmq_connection.process_data_events(time_limit=0.1)
            return True
        except Exception as e:
            logger.error(f"Error processing RabbitMQ data events: {e}")
            close_rabbitmq_connection()
            return False
    return False 