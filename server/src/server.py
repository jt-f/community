import asyncio
import logging
import json
import os
import asyncio
import pika
import time   # Added for retry logic
import threading
import uuid
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Set, List, Optional

# Import shared models directly - they will always be available
from shared_models import (
    ChatMessage,
    MessageType,
    ResponseStatus,
    AgentRegistrationMessage,
    AgentRegistrationResponse,
    AgentStatus,
    AgentStatusUpdate
)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
INCOMING_QUEUE = "incoming_messages_queue"
BROKER_CONTROL_QUEUE = "broker_control_queue"
SERVER_RESPONSE_QUEUE = "server_response_queue"

# Configure CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active websocket connections
active_connections = set()  # All active websocket connections
agent_connections = {}  # Dictionary to track agent websocket connections: agent_id -> websocket
frontend_connections = set()  # Set to track frontend connections
broker_connection = None  # Single broker WebSocket connection

# Dictionary to track agent status
agent_statuses = {}  # agent_id -> AgentStatus object
agent_status_history = {}  # agent_id -> previous AgentStatus object for change detection

# Server advertisement settings
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# Global variable for tracking the RabbitMQ connection
rabbitmq_connection = None

def get_rabbitmq_connection():
    global rabbitmq_connection
    try:
        rabbitmq_connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        return rabbitmq_connection
    except Exception as e:
        logging.error(f"Failed to connect to RabbitMQ: {e}")
        return None

def publish_to_queue(queue_name, message_data):
    """Publish a message to a RabbitMQ queue."""
    global rabbitmq_connection
    channel = None
    
    try:
        # Get or reuse the existing connection
        if not rabbitmq_connection or not rabbitmq_connection.is_open:
            connection = get_rabbitmq_connection()
            if not connection:
                logging.error(f"Failed to establish RabbitMQ connection for publishing to {queue_name}")
                return False
        
        # Create a new channel for this publish operation
        channel = rabbitmq_connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        
        logging.info(f"Message published to {queue_name}")
        
        # Close only the channel, keep the connection open
        if channel and channel.is_open:
            channel.close()
            
        return True
    except Exception as e:
        logging.error(f"Error publishing to queue {queue_name}: {e}")
        return False
    finally:
        # Ensure channel is closed if an exception occurs
        if channel and channel.is_open:
            try:
                channel.close()
            except:
                pass

def publish_to_incoming_queue(message_data):
    """Publish a message to the incoming messages queue."""
    return publish_to_queue(INCOMING_QUEUE, message_data)

def publish_to_broker_control_queue(message_data):
    """Publish a control message to the broker control queue."""
    return publish_to_queue(BROKER_CONTROL_QUEUE, message_data)

async def response_consumer():
    """Consumer that listens for responses from the broker to send back to clients."""
    global rabbitmq_connection
    channel = None
    
    try:
        while True:
            try:
                if not rabbitmq_connection or not rabbitmq_connection.is_open:
                    connection = get_rabbitmq_connection()
                    if not connection:
                        logging.error("Failed to connect to RabbitMQ for response consumer. Retrying...")
                        await asyncio.sleep(5)  # Wait before retrying
                        continue
                
                channel = rabbitmq_connection.channel()
                channel.queue_declare(queue=SERVER_RESPONSE_QUEUE, durable=True)
                
                logging.info(f"Started listening on {SERVER_RESPONSE_QUEUE} for broker responses")
                
                # Set up consumer with callback that handles async
                def callback(ch, method, properties, body):
                    # Run the async process_message in the event loop
                    asyncio.create_task(process_message(ch, method, properties, body))
                
                channel.basic_consume(queue=SERVER_RESPONSE_QUEUE, on_message_callback=callback)
                
                # Keep the connection open and consuming
                logging.info("Response consumer is now listening for messages from broker")
                
                # This approach keeps the connection open but allows the asyncio event loop to continue
                while rabbitmq_connection and rabbitmq_connection.is_open:
                    # Process events but don't block the event loop
                    rabbitmq_connection.process_data_events(time_limit=0.1)
                    await asyncio.sleep(0.1)
                    
                logging.warning("RabbitMQ connection closed or lost, reconnecting...")
                
            except Exception as e:
                logging.error(f"Error in response consumer: {e}")
                
                # Close channel and connection if they're still open
                if channel and channel.is_open:
                    try:
                        channel.close()
                    except:
                        pass
                
                # Wait before retrying
                await asyncio.sleep(5)
                
    except asyncio.CancelledError:
        logging.info("Response consumer task cancelled")
        # Clean up if task is cancelled
        if channel and channel.is_open:
            try:
                channel.close()
            except:
                pass
        raise

