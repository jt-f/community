"""Handles message processing, generation, and publishing for the agent."""
import pika
import json
from shared_models import setup_logging
import uuid
from decorators import log_exceptions
from typing import Dict, Any
import logging

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module

@log_exceptions
def publish_to_broker_input_queue(rabbitmq_channel, message_dict):
    """
    Publish a pre-formatted response message dictionary to the broker input queue.
    """
    if not rabbitmq_channel:
        logger.error("Cannot publish: RabbitMQ connection not established")
        return False
    try:
        rabbitmq_channel.queue_declare(queue="broker_input_queue", durable=True)
        rabbitmq_channel.basic_publish(
            exchange='',
            routing_key="broker_input_queue",
            body=json.dumps(message_dict),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        logger.info(f"Published response message {message_dict.get('message_id', 'N/A')} to broker_input_queue")
        return True
    except TypeError as e:
        logger.error(f"Failed to serialize message for publishing: {e} - Message: {message_dict}")
        return False


@log_exceptions
def process_message(llm_client, mq_channel, agent_id: str, message: Dict[str, Any] ):
    """
    Process a message, generate a response using the LLM, and publish it.
    """
    logger.info(f"Processing message: {message!r}")

    llm_response_text = llm_client.generate_response(message.get("text_payload", ""))

    response_message = {
        "message_id": f"msg_{uuid.uuid4()}",
        "sender_id": agent_id, # Use the passed agent_id
        "message_type": message.get("message_type", "unknown"), # Preserve original type or default
        "text_payload": llm_response_text,
        "original_message_id": message.get("message_id", "unknown"),
        "routing_status": "pending"
    }
    
    # Publish response using the provided MQ channel
    if mq_channel:
        publish_to_broker_input_queue(mq_channel, response_message)
    else:
        logger.warning("MQ channel not provided, cannot publish response.")

    return response_message

