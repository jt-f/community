import logging
import threading
import json
import time
import pika
import os
import random
from datetime import datetime
from typing import Dict

# Import shared models directly
from shared_models import (
    MessageType,
    ResponseStatus
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Get a logger for this module
log = logging.getLogger("broker")

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
log.info("Pika library logging level set to WARNING.")

# RabbitMQ connection details - can be overridden with environment variables
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
BROKER_INPUT_QUEUE = "broker_input_queue"         # Messages from server (from frontends or agents)
AGENT_METADATA_QUEUE = "agent_metadata_queue"     # Agent registration and status
BROKER_OUTPUT_QUEUE = "broker_output_queue"       # Messages to server (to be routed to frontends or agents)
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"  # Server availability

# Dictionary to store registered agents - the only state the broker needs
registered_agents = {}  # agent_id -> agent info (capabilities, name, etc.)

def setup_rabbitmq_channel(queue_name, callback_function):
    """Set up a RabbitMQ channel and consumer."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        
        # Declare the queue, ensuring it exists
        channel.queue_declare(queue=queue_name, durable=True)
        
        # Set up the consumer
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=lambda ch, method, properties, body: callback_function(ch, method, properties, body),
            auto_ack=False
        )
        
        log.info(f"Connected to RabbitMQ and consuming from {queue_name}")
        return channel
    except Exception as e:
        log.error(f"Failed to set up RabbitMQ channel for {queue_name}: {e}")
        return None

def publish_to_broker_output_queue(message_data):
    """Publish a message to the broker's output queue (read by the server)."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        
        # Ensure the queue exists
        channel.queue_declare(queue=BROKER_OUTPUT_QUEUE, durable=True)
        
        # Publish the message
        channel.basic_publish(
            exchange='',
            routing_key=BROKER_OUTPUT_QUEUE,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        
        log.info(f"Published message to {BROKER_OUTPUT_QUEUE}")
        
        # Clean up
        connection.close()
        return True
    except Exception as e:
        log.error(f"Failed to publish to {BROKER_OUTPUT_QUEUE}: {e}")
        return False

def handle_incoming_message(channel, method, properties, body):
    """Handle incoming chat messages from the BROKER_INPUT_QUEUE."""
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        
        if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
            # Get sender and receiver IDs
            sender_id = message_data.get("sender_id", "unknown")
            
            log.info(f"Received message type {message_type} from {sender_id}")
            
            # Route message
            route_message(message_data)
            
            # Acknowledge the message was processed
            channel.basic_ack(delivery_tag=method.delivery_tag)
        else:
            log.warning(f"Received unsupported message type in broker input queue: {message_type}")
            # Acknowledge but skip processing
            channel.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        log.error(f"Invalid JSON in message: {body}")
        # Acknowledge but don't process invalid messages
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        log.error(f"Error processing incoming message: {e}")
        # Negative acknowledgment for failed processing
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def handle_control_message(channel, method, properties, body):
    """Handle control messages for the broker."""
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        
        # Process based on message type
        if message_type == MessageType.REGISTER_AGENT:
            handle_agent_registration(message_data)
        elif message_type == MessageType.CLIENT_DISCONNECTED:
            handle_client_disconnected(message_data)
        else:
            log.warning(f"Received unsupported control message type: {message_type}")
        
        # Acknowledge the message was processed
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        log.error(f"Invalid JSON in control message: {body}")
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        log.error(f"Error processing control message: {e}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def handle_agent_registration(message_data):
    """Handles agent registration requests."""
    agent_id = message_data.get("agent_id")
    agent_name = message_data.get("agent_name", "Unknown Agent")
    client_id = message_data.get("_client_id")
    
    if not agent_id:
        log.error("Agent registration failed: Missing agent_id")
        return
    
    # Store agent information - this is the only state we need to maintain
    registered_agents[agent_id] = {
        "name": agent_name,
        "capabilities": message_data.get("capabilities", []),
        "registration_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_online": True
    }
    
    log.info(f"Agent registered: {agent_name} (ID: {agent_id})")
    
    # Prepare registration response
    response = {
        "message_type": MessageType.REGISTER_AGENT_RESPONSE,
        "status": ResponseStatus.SUCCESS,
        "agent_id": agent_id,
        "message": "Agent registered successfully",
    }
    
    # Add client_id for routing back to the correct client (if provided)
    if client_id:
        response["_client_id"] = client_id
    
    # Send response back to the server via the broker output queue
    publish_to_broker_output_queue(response)

def handle_client_disconnected(message_data):
    """Handles client disconnection notification."""
    agent_id = message_data.get("agent_id")
    
    # If this is an agent disconnection and we know about this agent
    if agent_id and agent_id in registered_agents:
        log.info(f"Unregistering agent {agent_id} due to client disconnection")
        
        # Mark agent as offline but keep its registration
        registered_agents[agent_id]["is_online"] = False
        log.info(f"Agent {agent_id} marked as offline")

def handle_server_advertisement(channel, method, properties, body):
    """Handle server availability advertisement."""
    try:
        message_data = json.loads(body)
        if message_data.get("message_type") == MessageType.SERVER_AVAILABLE:
            log.info(f"Server available at {message_data.get('websocket_url')}")
    except Exception as e:
        log.error(f"Error handling server advertisement: {e}")
    finally:
        channel.basic_ack(delivery_tag=method.delivery_tag)

def route_message(message_data):
    """Route messages to the appropriate recipients.
    If receiver_id is 'broadcast' or not specified, randomly selects an online agent.
    Otherwise, attempts direct routing to the specified agent.
    
    All messages are published to BROKER_OUTPUT_QUEUE with appropriate receiver_id set.
    """
    message_type = message_data.get("message_type")
    sender_id = message_data.get("sender_id", "unknown")

    log.info(f"Routing message from {sender_id} type={message_type}")
    
    # Create a clean copy of the message for routing
    outgoing_message = dict(message_data)

    # Remove any routing metadata fields that might be present
    for field in ["_broadcast", "_target_agent_id", "_client_id"]:
        if field in outgoing_message:
            outgoing_message.pop(field)


    # Get list of online agents
    online_agents = [
        agent_id for agent_id, info in registered_agents.items()
        if info.get("is_online", False)
    ]

    if online_agents:
        # Randomly select an agent
        chosen_agent_id = random.choice(online_agents)
        
        # Set the receiver_id to the chosen agent
        outgoing_message["receiver_id"] = chosen_agent_id
        
        # Send the message
        publish_to_broker_output_queue(outgoing_message)
        log.info(f"Randomly routed message from {sender_id} to agent {chosen_agent_id}")
        return
    else:
        # No online agents available - generate error response
        error_response = {
            "message_type": MessageType.ERROR,
            "sender_id": "broker",
            "receiver_id":"server",
            "text_payload": "No online agents available to handle the request."
        }
        publish_to_broker_output_queue(error_response)
        log.warning(f"Could not route message from {sender_id}: No online agents found")
        return

def main():
    """Main function to start the broker service."""
    log.info("Starting message broker service")
    
    # Set up channels for incoming messages, control messages, and server advertisements
    incoming_channel = setup_rabbitmq_channel(BROKER_INPUT_QUEUE, handle_incoming_message)
    control_channel = setup_rabbitmq_channel(AGENT_METADATA_QUEUE, handle_control_message)
    advertisement_channel = setup_rabbitmq_channel(SERVER_ADVERTISEMENT_QUEUE, handle_server_advertisement)
    
    if not all([incoming_channel, control_channel, advertisement_channel]):
        log.error("Failed to set up RabbitMQ channels. Exiting.")
        return
    
    # Start consuming from RabbitMQ channels in threads
    threads = []
    for channel, name in [
        (incoming_channel, "incoming_channel"),
        (control_channel, "control_channel"),
        (advertisement_channel, "advertisement_channel")
    ]:
        thread = threading.Thread(target=channel.start_consuming, daemon=True)
        thread.start()
        threads.append((thread, name))
        log.info(f"Started consuming on {name}")
    
    log.info("Broker service is running. Press Ctrl+C to exit.")
    
    try:
        # Keep the main thread alive
        while True:
            # Check if all threads are still alive
            for thread, name in threads:
                if not thread.is_alive():
                    log.error(f"Thread for {name} died. Exiting.")
                    return
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Received interrupt. Shutting down broker service...")
        
        # Stop consuming and close channels
        if incoming_channel:
            incoming_channel.stop_consuming()
        if control_channel:
            control_channel.stop_consuming()
        if advertisement_channel:
            advertisement_channel.stop_consuming()
        
        log.info("Broker service shut down successfully")
    except Exception as e:
        log.error(f"Unexpected error in broker service: {e}")

if __name__ == "__main__":
    main() 