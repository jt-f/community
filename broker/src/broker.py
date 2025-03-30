import pika
import json
import logging
import time
import os
import sys

# Adjust import path for running as a script/module
# This assumes you run the broker from the workspace root like: python -m server.broker.broker
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.append(PROJECT_ROOT)

from shared_models import ChatMessage, MessageType

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
INCOMING_QUEUE = 'incoming_messages_queue'

# Placeholder for LLM-based agent routing
def get_target_agent_queue(message: ChatMessage) -> str:
    """Simulates LLM determining the target agent queue based on message content."""
    log.debug(f"Determining route for message: {message.message_id}")
    content = message.text_payload.lower()
    if "weather" in content:
        queue = "weather_agent_queue"
    elif "translate" in content:
        queue = "translation_agent_queue"
    else:
        queue = "general_agent_queue"
    log.debug(f"Target queue for {message.message_id}: {queue}")
    return queue

def get_rabbitmq_connection(retries=5, delay=5):
    """Establishes a connection to RabbitMQ with retry logic."""
    credentials = pika.PlainCredentials('guest', 'guest')
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, RABBITMQ_PORT, '/', credentials)
    attempt = 0
    while attempt < retries:
        attempt += 1
        try:
            connection = pika.BlockingConnection(parameters)
            log.info(f"Broker successfully connected to RabbitMQ on attempt {attempt}.")
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            log.warning(f"Broker failed to connect to RabbitMQ: {e}. Retrying in {delay} seconds... ({attempt}/{retries})")
            time.sleep(delay)
    log.error("Broker could not connect to RabbitMQ after multiple retries. Exiting.")
    sys.exit(1) # Exit if connection fails permanently

def publish_to_agent_queue(channel, message: ChatMessage, target_queue: str):
    """Publishes a message to the specified agent queue."""
    try:
        channel.queue_declare(queue=target_queue, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=target_queue,
            body=message.model_dump_json(),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        log.info(f"Message {message.message_id} successfully re-published to {target_queue}.")
    except Exception as e:
        log.error(f"Error publishing message {message.message_id} to {target_queue}: {e}", exc_info=True)

def message_callback(ch, method, properties, body):
    """Callback function executed when a message is received from INCOMING_QUEUE."""
    log.info(f"Received message from {INCOMING_QUEUE}. Delivery tag: {method.delivery_tag}")
    try:
        message_data = json.loads(body)
        incoming_message = ChatMessage(**message_data)
        log.debug(f"Processing message: {incoming_message.message_id}")

        target_queue = get_target_agent_queue(incoming_message)

        # Re-publish to the target agent queue
        publish_to_agent_queue(ch, incoming_message, target_queue)

        # Acknowledge the message was processed successfully
        ch.basic_ack(delivery_tag=method.delivery_tag)
        log.debug(f"Acknowledged message: {incoming_message.message_id}")

    except json.JSONDecodeError:
        log.error(f"Invalid JSON received in incoming queue: {body}")
        # Decide how to handle poison messages (e.g., move to dead-letter queue or discard)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Discarding for now
    except Exception as e:
        log.error(f"Error processing message {properties.message_id if properties else 'Unknown'}: {e}", exc_info=True)
        # Negative acknowledge, potentially requeue depending on error type
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Requeue=False to avoid infinite loops for persistent errors

def start_consuming():
    """Starts consuming messages from the incoming queue."""
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    channel.queue_declare(queue=INCOMING_QUEUE, durable=True)
    log.info(f"Broker waiting for messages on {INCOMING_QUEUE}. To exit press CTRL+C")

    # Ensure fair dispatch (only fetch 1 message at a time per consumer)
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(queue=INCOMING_QUEUE, on_message_callback=message_callback)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        log.info("Broker shutting down...")
    except Exception as e:
        log.error(f"Broker encountered an error: {e}", exc_info=True)
    finally:
        if channel.is_open:
            channel.close()
            log.info("RabbitMQ channel closed.")
        if connection.is_open:
            connection.close()
            log.info("RabbitMQ connection closed.")

if __name__ == '__main__':
    start_consuming() 