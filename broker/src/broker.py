import logging
import threading
import json
import time
import pika
import os
import asyncio
import websockets
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

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
log.info("Pika library logging level set to WARNING.")

# RabbitMQ connection details - can be overridden with environment variables
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
INCOMING_QUEUE = "incoming_messages_queue"
BROKER_CONTROL_QUEUE = "broker_control_queue"
SERVER_RESPONSE_QUEUE = "server_response_queue"
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# Server WebSocket connection details
SERVER_WS_URL = os.getenv('SERVER_WS_URL', 'ws://localhost:8765/ws')
RECONNECT_DELAY = 5  # seconds
MAX_RECONNECT_DELAY = 60  # seconds

# Dictionary to store registered agents - the only state the broker needs
registered_agents = {}  # agent_id -> agent info (capabilities, name, etc.)

# Global WebSocket connection to server
server_ws = None
server_ws_task = None
server_available = False  # Track server availability

# Add this near the top with other global variables
websocket_loop = None

def get_websocket_loop():
    """Get or create the WebSocket event loop."""
    global websocket_loop
    if websocket_loop is None:
        websocket_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(websocket_loop)
    return websocket_loop

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

    # Add WebSocket connection and message handling functions here

async def connect_to_server():
    """Establish WebSocket connection to the server."""
    global server_ws, server_ws_task
    
    try:
        server_ws = await websockets.connect(SERVER_WS_URL)
        log.info("Connected to server via WebSocket")
        
        # Register as broker
        register_message = {
            "message_type": MessageType.REGISTER_BROKER,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        await server_ws.send(json.dumps(register_message))
        
        # Start message handling task
        server_ws_task = asyncio.create_task(handle_server_messages())
        
    except Exception as e:
        log.error(f"Failed to connect to server: {e}")
        server_ws = None
        raise

async def handle_server_messages():
    """Handle messages from the server WebSocket connection."""
    global server_ws, server_available
    
    try:
        while True:
            message = await server_ws.recv()
            message_data = json.loads(message)
            message_type = message_data.get("message_type")
            
            if message_type == MessageType.AGENT_STATUS_UPDATE:
                # Update agent statuses
                agents = message_data.get("agents", [])
                log.info(f"Received agent status update with {len(agents)} agents")
                
                for agent in agents:
                    agent_id = agent.get("agent_id")
                    if agent_id:
                        if agent_id not in registered_agents:
                            registered_agents[agent_id] = {}
                            log.info(f"Adding new agent: {agent.get('agent_name')} (ID: {agent_id})")
                        
                        # Update agent info
                        registered_agents[agent_id].update({
                            "name": agent.get("agent_name", "Unknown Agent"),
                            "is_online": agent.get("is_online", False),
                            "last_seen": agent.get("last_seen"),
                            "capabilities": agent.get("capabilities", [])
                        })
                        log.info(f"Updated agent {agent.get('agent_name')} (ID: {agent_id}) - Online: {agent.get('is_online')}")
                
                # Log current state of all registered agents
                log.info(f"Current registered agents: {len(registered_agents)}")
                for agent_id, info in registered_agents.items():
                    log.info(f"Agent: {info['name']} (ID: {agent_id}) - Online: {info['is_online']}")
            else:
                log.warning(f"Received unknown message type from server: {message_type}")
                
    except websockets.exceptions.ConnectionClosed:
        log.warning("Server WebSocket connection closed")
        server_ws = None
        server_available = False  # Mark server as unavailable
        raise
    except Exception as e:
        log.error(f"Error handling server messages: {e}")
        server_ws = None
        server_available = False  # Mark server as unavailable
        raise

async def server_connection_manager():
    """Manage server WebSocket connection and reconnection."""
    global server_ws, server_ws_task, server_available
    
    while True:
        try:
            if not server_ws and server_available:
                await connect_to_server()
            elif server_ws:
                # Check if connection is still alive
                try:
                    await server_ws.ping()
                    await server_ws.pong()
                except:
                    log.warning("Server connection lost")
                    server_ws = None
                    if server_ws_task:
                        server_ws_task.cancel()
                        server_ws_task = None
                    server_available = False  # Mark server as unavailable
                
                await asyncio.sleep(1)  # Check connection every second
            else:
                # Server is not available, wait for advertisement
                await asyncio.sleep(1)
                
        except Exception as e:
            log.error(f"Error in server connection manager: {e}")
            server_ws = None
            if server_ws_task:
                server_ws_task.cancel()
                server_ws_task = None
            server_available = False  # Mark server as unavailable
            await asyncio.sleep(1)  # Wait before checking again

def handle_server_advertisement(channel, method, properties, body):
    """Handle server availability advertisement."""
    try:
        message_data = json.loads(body)
        if message_data.get("message_type") == MessageType.SERVER_AVAILABLE:
            global server_available
            server_available = True
            log.info(f"Server available at {message_data.get('websocket_url')}")
            # No need to store the URL as it's configured via environment variable
    except Exception as e:
        log.error(f"Error handling server advertisement: {e}")
    finally:
        channel.basic_ack(delivery_tag=method.delivery_tag)

def route_message(message_data):
    """Route messages to the appropriate recipients based on sender and receiver.
    Server will handle the client connection mapping."""
    message_type = message_data.get("message_type")
    sender_id = message_data.get("sender_id", "unknown")
    receiver_id = message_data.get("receiver_id", "broadcast")
    
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
    
    # Set up channels for incoming messages, control messages, and server advertisements
    incoming_channel = setup_rabbitmq_channel(INCOMING_QUEUE, handle_incoming_message)
    control_channel = setup_rabbitmq_channel(BROKER_CONTROL_QUEUE, handle_control_message)
    advertisement_channel = setup_rabbitmq_channel(SERVER_ADVERTISEMENT_QUEUE, handle_server_advertisement)
    
    if not all([incoming_channel, control_channel, advertisement_channel]):
        log.error("Failed to set up RabbitMQ channels. Exiting.")
        return
    
    # Create event loop for async operations
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Start the server connection manager
        server_manager_task = loop.create_task(server_connection_manager())
        
        # Start consuming from RabbitMQ channels
        threading.Thread(target=incoming_channel.start_consuming, daemon=True).start()
        threading.Thread(target=control_channel.start_consuming, daemon=True).start()
        threading.Thread(target=advertisement_channel.start_consuming, daemon=True).start()
        
        log.info("Broker service is running. Press Ctrl+C to exit.")
        
        # Run the event loop
        loop.run_forever()
        
    except KeyboardInterrupt:
        log.info("Received interrupt. Shutting down broker service...")
        
        # Cancel server connection manager
        if server_manager_task:
            server_manager_task.cancel()
        
        # Stop consuming and close channels
        if incoming_channel:
            incoming_channel.stop_consuming()
        if control_channel:
            control_channel.stop_consuming()
        if advertisement_channel:
            advertisement_channel.stop_consuming()
        
        # Close WebSocket connection if open
        if server_ws:
            loop.run_until_complete(server_ws.close())
        
        # Close event loops
        loop.close()
        if websocket_loop:
            websocket_loop.close()
        
        log.info("Broker service shut down successfully")
    except Exception as e:
        log.error(f"Unexpected error in broker service: {e}")
        loop.close()
        if websocket_loop:
            websocket_loop.close()

if __name__ == "__main__":
    main() 