import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Set, Optional
import asyncio
import os

from fastapi import WebSocket, WebSocketDisconnect

# Import shared models, config, state, and utils
from shared_models import MessageType, ResponseStatus, ChatMessage, setup_logging

import state
import rabbitmq_utils
import agent_manager
# Revert to direct import as main.py is run directly
import services
import grpc_services  # Import the gRPC services module


logger = setup_logging(__name__)

# Store client names
client_names: Dict[str, str] = {}

def generate_unique_id(client_type: str) -> str:
    """Generate a unique ID for a client based on their type."""
    unique_id = str(uuid.uuid4())[:8]  # Take first 8 characters of UUID
    return f"{client_type}_{unique_id}"



async def _handle_register_broker(websocket: WebSocket, message: dict) -> dict:
    """Handle broker registration.
    
    WebSocket connection is maintained for general message passing,
    but agent status updates are sent exclusively via gRPC.
    """
    logger.info(f"Handling broker registration request: {message}")
    broker_name = message.get("broker_name")
    if not broker_name:
        logger.warning(f"Broker registration failed: missing broker_name in request: {message}")
        return {
            "message_type": MessageType.ERROR,
            "text_payload": "Broker name is required for registration"
        }
    
    # Generate unique ID for broker
    broker_id = generate_unique_id("broker")
    logger.info(f"Generated new broker ID: {broker_id} for broker: {broker_name}")
    
    # Store the connection and name
    state.broker_connections[broker_id] = websocket
    client_names[broker_id] = broker_name
    
    # Set connection type on the websocket object
    websocket.client_id = broker_id
    websocket.connection_type = "broker"
    
    logger.info(f"Stored broker connection and name. Current broker connections: {list(state.broker_connections.keys())}")
    
    # Add to broker status dictionary
    async with state.broker_status_lock:
        state.broker_statuses[broker_id] = {
            "is_online": True,
            "last_seen": datetime.now().isoformat()
        }
    
    logger.info(f"Broker registered successfully: {broker_name} (ID: {broker_id})")
    
    # Get gRPC config
    grpc_host = os.getenv("GRPC_HOST", "localhost")
    grpc_port = os.getenv("GRPC_PORT", "50051")
    
    # Create registration response with gRPC info
    response = {
        "message_type": MessageType.REGISTER_BROKER_RESPONSE,
        "status": ResponseStatus.SUCCESS,
        "broker_id": broker_id,
        "broker_name": broker_name,
        "message": "Broker registered successfully",
        "grpc_host": grpc_host,
        "grpc_port": grpc_port,
        "use_grpc_for_agent_status": True
    }
    
    logger.debug(f"Sending registration response to broker: {response}")
    
    # No longer sending agent status via WebSocket
    # Agent status updates will be sent via gRPC
    
    return response

async def _handle_register_agent(websocket: WebSocket, message: dict) -> dict:
    """Handle agent registration."""
    logger.debug(f"Handling agent registration request: {message}")
    agent_name = message.get("agent_name")
    if not agent_name:
        logger.warning(f"Registration failed: missing agent_name in request: {message}")
        return {
            "message_type": MessageType.ERROR,
            "text_payload": "Agent name is required for registration"
        }
    
    # Generate unique ID for agent
    agent_id = generate_unique_id("agent")
    logger.debug(f"Generated new agent ID: {agent_id} for agent: {agent_name}")
    
    # Store the connection and name
    state.agent_connections[agent_id] = websocket
    client_names[agent_id] = agent_name
    
    # Set the connection type attributes on the websocket
    websocket.client_id = agent_id
    websocket.connection_type = "agent"
    
    logger.debug(f"Stored agent connection and name: agent_id={agent_id}, name={agent_name}")
    
    # Update agent status and trigger broadcast
    status_updated = agent_manager.update_agent_status(agent_id, agent_name, True)
    logger.debug(f"Agent status updated in agent manager: {status_updated}")
    
    # Explicitly trigger broadcasting via gRPC
    logger.info(f"Broadcasting agent status via gRPC after agent registration: {agent_id}")
    asyncio.create_task(grpc_services.broadcast_agent_status_updates(is_full_update=True))
    
    logger.info(f"Agent registered successfully: {agent_name} (ID: {agent_id})")
    
    response = {
        "message_type": MessageType.REGISTER_AGENT_RESPONSE,
        "status": ResponseStatus.SUCCESS,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "message": "Agent registered successfully"
    }
    logger.debug(f"Sending registration response: {response}")
    return response

