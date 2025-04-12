import json
import pika
from typing import Optional
from datetime import datetime

# Import config and state
from shared_models import setup_logging
import config
import state

# Configure logging
logger = setup_logging(__name__)

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
        logger.info(f"Message {message_data.get('message_id','N/A')} published to {queue_name}")
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

def publish_to_broker_input_queue(message_data: dict) -> bool:
    """Publish a message to the main broker input queue."""
    return publish_to_queue(config.BROKER_INPUT_QUEUE, message_data)

def publish_to_agent_metadata_queue(message_data: dict) -> bool:
    """Publish an agent metadata message (register, disconnect) to the queue."""
    return publish_to_queue(config.AGENT_METADATA_QUEUE, message_data)

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

def setup_agent_queue(queue_name: str) -> bool:
    """Create or verify an agent's message queue exists.
    
    Args:
        queue_name: The name of the queue to create/verify (usually agent_queue_{agent_id})
        
    Returns:
        bool: True if queue is successfully created or already exists
    """
    connection = get_rabbitmq_connection()
    if not connection:
        logger.error(f"Cannot setup queue {queue_name}: No RabbitMQ connection")
        return False
        
    try:
        channel = connection.channel()
        # Ensure queue exists and is durable
        channel.queue_declare(queue=queue_name, durable=True)
        logger.info(f"Successfully created/verified queue: {queue_name}")
        channel.close()
        return True
    except Exception as e:
        logger.error(f"Failed to setup queue {queue_name}: {e}")
        return False

def publish_to_agent_queue(agent_id: str, message_data: dict) -> bool:
    """Publish a message directly to an agent's queue.
    
    Args:
        agent_id: The ID of the agent to send the message to
        message_data: The message to send
        
    Returns:
        bool: True if message is successfully published
    """
    queue_name = f"agent_queue_{agent_id}"
    result = publish_to_queue(queue_name, message_data)
    if result:
        logger.info(f"Published message to agent {agent_id} queue")
    else:
        logger.error(f"Failed to publish message to agent {agent_id} queue")
    return result 