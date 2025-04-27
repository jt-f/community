import pika
import json
from shared_models import setup_logging
import uuid

logger = setup_logging(__name__)

#logger.propagate = False # Prevent messages reaching the root logger

def publish_to_broker_input_queue(rabbitmq_channel, message_dict):
    """Publish a pre-formatted response message dictionary to the broker input queue."""
    if not rabbitmq_channel:
        logger.error("Cannot publish: RabbitMQ connection not established")
        return False
    try:
        # routing_status and other fields are assumed to be set by the caller (Agent.generate_response)
        rabbitmq_channel.queue_declare(queue="broker_input_queue", durable=True)
        rabbitmq_channel.basic_publish(
            exchange='',
            routing_key="broker_input_queue",
            body=json.dumps(message_dict), # Serialize the dictionary
            properties=pika.BasicProperties(delivery_mode=2)
        )
        logger.info(f"Published response message {message_dict.get('message_id', 'N/A')} to broker_input_queue")
        return True
    except TypeError as e: # Catch potential JSON serialization errors
        logger.error(f"Failed to serialize message for publishing: {e} - Message: {message_dict}")
        return False
    except Exception as e:
        logger.error(f"Failed to publish to broker_input_queue: {e}")
        return False

def process_message_dict(agent, message_dict):
    """
    Process a message dict (not raw RabbitMQ body) for the agent. This allows direct invocation from agent code.
    """
    logger.info(f"Processing message dict: {message_dict}")
    message_type = message_dict.get("message_type", "unknown")
    message_id = message_dict.get("message_id", "unknown")
    sender_id = message_dict.get("sender_id", "unknown")
    logger.info(f"Received message type={message_type}, id={message_id} from {sender_id} (direct call)")
    # No artificial delay here; only in RabbitMQ handler
    response = agent.generate_response(message_dict)
    logger.info(f"Generated response: {response}")
    #logger.info(f"Generated response: {response.get('text_payload','ERROR: NO TEXT PAYLOAD')}")
    # If agent has a rabbitmq_channel, publish response (optional)
    if hasattr(agent, 'rabbitmq_channel') and agent.rabbitmq_channel:
        publish_to_broker_input_queue(agent.rabbitmq_channel, response)
    return response

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
        
        # Agent.generate_response now handles LLM call AND publishing the response
        response_dict = agent.generate_response(message_dict) 
        
        # Check if response generation and publishing was successful (though publish has its own logs)
        if response_dict:
            logger.info(f"Successfully processed and initiated publishing for message {message_id}. Response ID: {response_dict.get('message_id', 'N/A')}")
            # Acknowledge the message as processed
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # If generate_response failed internally (e.g., LLM error, though that should return error text)
            # or potentially if publishing failed silently (unlikely with current logging)
            logger.error(f"Failed to process or publish response for message {message_id}. Nacking message.")
            # Nack without requeue if processing failed fundamentally
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) 
            
        # Removed the explicit publish call here as it's now inside agent.generate_response
        # Removed the basic_ack logic duplication

    except json.JSONDecodeError:
        logger.error("Received invalid JSON in queue message")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.error(f"Error processing queue message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)