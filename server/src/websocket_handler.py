import json
import uuid
from typing import Dict, Any
import asyncio

from fastapi import WebSocket, WebSocketDisconnect

# Import shared models, config, state, and utils
from shared_models import MessageType, ResponseStatus, ChatMessage, setup_logging
import state
import rabbitmq_utils
import agent_manager
import services

logger = setup_logging(__name__)

# Store client names
client_names: Dict[str, str] = {}

def generate_unique_id(client_type: str) -> str:
    """Generate a unique ID for a client based on their type."""
    return f"{client_type}_{uuid.uuid4().hex[:8]}"

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
    """Handle standard chat, reply, and system messages."""
    message_type = message_data.get("message_type", "UNKNOWN")
    message_data["_connection_type"] = getattr(websocket, "connection_type", "unknown")
    message_data["_client_id"] = client_id
    message_data["routing_status"] = "pending"
    
    logger.info(f"Incoming {message_type} message {message_data.get('message_id','N/A')} from {client_id}")

    # Broadcast to all connected Frontends
    payload_str = json.dumps(message_data)
    disconnected_frontend = set()
    frontend_count = len(state.frontend_connections)
    if frontend_count > 0:
        for fe_ws in list(state.frontend_connections):
            fe_client_desc = f"frontend client {getattr(fe_ws, 'client_id', '?')}"
            logger.info(f"Broadcasting message {message_data.get('message_id','N/A')} to {fe_client_desc}")
            if not await services._safe_send_websocket(fe_ws, payload_str, fe_client_desc):
                disconnected_frontend.add(fe_ws)
        if disconnected_frontend:
            state.frontend_connections -= disconnected_frontend
            logger.info(f"Removed {len(disconnected_frontend)} disconnected frontend clients during broadcast.")

    # Forward to Broker via RabbitMQ
    logger.debug(f"Forwarding {message_type} message from {client_id} to broker input queue.")
    if not rabbitmq_utils.publish_to_broker_input_queue(message_data):
        logger.error(f"Failed to publish incoming message from {client_id} to RabbitMQ.")
        error_resp = {
            "message_type": MessageType.ERROR,
            "sender_id": "server",
            "receiver_id": client_id,
            "routing_status": "error",
            "text_payload": "Error: Could not forward message to broker."
        }
        try: 
            await websocket.send_text(json.dumps(error_resp))
            logger.warning(f"Sent broker publish error back to client {client_id}")
        except Exception as e:
            logger.error(f"Failed to send broker publish error back to client {client_id}: {e}")

async def _handle_client_disconnected_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle (unexpected) client disconnected messages."""
    logger.warning(f"Received unexpected CLIENT_DISCONNECTED message from {client_id}. Ignoring.")

async def _handle_unknown_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle unrecognized message types."""
    message_type = message_data.get("message_type", "UNKNOWN")
    error_text = f"Error: Unsupported message type '{message_type}' received."
    logger.warning(f"{error_text} from {client_id}. Data: {message_data}")
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
    """Handle REQUEST_AGENT_STATUS message from clients."""
    connection_type = getattr(websocket, "connection_type", "unknown")
        
    if connection_type == "frontend":
        logger.info(f"Frontend {client_id} requested agent status update")
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
        logger.warning(f"Client type {connection_type} requested agent status via WebSocket, should use gRPC")
        response = {
            "message_type": MessageType.ERROR,
            "text_payload": "Please use gRPC for agent status updates",
            "sender_id": "Server",
            "receiver_id": client_id
        }
        await websocket.send_text(json.dumps(response))

async def _handle_disconnect(websocket: WebSocket, client_id: str):
    """Handle cleanup when a WebSocket connection is closed."""
    logger.info(f"Cleaning up connection for {client_id} ({getattr(websocket, 'connection_type', 'unknown')})")
    
    connection_type = getattr(websocket, "connection_type", "unknown")
    needs_status_broadcast = False
    disconnected_agent_id = None
    
    try:
        state.active_connections.discard(websocket)
            
        if connection_type == "frontend":
            state.frontend_connections.discard(websocket)
            logger.info(f"Frontend client connection closed: {client_id}")
                    
        logger.info(f"Connection counts after cleanup: {len(state.active_connections)} active, {len(state.frontend_connections)} frontend, {len(state.agent_connections)} agent, {len(state.broker_connections)} broker")
        
        if needs_status_broadcast:
            asyncio.create_task(agent_manager.broadcast_agent_status())
    
    except Exception as e:
        logger.error(f"Error during disconnect cleanup for {client_id}: {e}")
        state.active_connections.discard(websocket)
        state.frontend_connections.discard(websocket)

async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket handling endpoint"""
    await websocket.accept()
    client_id = None
    
    try:
        logger.debug("New WebSocket connection")
        
        # First message should be a registration message
        registration_msg_str = await websocket.receive_text()
        registration_msg = json.loads(registration_msg_str)
        
        message_type = registration_msg.get("message_type")
        
        if message_type == MessageType.REGISTER_FRONTEND:
            response = await _handle_register_frontend(websocket, registration_msg)
            await websocket.send_text(json.dumps(response))
            client_id = websocket.client_id
        else:
            logger.warning(f"Invalid first message type: {message_type}")
            await websocket.send_text(json.dumps({
                "message_type": MessageType.ERROR,
                "text_payload": "First message must be a registration message"
            }))
            return
        
        while True:
            message_str = await websocket.receive_text()
            message_data = json.loads(message_str)
            
            message_type = message_data.get("message_type")
            
            if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                await _handle_chat_message(websocket, client_id, message_data)
            elif message_type == MessageType.PONG:
                logger.debug(f"Received PONG from {client_id}")
            elif message_type == MessageType.PING:
                logger.debug(f"Received PING from {client_id}, sending PONG")
                await websocket.send_text(json.dumps({"message_type": MessageType.PONG}))
            elif message_type == MessageType.CLIENT_DISCONNECTED:
                await _handle_client_disconnected_message(websocket, client_id, message_data)
            elif message_type == MessageType.REQUEST_AGENT_STATUS:
                await _handle_request_agent_status(websocket, client_id, message_data)
            else:
                await _handle_unknown_message(websocket, client_id, message_data)
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_id}")
    except Exception as e:
        logger.exception(f"Error in WebSocket handler: {e}")
    finally:
        if client_id:
            await _handle_disconnect(websocket, client_id)
        else:
            logger.info("WebSocket disconnected before registration completed")