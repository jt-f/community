import logging
import threading
import json
import time
import pika
import os
from datetime import datetime
from typing import Dict, Set, List, Optional

# Import shared models directly
from shared_models import (
    MessageType,
    ResponseStatus,
    ChatMessage
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Get a logger for this module
log = logging.getLogger("broker")

# RabbitMQ connection details - can be overridden with environment variables
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
INCOMING_QUEUE = "incoming_messages_queue"
BROKER_CONTROL_QUEUE = "broker_control_queue"
SERVER_RESPONSE_QUEUE = "server_response_queue"

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

def publish_to_server_response_queue(message_data):
    """Publish a message to the server response queue."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        
        # Ensure the queue exists
        channel.queue_declare(queue=SERVER_RESPONSE_QUEUE, durable=True)
        
        # Publish the message
        channel.basic_publish(
            exchange='',
            routing_key=SERVER_RESPONSE_QUEUE,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        
        log.debug(f"Published message to {SERVER_RESPONSE_QUEUE}")
        
        # Clean up
        connection.close()
        return True
    except Exception as e:
        log.error(f"Failed to publish to {SERVER_RESPONSE_QUEUE}: {e}")
        return False

def handle_incoming_message(channel, method, properties, body):
    """Handle incoming chat messages."""
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        
        if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
            # Get sender and receiver IDs
            sender_id = message_data.get("sender_id", "unknown")
            receiver_id = message_data.get("receiver_id", "broadcast")
            
            log.info(f"Received message type {message_type} from {sender_id} to {receiver_id}")
            
            # Update message routing with the simplified approach
            route_message(message_data)
            
            # Acknowledge the message was processed
            channel.basic_ack(delivery_tag=method.delivery_tag)
        else:
            log.warning(f"Received unsupported message type in incoming queue: {message_type}")
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
            handle_agent_registration(channel, message_data)
        elif message_type == MessageType.CLIENT_DISCONNECTED:
            handle_client_disconnected(channel, message_data)
        elif message_type == MessageType.AGENT_STATUS_UPDATE:
            handle_agent_status_update(channel, message_data)
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

def handle_agent_registration(channel, message_data):
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
    
    # Add client_id for routing back to the correct client
    if client_id:
        response["client_id"] = client_id
    
    # Send response back to the server
    publish_to_server_response_queue(response)

def handle_client_disconnected(channel, message_data):
    """Handles client disconnection notification."""
    agent_id = message_data.get("agent_id")
    
    # If this is an agent disconnection and we know about this agent
    if agent_id and agent_id in registered_agents:
        log.info(f"Unregistering agent {agent_id} due to client disconnection")
        
        # Mark agent as offline but keep its registration
        registered_agents[agent_id]["is_online"] = False
        log.info(f"Agent {agent_id} marked as offline")

def handle_agent_status_update(channel, message_data):
    """Handles agent status updates from the server."""
    agents = message_data.get("agents", [])
    
    log.info(f"Received status update for {len(agents)} agents")
    log.info(f"Agents: {message_data}")
    # Update our registry with online/offline status
    for agent in agents:
        agent_id = agent.get("agent_id")
        is_online = agent.get("is_online", False)
        
        if agent_id:
            # If we know about this agent, update its status
            if agent_id in registered_agents:
                registered_agents[agent_id]["is_online"] = is_online
                log.debug(f"Updated agent {agent_id} status: online={is_online}")
            # Otherwise, create a minimal entry for it
            else:
                registered_agents[agent_id] = {
                    "name": agent.get("agent_name", "Unknown Agent"),
                    "is_online": is_online,
                    "registration_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "capabilities": []
                }
                log.debug(f"Added new agent {agent_id} from status update")

def request_agent_status_sync():
    """Request a full agent status update from the server."""
    request = {
        "message_type": MessageType.REQUEST_AGENT_STATUS
    }
    publish_to_server_response_queue(request)
    log.info("Requested full agent status update from server")

def route_message(message_data):
    """Route messages to the appropriate recipients based on sender and receiver.
    Server will handle the client connection mapping."""
    message_type = message_data.get("message_type")
    sender_id = message_data.get("sender_id", "unknown")
    receiver_id = message_data.get("receiver_id", "broadcast")
    
    # Request the latest agent status before routing
    request_agent_status_sync()
    
    # Prepare the message for routing
    outgoing_message = dict(message_data)
    
    # For broadcast messages, add a flag for the server to broadcast
    if receiver_id == "broadcast":
        outgoing_message["_broadcast"] = True
        publish_to_server_response_queue(outgoing_message)
        log.info(f"Sent broadcast message from {sender_id} to server for distribution")
        return
        
    # For direct messages to specific agents, check if we know the agent
    if receiver_id in registered_agents:
        # Check if the agent is online
        if registered_agents[receiver_id]["is_online"]:
            # Add routing info for the server
            outgoing_message["_target_agent_id"] = receiver_id
            publish_to_server_response_queue(outgoing_message)
            log.info(f"Routed message from {sender_id} to agent {receiver_id}")
        else:
            # Agent is offline, send an error message back
            error_response = {
                "message_type": MessageType.ERROR,
                "sender_id": "broker",
                "receiver_id": sender_id,
                "text_payload": f"Agent {receiver_id} is currently offline",
                "_client_id": message_data.get("_client_id")  # Route back to original sender
            }
            publish_to_server_response_queue(error_response)
            log.warning(f"Cannot route message to offline agent {receiver_id}")
    else:
        # Unknown agent, send an error message back
        error_response = {
            "message_type": MessageType.ERROR,
            "sender_id": "broker",
            "receiver_id": sender_id,
            "text_payload": f"Unknown agent ID: {receiver_id}",
            "_client_id": message_data.get("_client_id")  # Route back to original sender
        }
        publish_to_server_response_queue(error_response)
        log.warning(f"Cannot route message to unknown agent {receiver_id}")

def main():
    """Main function to start the broker service."""
    log.info("Starting message broker service")
    
    # Initial request for agent status on startup
    request_agent_status_sync()
    
    # Set up channels for incoming messages and control messages
    incoming_channel = setup_rabbitmq_channel(INCOMING_QUEUE, handle_incoming_message)
    control_channel = setup_rabbitmq_channel(BROKER_CONTROL_QUEUE, handle_control_message)
    
    if not incoming_channel or not control_channel:
        log.error("Failed to set up RabbitMQ channels. Exiting.")
        return
    
    # Set up periodic status sync
    def periodic_status_sync():
        while True:
            try:
                request_agent_status_sync()
                time.sleep(30)  # Sync every 30 seconds
            except Exception as e:
                log.error(f"Error in periodic status sync: {e}")
                time.sleep(5)  # Wait a bit before retrying
    
    # Start the periodic sync in a background thread
    sync_thread = threading.Thread(target=periodic_status_sync, daemon=True)
    sync_thread.start()
    
    try:
        log.info("Broker service is running. Press Ctrl+C to exit.")
        
        # Start consuming from both channels
        threading.Thread(target=incoming_channel.start_consuming, daemon=True).start()
        control_channel.start_consuming()
    except KeyboardInterrupt:
        log.info("Received interrupt. Shutting down broker service...")
        
        # Stop consuming and close channels
        if incoming_channel:
            incoming_channel.stop_consuming()
        if control_channel:
            control_channel.stop_consuming()
            
        log.info("Broker service shut down successfully")
    except Exception as e:
        log.error(f"Unexpected error in broker service: {e}")

if __name__ == "__main__":
    main() 