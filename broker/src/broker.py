import pika
import json
import logging
import time
import os
import sys
import threading
import uuid

# Adjust import path for running as a script/module
# This assumes you run the broker from the workspace root like: python -m server.broker.broker
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.append(PROJECT_ROOT)

# Import shared models directly - they will always be available
from shared_models import ChatMessage, MessageType, ResponseStatus

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
INCOMING_QUEUE = 'incoming_messages_queue'
BROKER_CONTROL_QUEUE = 'broker_control_queue'  # Queue for control messages (registrations, etc.)

# Dictionary to track registered agents and their queues
registered_agents = {}
# Dictionary to track client websocket IDs for message routing
client_connections = {}

# Placeholder for LLM-based agent routing
def get_target_agent_queue(message_data) -> str:
    """Determines the target agent queue based on message content."""
    log.debug(f"Determining route for message")
    
    # If message has a specific receiver_id that's a registered agent, use that
    receiver_id = message_data.get('receiver_id')
    if receiver_id in registered_agents:
        return registered_agents[receiver_id]['queue']
    
    # Otherwise use content-based routing
    content = message_data.get('text_payload', '').lower()
    if "weather" in content:
        queue = "weather_agent_queue"
    elif "translate" in content:
        queue = "translation_agent_queue"
    else:
        queue = "general_agent_queue"
    log.debug(f"Target queue: {queue}")
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

