import pika
import json
import logging
import uuid

logger = logging.getLogger(__name__)

def publish_to_broker_input_queue(rabbitmq_channel, message_data):
    """Publish a response message to the broker input queue."""
    if not rabbitmq_channel:
        logger.error("Cannot publish: RabbitMQ connection not established")
        return False
    try:
        message_data["routing_status"] = "pending"
        rabbitmq_channel.queue_declare(queue="broker_input_queue", durable=True)
        rabbitmq_channel.basic_publish(
            exchange='',
            routing_key="broker_input_queue",
            body=json.dumps(message_data),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        logger.info(f"Published response message {message_data.get('message_id', 'N/A')} to broker_input_queue")
        return True
    except Exception as e:
        logger.error(f"Failed to publish to broker_input_queue: {e}")
        return False

def process_rabbitmq_message(agent, ch, method, properties, body):
    """Process a message received from RabbitMQ queue."""
    try:
        message_dict = json.loads(body)
        logger.info(f"Received message: {message_dict}")
        message_type = message_dict.get("message_type", "unknown")
        message_id = message_dict.get("message_id", "unknown")
        sender_id = message_dict.get("sender_id", "unknown")
        logger.info(f"Received message type={message_type}, id={message_id} from {sender_id} via queue")
        
        delay = 5
        logger.info(f"Waiting {delay} seconds before processing...")
        import time
        time.sleep(delay)
        logger.info("Finished waiting, proceeding with processing.")
        response = agent.generate_response(message_dict)
        logger.info(f"Generated response: {response.get('text_payload','ERROR: NO TEXT PAYLOAD')}")
        if publish_to_broker_input_queue(agent.rabbitmq_channel, response):
            logger.info(f"Sent response {response.get('message_id','ERROR: NO MESSAGE ID')} to message {message_id} to broker_input_queue")
        else:
            logger.error(f"Failed to send response to message {message_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        logger.error("Received invalid JSON in queue message")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.error(f"Error processing queue message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)