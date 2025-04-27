import pika
import json
from shared_models import setup_logging
import uuid
from decorators import log_exceptions

logger = setup_logging(__name__)


@log_exceptions
def publish_to_broker_input_queue(rabbitmq_channel, message_dict):
    """Publish a pre-formatted response message dictionary to the broker input queue."""
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
def process_message_dict(agent, message_dict):
    """
    Process a message dict (not raw RabbitMQ body) for the agent. This allows direct invocation from agent code.
    """
    logger.info(f"Processing message dict: {message_dict}")
    message_type = message_dict.get("message_type", "unknown")
    message_id = message_dict.get("message_id", "unknown")
    sender_id = message_dict.get("sender_id", "unknown")
    logger.info(f"Received message type={message_type}, id={message_id} from {sender_id} (direct call)")
    response = agent.generate_response(message_dict)
    logger.info(f"Generated response: {response}")
    if hasattr(agent, 'rabbitmq_channel') and agent.rabbitmq_channel:
        publish_to_broker_input_queue(agent.rabbitmq_channel, response)
    return response


@log_exceptions
def process_rabbitmq_message(agent, ch, method, properties, body):
    """Process a message received from RabbitMQ queue."""
    try:
        message_dict = json.loads(body)
        logger.info(f"Received message: {message_dict}")
        message_type = message_dict.get("message_type", "unknown")
        message_id = message_dict.get("message_id", "unknown")
        sender_id = message_dict.get("sender_id", "unknown")
        logger.info(f"Received message type={message_type}, id={message_id} from {sender_id} via queue")
        response_dict = agent.generate_response(message_dict)
        if response_dict:
            logger.info(f"Successfully processed and initiated publishing for message {message_id}. Response ID: {response_dict.get('message_id', 'N/A')}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            logger.error(f"Failed to process or publish response for message {message_id}. Nacking message.")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except json.JSONDecodeError:
        logger.error("Received invalid JSON in queue message")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.error(f"Error processing queue message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)