async def _handle_register_frontend(websocket: WebSocket, message: dict) -> dict:
    """Handle frontend registration."""
    frontend_name = message.get("frontend_name")
    if not frontend_name:
        return {
            "message_type": MessageType.ERROR,
            "text_payload": "Frontend name is required for registration"
        }
    
    # Generate unique ID for frontend
    frontend_id = generate_unique_id("web")
    
    # Store the connection and name
    state.frontend_connections.add(websocket)
    client_names[frontend_id] = frontend_name
    
    # Set the client_id attribute on the websocket
    websocket.client_id = frontend_id
    websocket.connection_type = "frontend"
    
    logger.info(f"Frontend registered: {frontend_name} (ID: {frontend_id})")
    
    # Send an immediate agent status update to the newly connected frontend
    logger.debug(f"Sending immediate agent status update to new frontend {frontend_id}")
    asyncio.create_task(agent_manager.broadcast_agent_status(force_full_update=True, is_full_update=True))
    
    return {
        "message_type": MessageType.REGISTER_FRONTEND_RESPONSE,
        "status": ResponseStatus.SUCCESS,
        "frontend_id": frontend_id,
        "frontend_name": frontend_name,
        "message": "Frontend registered successfully"
    }

async def _handle_pong(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles pong messages from agents and brokers."""
    # Use the client_id to identify the sender type
    if client_id.startswith("broker_"):
        # PONG is from a broker, handle using its client_id
        logger.debug(f"Received PONG from broker: {client_id}")
        agent_manager.handle_pong(client_id) # The manager function can differentiate
    elif client_id.startswith("agent_"):
        # PONG is from an agent, expect agent_id in the message body
        logger.debug(f"Received PONG from agent: {client_id}")
        agent_id_from_message = message_data.get("agent_id")
        if agent_id_from_message:
            # Verify the agent_id in the message matches the client_id if needed
            if agent_id_from_message != client_id:
                logger.warning(f"Received PONG from agent {client_id} but message contains different agent_id: {agent_id_from_message}")
                # Decide how to handle mismatch - maybe trust client_id?
                agent_manager.handle_pong(client_id)
            else:
                agent_manager.handle_pong(agent_id_from_message)
        else:
            logger.warning(f"Received PONG from agent {client_id} but it's missing the 'agent_id' field.")
            # Optionally, still update based on client_id if agent_id is missing
            agent_manager.handle_pong(client_id)
    else:
        # PONG from an unknown client type (e.g., frontend, though they shouldn't send PONGs)
        logger.warning(f"Received PONG from unexpected client type: {client_id}")

async def _handle_chat_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles standard chat, reply, and system messages.

    Broadcasts these messages to all connected frontends before sending to RabbitMQ.
    All messages are marked with routing_status="pending" until processed by the broker.
    """
    message_type = message_data.get("message_type", "UNKNOWN")
    # Add connection type metadata before forwarding
    message_data["_connection_type"] = getattr(websocket, "connection_type", "unknown")
    # Add client_id to the message
    message_data["_client_id"] = client_id
    # Add routing status to indicate message is pending broker routing
    message_data["routing_status"] = "pending"
    
    logger.info(f"Incoming {message_type} message {message_data.get('message_id','N/A')} from {client_id} : '{message_data.get('text_payload','N/A')}'")

    # --- Broadcast to all connected Frontends FIRST --- 
    payload_str = json.dumps(message_data)
    disconnected_frontend = set()
    frontend_count = len(state.frontend_connections)
    if frontend_count > 0:
        for fe_ws in list(state.frontend_connections):
            fe_client_desc = f"frontend client {getattr(fe_ws, 'client_id', '?')}"
            logger.info(f"Broadcasting message {message_data.get('message_id','N/A')} to {fe_client_desc}")
            if not await services._safe_send_websocket(fe_ws, payload_str, fe_client_desc):
                disconnected_frontend.add(fe_ws)
        # Clean up disconnected frontends immediately
        if disconnected_frontend:
            state.frontend_connections -= disconnected_frontend
            logger.info(f"Removed {len(disconnected_frontend)} disconnected frontend clients during incoming message broadcast.")

    # --- Forward to Broker via RabbitMQ --- 
    logger.debug(f"Forwarding {message_type} message from {client_id} to broker input queue.")
    if not rabbitmq_utils.publish_to_broker_input_queue(message_data):
        logger.error(f"Failed to publish incoming message from {client_id} to RabbitMQ.")
        # Send error back to the original sender
        error_resp = {
            "message_type": MessageType.ERROR,
            "sender_id": "server",
            "receiver_id": client_id,  # Send back to the original sender
            "routing_status": "error",  # Mark as routing error
            "text_payload": "Error: Could not forward message to broker."
        }
        try: 
            await websocket.send_text(json.dumps(error_resp))
            logger.warning(f"Sent broker publish error back to client {client_id}")
        except Exception as e:
            logger.error(f"Failed to send broker publish error back to client {client_id}: {e}")
            # If sending error fails, the connection might be dead. 
            # The disconnect will likely be handled by the main loop's finally block.

async def _handle_client_disconnected_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles (unexpected) client disconnected messages."""
    logger.warning(f"Received unexpected CLIENT_DISCONNECTED message from {client_id}. Ignoring.")

async def _handle_unknown_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles unrecognized message types."""
    message_type = message_data.get("message_type", "UNKNOWN")
    error_text = f"Error: Unsupported message type '{message_type}' received."
    logger.warning(f"{error_text} from {client_id}. Data: {message_data}")
    # Reverted: Optionally send an error message back
    error_resp = ChatMessage.create(
        sender_id="server",
        receiver_id=message_data.get("sender_id", client_id),
        text_payload=error_text,
        message_type=MessageType.ERROR
    )
    try: 
        await websocket.send_text(error_resp.model_dump_json()) 
    except Exception as e:
         logger.error(f"Failed to send unknown message type error back to client {client_id}: {e}")

async def _handle_request_agent_status(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles REQUEST_AGENT_STATUS message from clients.
    
    For brokers, recommend using gRPC instead.
    For frontends, send status via WebSocket.
    """
    # Check if this is a broker (should use gRPC instead)
    connection_type = getattr(websocket, "connection_type", "unknown")
    if connection_type == "broker":
        logger.warning(f"Broker {client_id} requested agent status via WebSocket, should use gRPC instead")
        response = {
            "message_type": MessageType.ERROR,
            "text_payload": "Brokers should use gRPC for agent status updates",
            "sender_id": "Server",
            "receiver_id": client_id
        }
        await websocket.send_text(json.dumps(response))
        return
    
    # For frontends, send status update via WebSocket
    if connection_type == "frontend":
        logger.info(f"Frontend {client_id} requested agent status update")
        # Create and send a full agent status update for this specific frontend
        status_update = {
            "message_type": MessageType.AGENT_STATUS_UPDATE,
            "agents": [
                {
                    "agent_id": agent_id,
                    "agent_name": status.agent_name,
                    "is_online": status.is_online,
                    "last_seen": status.last_seen
                }
                for agent_id, status in state.agent_statuses.items()
            ],
            "is_full_update": True
        }
        await websocket.send_text(json.dumps(status_update))
        logger.info(f"Sent agent status update to frontend {client_id}")
    else:
        logger.warning(f"Unexpected client type {connection_type} requested agent status")

# --- Helper Function for Disconnect Cleanup ---

async def _handle_disconnect(websocket: WebSocket, client_id: str):
    """Handles cleanup when a WebSocket connection is closed."""
    logger.info(f"Cleaning up connection for {client_id} ({getattr(websocket, 'connection_type', 'unknown')})")
    
    connection_type = getattr(websocket, "connection_type", "unknown")
    needs_status_broadcast = False
    disconnected_agent_id = None
    
    try:
        # Always make sure to remove from active connections first
        state.active_connections.discard(websocket)
        
        if connection_type == "broker":
            # Remove from broker_connections dictionary
            for broker_id, ws in list(state.broker_connections.items()):
                if ws == websocket:
                    del state.broker_connections[broker_id]
                    logger.info(f"Broker connection closed: {broker_id}")
                    break
            
        elif connection_type == "frontend":
            state.frontend_connections.discard(websocket)
            logger.info(f"Frontend client connection closed: {client_id}")
            
        elif connection_type == "agent":
            for agent_id, ws in list(state.agent_connections.items()):
                if ws == websocket:
                    disconnected_agent_id = agent_id
                    del state.agent_connections[agent_id]
                    logger.info(f"Agent connection closed: {client_id} (Agent ID: {agent_id})")
                    break
            
            if disconnected_agent_id:
                agent_manager.mark_agent_offline(disconnected_agent_id)
                needs_status_broadcast = True
        
        # Log remaining connection counts
        logger.info(f"Connection counts after cleanup: {len(state.active_connections)} active, {len(state.frontend_connections)} frontend, {len(state.agent_connections)} agent, {len(state.broker_connections)} broker")
        
        # Broadcast agent status updates if an agent disconnected
        if needs_status_broadcast:
            asyncio.create_task(agent_manager.broadcast_agent_status())
    
    except Exception as e:
        logger.error(f"Error during disconnect cleanup for {client_id}: {e}")
        # Still try to remove connections even if there was an error
        state.active_connections.discard(websocket)
        state.frontend_connections.discard(websocket)

# --- Main WebSocket Endpoint ---

async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket handling endpoint"""
    await websocket.accept()
    client_id = None
    
    try:
        logger.debug("New WebSocket connection")
        
        # First message should be a registration message
        registration_msg_str = await websocket.receive_text()
        registration_msg = json.loads(registration_msg_str)
        
        # Process based on message type
        message_type = registration_msg.get("message_type")
        
        if message_type == MessageType.REGISTER_BROKER:
            # Broker registration
            response = await _handle_register_broker(websocket, registration_msg)
            await websocket.send_text(json.dumps(response))
            client_id = websocket.client_id  # Store client_id from the registration
            
        elif message_type == MessageType.REGISTER_AGENT:
            # Agent registration
            response = await _handle_register_agent(websocket, registration_msg)
            await websocket.send_text(json.dumps(response))
            client_id = websocket.client_id  # Store client_id from the registration
            
        elif message_type == MessageType.REGISTER_FRONTEND:
            # Frontend registration
            response = await _handle_register_frontend(websocket, registration_msg)
            await websocket.send_text(json.dumps(response))
            client_id = websocket.client_id  # Store client_id from the registration
            
        else:
            # Invalid first message
            logger.warning(f"Invalid first message type: {message_type}")
            await websocket.send_text(json.dumps({
                "message_type": MessageType.ERROR,
                "text_payload": "First message must be a registration message"
            }))
            return
        
        # Continue handling WebSocket messages
        while True:
            message_str = await websocket.receive_text()
            message_data = json.loads(message_str)
            
            # Check message type and route accordingly
            message_type = message_data.get("message_type")
            
            if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                # Chat messages
                await _handle_chat_message(websocket, client_id, message_data)
            elif message_type == MessageType.PONG:
                # PONG response (from ping)
                logger.debug(f"Received PONG from {client_id}")
                # No need to do anything else with PONG
            elif message_type == MessageType.PING:
                # PING request (client wants to check server health)
                logger.debug(f"Received PING from {client_id}, sending PONG")
                await websocket.send_text(json.dumps({"message_type": MessageType.PONG}))
            elif message_type == MessageType.CLIENT_DISCONNECTED:
                # Client disconnection notice
                await _handle_client_disconnected_message(websocket, client_id, message_data)
            elif message_type == MessageType.REQUEST_AGENT_STATUS:
                # Agent status request
                await _handle_request_agent_status(websocket, client_id, message_data)
            else:
                # Unhandled message type
                await _handle_unknown_message(websocket, client_id, message_data)
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_id}")
    except Exception as e:
        logger.exception(f"Error in WebSocket handler: {e}")
    finally:
        # Handle cleanup on disconnect
        if client_id:
            await _handle_disconnect(websocket, client_id)
        else:
            logger.info("WebSocket disconnected before registration completed")