async def agent_ping_service():
    """Service to send periodic ping messages to agents and update their status."""
    try:
        while True:
            current_time = datetime.now()
            
            # Copy the agent connections dictionary to avoid modification during iteration
            agent_connections_copy = dict(agent_connections)
            
            # Send ping to all connected agents
            for agent_id, ws in agent_connections_copy.items():
                try:
                    # Send ping message
                    ping_message = {
                        "message_type": MessageType.PING,
                        "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    await ws.send_text(json.dumps(ping_message))
                    logging.info(f"Sent ping to agent {agent_id}")
                except Exception as e:
                    logging.error(f"Error sending ping to agent {agent_id}: {e}")
                    
            # Check for agents that haven't responded in a while
            for agent_id, status in list(agent_statuses.items()):
                try:
                    if agent_id in agent_statuses:
                        # Parse the last seen time
                        last_seen_str = status.last_seen
                        last_seen_time = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
                        
                        # If the agent hasn't been seen for more than 15 seconds, mark as offline
                        time_diff = (current_time - last_seen_time).total_seconds()
                        if time_diff > 15 and status.is_online:
                            logging.info(f"Agent {status.agent_name} (ID: {agent_id}) marked as offline due to inactivity")
                            status.is_online = False
                            
                            # Broadcast updated agent status
                            await broadcast_agent_status()
                except Exception as e:
                    logging.error(f"Error checking agent {agent_id} status: {e}")
                    
            # Broadcast current agent status to all frontend clients
            await broadcast_agent_status()
            
            # Wait before next ping cycle
            await asyncio.sleep(10)  # Send pings every 10 seconds
            
    except asyncio.CancelledError:
        logging.info("Agent ping service task cancelled")
        raise
    except Exception as e:
        logging.error(f"Error in agent ping service: {e}")

def has_agent_status_changed(agent_id: str, new_status: AgentStatus) -> bool:
    """Check if an agent's status has changed from its previous state."""
    if agent_id not in agent_status_history:
        return True  # First time seeing this agent
    
    old_status = agent_status_history[agent_id]
    return (old_status.is_online != new_status.is_online or 
            old_status.last_seen != new_status.last_seen)

async def advertise_server():
    """Publish server availability to RabbitMQ."""
    try:
        advertisement = {
            "message_type": MessageType.SERVER_AVAILABLE,
            "server_id": "server_1",  # Could be made configurable
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "websocket_url": "ws://localhost:8765/ws"  # Could be made configurable
        }
        publish_to_queue(SERVER_ADVERTISEMENT_QUEUE, advertisement)
        logging.info("Published server availability advertisement")
    except Exception as e:
        logging.error(f"Error advertising server: {e}")

async def broadcast_agent_status(force_full_update: bool = False):
    """Broadcast current agent status to all frontend clients and broker."""
    global broker_connection
    try:
        # Create status update message with all agents if force_full_update is True
        if force_full_update:
            status_update = AgentStatusUpdate(
                agents=list(agent_statuses.values())
            )
        else:
            # Create status update message with only changed agents
            changed_agents = []
            for agent_id, status in agent_statuses.items():
                if has_agent_status_changed(agent_id, status):
                    changed_agents.append(status)
                    # Update history
                    agent_status_history[agent_id] = AgentStatus(
                        agent_id=status.agent_id,
                        agent_name=status.agent_name,
                        is_online=status.is_online,
                        last_seen=status.last_seen
                    )
            
            if changed_agents:
                status_update = AgentStatusUpdate(
                    agents=changed_agents
                )
            else:
                return  # No changes to broadcast
        
        # Send to broker first if connected
        if broker_connection:
            try:
                await broker_connection.send_text(json.dumps(status_update.model_dump()))
            except Exception as e:
                logging.error(f"Error sending status update to broker: {e}")
                broker_connection = None
        
        # Then broadcast to all frontend clients
        for ws in frontend_connections:
            try:
                await ws.send_text(json.dumps(status_update.model_dump()))
            except Exception as e:
                logging.error(f"Error sending status update to frontend client: {e}")
                
        logging.info(f"Broadcast agent status update to broker and {len(frontend_connections)} frontend clients with {len(status_update.agents)} agents")
    except Exception as e:
        logging.error(f"Error broadcasting agent status: {e}")

async def periodic_status_broadcast():
    """Service to periodically broadcast full agent status to frontend clients."""
    try:
        while True:
            # Broadcast full agent status every minute
            await broadcast_agent_status(force_full_update=True)
            await asyncio.sleep(60)  # Wait 60 seconds before next broadcast
            
    except asyncio.CancelledError:
        logging.info("Periodic status broadcast service task cancelled")
        raise
    except Exception as e:
        logging.error(f"Error in periodic status broadcast service: {e}")

async def send_agent_status_to_broker():
    """Send current agent status to the broker."""
    try:
        # Prepare agent status message with only currently registered agents
        status_list = []
        for agent_id, status in agent_statuses.items():
            # Only include agents that are currently registered
            if agent_id in agent_connections:
                status_list.append({
                    "agent_id": agent_id,
                    "agent_name": status.agent_name,
                    "is_online": status.is_online,
                    "last_seen": status.last_seen
                })
        
        status_data = {
            "message_type": MessageType.AGENT_STATUS_UPDATE,
            "agents": status_list,
            "is_full_update": True  # Indicate this is a full update
        }
        
        # Send to broker
        publish_to_broker_control_queue(status_data)
        logging.info(f"Sent agent status update to broker with {len(status_list)} active agents")
    except Exception as e:
        logging.error(f"Error sending agent status to broker: {e}")

async def forward_response_to_client(response_data):
    """Forward a response from the broker to the appropriate WebSocket client."""
    try:
        # Handle broadcast flag for sending to all clients
        if response_data.get("_broadcast") == True:
            # Send to all frontend clients
            for ws in frontend_connections:
                try:
                    # Create a copy of the message without routing metadata
                    message_to_client = dict(response_data)
                    # Remove routing metadata
                    for key in ["_broadcast", "_target_agent_id", "_client_id"]:
                        if key in message_to_client:
                            del message_to_client[key]
                            
                    await ws.send_text(json.dumps(message_to_client))
                except Exception as e:
                    logging.error(f"Error sending broadcast to client: {e}")
            
            # Send to all agents except the sender
            sender_id = response_data.get("sender_id", "unknown")
            for agent_id, ws in agent_connections.items():
                if agent_id != sender_id:  # Don't send back to sender
                    try:
                        # Create a copy of the message without routing metadata
                        message_to_agent = dict(response_data)
                        # Remove routing metadata
                        for key in ["_broadcast", "_target_agent_id", "_client_id"]:
                            if key in message_to_agent:
                                del message_to_agent[key]
                                
                        await ws.send_text(json.dumps(message_to_agent))
                    except Exception as e:
                        logging.error(f"Error sending broadcast to agent {agent_id}: {e}")
            
            logging.info("Broadcast message sent to all connected clients and agents")
            return
            
        # Handle direct messages to a specific agent
        if "_target_agent_id" in response_data:
            target_agent_id = response_data.get("_target_agent_id")
            if target_agent_id in agent_connections:
                # Get the connection for this agent
                agent_ws = agent_connections[target_agent_id]
                
                # Create a copy of the message without routing metadata
                message_to_agent = dict(response_data)
                # Remove routing metadata
                for key in ["_broadcast", "_target_agent_id", "_client_id"]:
                    if key in message_to_agent:
                        del message_to_agent[key]
                
                # Send to the agent
                await agent_ws.send_text(json.dumps(message_to_agent))
                logging.info(f"Message forwarded to agent {target_agent_id}")
            else:
                logging.warning(f"Target agent {target_agent_id} not connected, cannot deliver message")
            return
        
        # Handle messages with a specific client_id
        client_id = response_data.get("client_id") or response_data.get("_client_id")
        if client_id:
            # Find the WebSocket for this client ID
            target_websocket = None
            for websocket in active_connections:
                websocket_client_id = getattr(websocket, "client_id", None)
                if websocket_client_id == client_id:
                    target_websocket = websocket
                    break
            
            if target_websocket:
                # Create a copy of the message without routing metadata
                message_to_client = dict(response_data)
                # Remove routing metadata
                for key in ["_broadcast", "_target_agent_id", "_client_id"]:
                    if key in message_to_client:
                        del message_to_client[key]
                
                # Send the response to the client
                await target_websocket.send_text(json.dumps(message_to_client))
                logging.info(f"Response forwarded to client {client_id}: {message_to_client}")
            else:
                logging.warning(f"Client {client_id} not found for response delivery")
        else:
            # If no routing information, log it
            logging.warning(f"Received response without routing info, cannot route: {response_data}")
    except Exception as e:
        logging.error(f"Error forwarding response to client: {e}")

async def process_message(channel, method, properties, body):
    """Process a message from RabbitMQ in an async way."""
    try:
        # Parse the message
        response_data = json.loads(body)
        logging.debug(f"Received response from broker: {response_data.get('message_type', 'unknown type')}")
        
        # Handle broker requesting agent status update
        if response_data.get("message_type") == MessageType.REQUEST_AGENT_STATUS:
            logging.info("Received request for agent status from broker")
            await send_agent_status_to_broker()
            await broadcast_agent_status()
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
            
        # Forward other messages to the appropriate WebSocket client
        await forward_response_to_client(response_data)
        
        # Acknowledge that the message was processed
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON in response from broker: {body}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logging.error(f"Error processing response from broker: {e}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

@app.on_event("startup")
async def startup_event():
    """Start the response consumer and agent ping service at application startup."""
    # Start response consumer for broker messages
    asyncio.create_task(response_consumer())
    
    # Start the agent ping service
    asyncio.create_task(agent_ping_service())
    
    # Start the periodic status broadcast service
    asyncio.create_task(periodic_status_broadcast())
    
    # Advertise server availability
    await advertise_server()
    
    # Setup signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handle_exit)

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources when the application is shutting down."""
    logging.info("Server shutting down...")
    
    # Close all WebSocket connections
    for ws in list(active_connections):
        try:
            await ws.close(code=1000, reason="Server shutdown")
        except Exception as e:
            logging.error(f"Error closing WebSocket: {e}")
    
    # Clear connection tracking dictionaries
    agent_connections.clear()
    frontend_connections.clear()
    active_connections.clear()
    agent_statuses.clear()
    agent_status_history.clear()  # Clear status history on shutdown
    
    # Close the RabbitMQ connection if it exists
    global rabbitmq_connection
    if rabbitmq_connection and rabbitmq_connection.is_open:
        try:
            rabbitmq_connection.close()
            logging.info("RabbitMQ connection closed")
        except Exception as e:
            logging.error(f"Error closing RabbitMQ connection: {e}")
    
    # Cancel all running tasks
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    logging.info("Server shutdown complete")

def handle_exit(sig, frame):
    """Handle exit signals (SIGINT, SIGTERM)."""
    logging.info(f"Received exit signal {sig}. Shutting down...")
    
    # Call shutdown event manually
    try:
        # Get event loop
        loop = asyncio.get_event_loop()
        
        # Schedule the shutdown event
        if loop.is_running():
            loop.create_task(shutdown_event())
            
            # Allow some time for shutdown tasks to complete
            shutdown_task = loop.create_task(asyncio.sleep(1))
            
            # Wait for the shutdown task to complete
            try:
                loop.run_until_complete(shutdown_task)
            except asyncio.CancelledError:
                pass
    except Exception as e:
        logging.error(f"Error during shutdown: {e}")
    
    # Exit with successful status code
    sys.exit(0)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    
    # Generate a unique client ID for this connection
    client_id = f"client_{len(active_connections)}_{uuid.uuid4().hex[:8]}"
    websocket.client_id = client_id  # Attach client_id to websocket object
    websocket.connection_type = "unknown"  # Will be set to "agent", "frontend", or "broker" later
    logging.info(f"New WebSocket connection: {client_id}")
    
    try:
        while True:
            message = await websocket.receive_text()
            message_data = json.loads(message)
            message_type = message_data.get("message_type")
            
            # Add client_id for routing responses back
            message_data["_client_id"] = client_id
            
            # Handle REGISTER_BROKER messages
            if message_type == MessageType.REGISTER_BROKER:
                websocket.connection_type = "broker"
                global broker_connection
                broker_connection = websocket
                logging.info(f"Broker connected: {client_id}")
                
                # Send current agent status to broker with only active agents
                await send_agent_status_to_broker()
                continue
            
            # Handle REGISTER_AGENT messages to track agent connections
            elif message_type == MessageType.REGISTER_AGENT:
                # If we initially thought this was a frontend, remove it
                if websocket in frontend_connections:
                    frontend_connections.remove(websocket)
                
                websocket.connection_type = "agent"
                agent_id = message_data.get("agent_id")
                agent_name = message_data.get("agent_name")
                
                if agent_id:
                    # Store agent websocket connection
                    agent_connections[agent_id] = websocket
                    
                    # Update agent status
                    current_time = datetime.now()
                    agent_statuses[agent_id] = AgentStatus(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        is_online=True,
                        last_seen=current_time.strftime("%Y-%m-%d %H:%M:%S")
                    )
                    
                    # Forward registration to broker
                    logging.info(f"Forwarding agent registration to broker: {agent_id}")
                    publish_to_broker_control_queue(message_data)
                    
                    # Send immediate registration success response to agent
                    response = AgentRegistrationResponse(
                        status=ResponseStatus.SUCCESS,
                        agent_id=agent_id,
                        message="Agent registered with server successfully"
                    )
                    await websocket.send_text(json.dumps(response.model_dump()))
                    
                    # Broadcast updated agent status to frontend clients and broker
                    await broadcast_agent_status(force_full_update=True)
                    
                    logging.info(f"Agent {agent_name} (ID: {agent_id}) registered")
                    
            # Handle explicit frontend registration
            elif message_type == MessageType.REGISTER_FRONTEND:
                websocket.connection_type = "frontend"
                frontend_connections.add(websocket)
                logging.info(f"Frontend client registered: {client_id}")
                
                # Send full agent status immediately
                await broadcast_agent_status(force_full_update=True)
                    
            # Handle PONG messages from agents
            elif message_type == MessageType.PONG:
                agent_id = message_data.get("agent_id")
                
                if agent_id and agent_id in agent_statuses:
                    # Update agent's last seen timestamp
                    current_time = datetime.now()
                    agent_statuses[agent_id].last_seen = current_time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Ensure agent is marked as online
                    if not agent_statuses[agent_id].is_online:
                        agent_statuses[agent_id].is_online = True
                        # Broadcast updated status since agent is back online
                        await broadcast_agent_status()
                        
                    logging.info(f"Received PONG from agent {agent_id}")
                else:
                    logging.warning(f"Received PONG for unknown agent ID: {agent_id}")
                    
            # Handle regular chat messages
            elif message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                # Add connection type metadata
                message_data["_connection_type"] = websocket.connection_type
                
                # Forward chat messages to the broker
                try:
                    logging.info(f"Forwarding message to broker from client {client_id}")
                    publish_to_incoming_queue(message_data)
                except Exception as e:
                    logging.error(f"Error processing chat message: {e}")
                    error_message = ChatMessage.create(
                        sender_id="server", 
                        receiver_id=message_data.get("sender_id", "unknown"),
                        text_payload=f"Error processing message: {str(e)}", 
                        message_type=MessageType.ERROR
                    )
                    await websocket.send_text(json.dumps(error_message.model_dump()))
            
            # Handle other message types
            else:
                # Log unhandled message type
                logging.warning(f"Received unhandled message type: {message_type}")
                error_message = ChatMessage.create(
                    sender_id="server", 
                    receiver_id=message_data.get("sender_id", "unknown"),
                    text_payload=f"Unsupported message type: {message_type}", 
                    message_type=MessageType.ERROR
                )
                await websocket.send_text(json.dumps(error_message.model_dump()))
                
    except WebSocketDisconnect:
        # Handle disconnection
        active_connections.remove(websocket)
        connection_type = getattr(websocket, "connection_type", "unknown")
        
        if connection_type == "broker" and websocket == broker_connection:
            broker_connection = None
            logging.info("Broker disconnected")
            
        elif connection_type == "frontend" and websocket in frontend_connections:
            frontend_connections.remove(websocket)
            logging.info(f"Frontend client disconnected: {client_id}")
            
        elif connection_type == "agent":
            # Find and remove the agent
            for agent_id, ws in list(agent_connections.items()):
                if ws == websocket:
                    # Mark agent as offline
                    if agent_id in agent_statuses:
                        agent_statuses[agent_id].is_online = False
                        logging.info(f"Agent {agent_statuses[agent_id].agent_name} (ID: {agent_id}) disconnected and marked as offline")
                        
                    # Remove from agent connections
                    del agent_connections[agent_id]
                    
                    # Broadcast updated agent status
                    await broadcast_agent_status()
                    
                    # Notify broker about agent disconnection
                    disconnect_message = {
                        "message_type": MessageType.CLIENT_DISCONNECTED,
                        "agent_id": agent_id,
                        "connection_type": "agent",
                        "is_full_update": True  # Indicate this is a full update
                    }
                    publish_to_broker_control_queue(disconnect_message)
                    break
            
        logging.info(f"WebSocket disconnected: {client_id} (type: {connection_type})")
        
    except Exception as e:
        logging.error(f"WebSocket error: {str(e)}")
        if websocket in active_connections:
            active_connections.remove(websocket)
        if websocket in frontend_connections:
            frontend_connections.remove(websocket)
        if websocket == broker_connection:
            broker_connection = None
        
        # Check if this was an agent connection
        for agent_id, ws in list(agent_connections.items()):
            if ws == websocket:
                # Mark agent as offline and remove connection
                if agent_id in agent_statuses:
                    agent_statuses[agent_id].is_online = False
                
                del agent_connections[agent_id]
                await broadcast_agent_status()
                
                # Notify broker about agent disconnection
                disconnect_message = {
                    "message_type": MessageType.CLIENT_DISCONNECTED,
                    "agent_id": agent_id,
                    "connection_type": "agent",
                    "is_full_update": True  # Indicate this is a full update
                }
                publish_to_broker_control_queue(disconnect_message)
                break

if __name__ == "__main__":
    import uvicorn
    
    # Run the FastAPI app with uvicorn
    print("Starting FastAPI WebSocket server on port 8765...")
    print("Press Ctrl+C to stop the server.")
    
    # Use a custom server config with proper signal handling
    config = uvicorn.Config(
        "server:app",
        host="0.0.0.0",
        port=8765,
        log_level="info",
        reload=False  # Disable reload to ensure proper signal handling
    )
    server = uvicorn.Server(config)
    
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nReceived Ctrl+C. Shutting down...")
        # The shutdown events will be triggered by uvicorn