def publish_to_queue(channel, queue_name, message_data):
    """Publishes a message to the specified queue."""
    try:
        channel.queue_declare(queue=queue_name, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        log.info(f"Message successfully published to {queue_name}.")
        return True
    except Exception as e:
        log.error(f"Error publishing message to {queue_name}: {e}", exc_info=True)
        return False

def publish_response_to_server(channel, response_data):
    """Publishes a response back to the server for client forwarding."""
    try:
        server_response_queue = "server_response_queue"
        channel.queue_declare(queue=server_response_queue, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=server_response_queue,
            body=json.dumps(response_data),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        log.info(f"Response sent back to server.")
        return True
    except Exception as e:
        log.error(f"Error sending response to server: {e}", exc_info=True)
        return False

def handle_agent_registration(channel, message_data):
    """Processes agent registration request."""
    agent_id = message_data.get("agent_id")
    agent_name = message_data.get("agent_name")
    client_id = message_data.get("_client_id")  # Sent by server to identify originating connection
    
    log.info(f"Processing registration for agent {agent_name} (ID: {agent_id}) from client {client_id}")
    
    # Default values for response
    status = ResponseStatus.ERROR
    response_message = "Unknown error during registration"
    
    # Create an agent queue
    queue_name = f"agent_queue_{agent_id}"
    try:
        # Declare a durable queue for the agent
        channel.queue_declare(queue=queue_name, durable=True)
        log.info(f"Created queue {queue_name} for agent {agent_id}")
        
        # Register the agent
        registered_agents[agent_id] = {
            'name': agent_name,
            'queue': queue_name,
            'client_id': client_id
        }
        
        # Add client mapping
        if client_id:
            client_connections[client_id] = agent_id
        
        # Set success status
        status = ResponseStatus.SUCCESS
        response_message = "Agent registered successfully"
        log.info(f"Agent {agent_id} registered successfully")
        
    except Exception as e:
        log.error(f"Failed to create queue for agent {agent_id}: {e}")
        response_message = f"Failed to register agent: {str(e)}"
    
    # Create response message
    response = {
        "message_type": MessageType.REGISTER_AGENT_RESPONSE,
        "status": status,
        "agent_id": agent_id,
        "message": response_message,
        "client_id": client_id  # Include client_id so server knows where to route
    }
    
    # Send response back to server
    publish_response_to_server(channel, response)

def handle_client_disconnected(channel, message_data):
    """Handles client disconnection notification."""
    client_id = message_data.get("client_id")
    log.info(f"Client disconnected: {client_id}")
    
    # Check if this client was associated with an agent
    if client_id in client_connections:
        agent_id = client_connections[client_id]
        if agent_id in registered_agents:
            log.info(f"Unregistering agent {agent_id} due to client disconnection")
            del registered_agents[agent_id]
        del client_connections[client_id]

def process_control_message(ch, method, properties, body):
    """Processes control messages such as agent registration."""
    log.info(f"Received control message. Delivery tag: {method.delivery_tag}")
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        
        if message_type == MessageType.REGISTER_AGENT:
            handle_agent_registration(ch, message_data)
        elif message_type == MessageType.CLIENT_DISCONNECTED:
            handle_client_disconnected(ch, message_data)
        else:
            log.warning(f"Unhandled control message type: {message_type}")
        
        # Acknowledge the message was processed
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except json.JSONDecodeError:
        log.error(f"Invalid JSON received in control queue: {body}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        log.error(f"Error processing control message: {e}", exc_info=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def message_callback(ch, method, properties, body):
    """Callback function executed when a message is received from INCOMING_QUEUE."""
    log.info(f"Received message from {INCOMING_QUEUE}. Delivery tag: {method.delivery_tag}")
    try:
        message_data = json.loads(body)
        log.debug(f"Processing message from incoming queue")

        target_queue = get_target_agent_queue(message_data)

        # Re-publish to the target agent queue
        publish_to_queue(ch, target_queue, message_data)

        # Acknowledge the message was processed successfully
        ch.basic_ack(delivery_tag=method.delivery_tag)
        log.debug(f"Acknowledged message from incoming queue")

    except json.JSONDecodeError:
        log.error(f"Invalid JSON received in incoming queue: {body}")
        # Decide how to handle poison messages (e.g., move to dead-letter queue or discard)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Discarding for now
    except Exception as e:
        log.error(f"Error processing message {properties.message_id if properties else 'Unknown'}: {e}", exc_info=True)
        # Negative acknowledge, potentially requeue depending on error type
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Requeue=False to avoid infinite loops for persistent errors

def start_control_consumer():
    """Starts a separate thread to consume control messages."""
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    
    # Declare the control queue
    channel.queue_declare(queue=BROKER_CONTROL_QUEUE, durable=True)
    log.info(f"Broker listening for control messages on {BROKER_CONTROL_QUEUE}")
    
    # Ensure fair dispatch
    channel.basic_qos(prefetch_count=1)
    
    # Set up consuming
    channel.basic_consume(queue=BROKER_CONTROL_QUEUE, on_message_callback=process_control_message)
    
    try:
        channel.start_consuming()
    except Exception as e:
        log.error(f"Control consumer encountered an error: {e}", exc_info=True)
    finally:
        if channel.is_open:
            channel.close()
        if connection.is_open:
            connection.close()

def start_message_consumer():
    """Starts consuming regular messages from the incoming queue."""
    connection = get_rabbitmq_connection()
    channel = connection.channel()

    channel.queue_declare(queue=INCOMING_QUEUE, durable=True)
    log.info(f"Broker waiting for messages on {INCOMING_QUEUE}")

    # Ensure fair dispatch (only fetch 1 message at a time per consumer)
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(queue=INCOMING_QUEUE, on_message_callback=message_callback)

    try:
        channel.start_consuming()
    except Exception as e:
        log.error(f"Message consumer encountered an error: {e}", exc_info=True)
    finally:
        if channel.is_open:
            channel.close()
        if connection.is_open:
            connection.close()

def start_consuming():
    """Starts both control and message consumers in separate threads."""
    # Create the server response queue
    connection = get_rabbitmq_connection()
    if connection:
        try:
            channel = connection.channel()
            channel.queue_declare(queue="server_response_queue", durable=True)
            log.info("Server response queue created")
        except Exception as e:
            log.error(f"Error creating server response queue: {e}")
        finally:
            if connection.is_open:
                connection.close()
    
    # Start control consumer in a separate thread
    control_thread = threading.Thread(target=start_control_consumer)
    control_thread.daemon = True
    control_thread.start()
    log.info("Control message consumer thread started")
    
    # Start message consumer in the main thread
    try:
        log.info("Starting message consumer in main thread")
        start_message_consumer()
    except KeyboardInterrupt:
        log.info("Broker shutting down...")
    except Exception as e:
        log.error(f"Broker encountered an error: {e}", exc_info=True)
    finally:
        log.info("Broker shutdown complete")

if __name__ == '__main__':
    start_consuming() 