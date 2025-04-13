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
    
    All agent status requests should now use gRPC.
    For frontends, still support WebSocket for legacy compatibility.
    """
    # Check connection type
    connection_type = getattr(websocket, "connection_type", "unknown")
        
    # For frontends, continue to support WebSocket updates for backwards compatibility 
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
        # For any other client type, recommend gRPC
        logger.warning(f"Client type {connection_type} requested agent status via WebSocket, should use gRPC")
        response = {
            "message_type": MessageType.ERROR,
            "text_payload": "Please use gRPC for agent status updates",
            "sender_id": "Server",
            "receiver_id": client_id
        }
        await websocket.send_text(json.dumps(response))

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
        
            
        if connection_type == "frontend":
            state.frontend_connections.discard(websocket)
            logger.info(f"Frontend client connection closed: {client_id}")
                    
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
        
        if message_type == MessageType.REGISTER_FRONTEND:
            # Frontend registration (still supported)
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