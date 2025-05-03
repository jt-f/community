"""Handles message processing, generation, and publishing for the agent."""
import json
import logging
import uuid
from typing import Any, Dict, Optional

import pika

from decorators import log_exceptions
from shared_models import setup_logging

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)


@log_exceptions
def publish_to_broker_input_queue(rabbitmq_channel: Optional[pika.channel.Channel], message_dict: Dict[str, Any]) -> bool:
    """
    Publish a pre-formatted response message dictionary to the broker input queue.

    Args:
        rabbitmq_channel: The Pika channel to use for publishing.
        message_dict: The dictionary representing the message to publish.

    Returns:
        True if publishing was successful, False otherwise.
    """
    if not rabbitmq_channel or not rabbitmq_channel.is_open:
        logger.error("Cannot publish: RabbitMQ channel is not available or closed.")
        return False
    try:
        # Ensure the queue exists (idempotent operation)
        rabbitmq_channel.queue_declare(queue="broker_input_queue", durable=True)
        rabbitmq_channel.basic_publish(
            exchange='',
            routing_key="broker_input_queue",
            body=json.dumps(message_dict),
            properties=pika.BasicProperties(delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE) # Use constant
        )
        logger.info(f"Published message {message_dict.get('message_id', 'N/A')} to broker_input_queue")
        return True
    except TypeError as e:
        logger.error(f"Failed to serialize message for publishing: {e} - Message: {message_dict}", exc_info=True)
        return False
    except pika.exceptions.AMQPError as e:
        logger.error(f"AMQP error during publishing: {e}", exc_info=True)
        # Consider handling specific AMQP errors (e.g., channel closed)
        return False


@log_exceptions
def process_message(llm_client, mq_channel: Optional[pika.channel.Channel], agent_id: str, message_body: bytes):
    """
    Process a raw message body, generate a response using the LLM, and publish it.

    Args:
        llm_client: The initialized LLM client instance.
        mq_channel: The Pika channel for publishing the response.
        agent_id: The ID of the agent processing the message.
        message_body: The raw bytes of the incoming message.

    Returns:
        The dictionary representing the response message, or None if processing failed.
    """
    try:
        message = json.loads(message_body.decode('utf-8'))
        logger.info(f"Processing message ID: {message.get('message_id', 'N/A')}")
    except json.JSONDecodeError:
        logger.error(f"Failed to decode message JSON: {message_body!r}", exc_info=True)
        return None # Cannot process invalid JSON
    except UnicodeDecodeError:
        logger.error(f"Failed to decode message body as UTF-8: {message_body!r}", exc_info=True)
        return None # Cannot process non-UTF-8

    prompt = message.get("text_payload", "")
    if not prompt:
        logger.warning(f"Received message {message.get('message_id', 'N/A')} with empty text_payload.")
        # Decide if an error response should be sent or just skip
        # For now, let's generate a default response
        llm_response_text = "Received empty message."
    else:
        llm_response_text = llm_client.generate_response(prompt)

    response_message = {
        "message_id": f"msg_{uuid.uuid4()}",
        "sender_id": agent_id,
        "message_type": message.get("message_type", "response"), # Default to 'response'
        "text_payload": llm_response_text,
        "original_message_id": message.get("message_id", "unknown"),
        "routing_status": "pending"
    }

    # Publish response using the provided MQ channel
    if mq_channel:
        if not publish_to_broker_input_queue(mq_channel, response_message):
            logger.error(f"Failed to publish response for original message {message.get('message_id', 'N/A')}")
            # Consider retry logic or alternative error handling
    else:
        logger.warning("MQ channel not provided, cannot publish response.")

    return response_message

