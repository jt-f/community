"""Handles message processing, generation, and publishing for the agent."""
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
def process_message(llm_client, mq_channel, agent_id: str, message: Dict[str, Any] ):
    """
    Process a message, generate a response using the LLM, and publish it.
    """
    logger.info(f"Processing message: {message}")

    llm_response_text = llm_client.generate_response(message.get("text_payload", ""))

    response_message = {
        "message_id": f"msg_{uuid.uuid4()}",
        "sender_id": agent_id, # Use the passed agent_id
        "message_type": message.get("message_type", "unknown"), # Preserve original type or default
        "text_payload": llm_response_text,
        "original_message_id": message.get("message_id", "unknown"),
        "routing_status": "pending"
    }

    logger.info(f"Generated response: {response_message}")

    # Publish response using the provided MQ channel
    if mq_channel:
        publish_to_broker_input_queue(mq_channel, response_message)
    else:
        logger.warning("MQ channel not provided, cannot publish response.")

    return response_message


# Note: The process_rabbitmq_message function is less used now as the MessageQueueHandler
# directly calls the agent's handle_message, which then calls process_message_dict.
# Keeping it here for potential future use or reference, but commenting out the direct
# call to agent.generate_response as process_message_dict now handles generation and publishing.
# If this function were to be used directly as a pika callback again, it would need
# access to llm_client, mq_channel, and agent_id similar to process_message_dict.

# @log_exceptions
# def process_rabbitmq_message(agent, ch, method, properties, body):
#     """Process a message received from RabbitMQ queue."""
#     try:
#         message_dict = json.loads(body)
#         logger.info(f"Received message: {message_dict}")
#         message_type = message_dict.get("message_type", "unknown")
#         message_id = message_dict.get("message_id", "unknown")
#         sender_id = message_dict.get("sender_id", "unknown")
#         logger.info(f"Received message type={message_type}, id={message_id} from {sender_id} via queue")
#
#         # *** Decoupling Change: Instead of agent.generate_response, call process_message_dict ***
#         # This requires llm_client and agent_id to be available here.
#         # response_dict = agent.generate_response(message_dict)
#
#         # Placeholder: Assume process_message_dict is called elsewhere or dependencies are passed
#         # For now, just acknowledge if JSON is valid.
#         # response_dict = process_message_dict(llm_client, ch, agent_id, message_dict) # Example call
#
#         # Simplified logic for demonstration if this callback were used:
#         logger.info(f"Message {message_id} received, processing delegated.")
#         ch.basic_ack(delivery_tag=method.delivery_tag)
#
#     except json.JSONDecodeError:
#         logger.error("Received invalid JSON in queue message")
#         ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
#     except Exception as e:
#         logger.error(f"Error processing queue message: {e}")
#         ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)