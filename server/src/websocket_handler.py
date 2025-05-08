import json
import uuid
from typing import Dict, Any
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect

# Import shared models, config, state, and utils
from shared_models import MessageType, ResponseStatus, ChatMessage, setup_logging
from decorators import log_function_call
import state
import message_queue_handler
import agent_manager
import services

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module

# Store client names
client_names: Dict[str, str] = {}

@log_function_call
async def _handle_register_frontend(websocket: WebSocket, message: dict) -> dict:
    """Handle frontend registration."""
    frontend_name = message.get("frontend_name")
    if not frontend_name:
        return {
            "message_type": MessageType.ERROR,
            "text_payload": "Frontend name is required for registration"
        }

    # Generate unique ID for frontend - Keep this specific to frontend WS registration
    frontend_id = f"web_{uuid.uuid4().hex[:8]}"

    # Store the connection and name
    state.frontend_connections.add(websocket)
    client_names[frontend_id] = frontend_name

    # Set the client_id attribute on the websocket
    websocket.client_id = frontend_id
    websocket.connection_type = "frontend"

    logger.info(f"Frontend registered: {frontend_name} (ID: {frontend_id})")

    # Send an immediate agent status update to the newly connected frontend
    asyncio.create_task(agent_manager.broadcast_agent_status(force_full_update=True, is_full_update=True, target_websocket=None))

    return {
        "message_type": MessageType.REGISTER_FRONTEND_RESPONSE,
        "status": ResponseStatus.SUCCESS,
        "frontend_id": frontend_id,
        "frontend_name": frontend_name,
        "message": "Frontend registered successfully"
    }

@log_function_call
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
            logger.debug(f"Broadcasting message {message_data.get('message_id','N/A')} to {fe_client_desc}")
            if not await services._safe_send_websocket(fe_ws, payload_str, fe_client_desc):
                disconnected_frontend.add(fe_ws)
        if disconnected_frontend:
            state.frontend_connections -= disconnected_frontend
            logger.info(f"Removed {len(disconnected_frontend)} disconnected frontend clients during broadcast.")

    # Forward to Broker via RabbitMQ
    if not message_queue_handler.publish_to_broker_input_queue(message_data):
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

@log_function_call
async def _handle_client_disconnected_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle (unexpected) client disconnected messages."""
    logger.warning(f"Received unexpected CLIENT_DISCONNECTED message from {client_id}. Ignoring.")

@log_function_call
async def _handle_unknown_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle unrecognized message types."""
    message_type = message_data.get("message_type", "UNKNOWN")
    error_text = f"Error: Unsupported message type '{message_type}' received."
    logger.warning(f"{error_text} from {client_id}. Data: {message_data}")
    error_resp = ChatMessage.create(
        sender_id="server",
        text_payload=error_text,
        message_type=MessageType.ERROR
    )
    try: 
        await websocket.send_text(json.dumps(error_resp.model_dump())) 
    except Exception as e:
        logger.error(f"Failed to send unknown message type error back to client {client_id}: {e}")

@log_function_call
async def _handle_request_agent_status(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle REQUEST_AGENT_STATUS message from frontend clients."""
    connection_type = getattr(websocket, "connection_type", "unknown")
    if connection_type != "frontend":
        logger.warning(f"Received REQUEST_AGENT_STATUS from non-frontend client {client_id}. Ignoring.")
        return

    logger.info(f"Frontend {client_id} requested agent status update")
    
    # Use the agent_manager's broadcast_agent_status function to send the update
    # to just the requesting frontend using the target_websocket parameter
    await agent_manager.broadcast_agent_status(
        force_full_update=True, 
        is_full_update=True,
        target_websocket=websocket
    )
    
    logger.info(f"Agent status update sent to requesting frontend {client_id}")

@log_function_call
async def _send_agent_command_to_agents(agent_ids, websocket, client_id, command_type, message_type):
    """Send a command (pause/resume/shutdown) to one or more agents and send an ack to the frontend."""
    from agent_registration_service import send_command_to_agent
    tasks = [send_command_to_agent(agent_id, command_type, "") for agent_id in agent_ids]
    if tasks:
        await asyncio.gather(*tasks)
        logger.info(f"Sent {command_type.upper()} command to {len(tasks)} agent(s).")
    else:
        logger.info(f"No agents to {command_type}.")
    ack = {
        "message_type": message_type,
        "status": ResponseStatus.SUCCESS,
        "text_payload": f"{command_type.capitalize()} command sent to {len(tasks)} agent(s)."
    }
    try:
        await websocket.send_text(json.dumps(ack))
    except Exception as e:
        logger.error(f"Failed to send {message_type} ack to client {client_id}: {e}")

@log_function_call
async def _handle_pause_all_agents(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle PAUSE_ALL_AGENTS control message from frontend."""
    # Select all agent_ids (no is_online check, as that field is removed)
    agent_ids = list(state.agent_statuses.keys())
    await _send_agent_command_to_agents(agent_ids, websocket, client_id, "pause", MessageType.PAUSE_ALL_AGENTS)

@log_function_call
async def _handle_RESUME_All_agents(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle RESUME_ALL_AGENTS control message from frontend."""
    agent_ids = list(state.agent_statuses.keys())
    await _send_agent_command_to_agents(agent_ids, websocket, client_id, "resume", MessageType.RESUME_ALL_AGENTS)

@log_function_call
async def _handle_pause_agent(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle PAUSE_AGENT control message for a single agent from frontend."""
    agent_id = message_data.get('agent_id')
    if not agent_id:
        logger.warning(f"PAUSE_AGENT received with no agent_id from {client_id}.")
        return
    await _send_agent_command_to_agents([agent_id], websocket, client_id, "pause", MessageType.PAUSE_AGENT)

@log_function_call
async def _handle_RESUME_Agent(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handle RESUME_AGENT control message for a single agent from frontend."""
    agent_id = message_data.get('agent_id')
    if not agent_id:
        logger.warning(f"RESUME_AGENT received with no agent_id from {client_id}.")
        return
    await _send_agent_command_to_agents([agent_id], websocket, client_id, "resume", MessageType.RESUME_AGENT)

@log_function_call
async def _handle_deregister_all_agents(websocket: WebSocket, client_id: str, message_data: dict):
    """Handle DEREGISTER_ALL_AGENTS control message from frontend."""
    agent_ids = list(state.agent_statuses.keys())
    await _send_agent_command_to_agents(agent_ids, websocket, client_id, "shutdown", MessageType.DEREGISTER_ALL_AGENTS)

@log_function_call
async def _handle_deregister_agent(websocket: WebSocket, client_id: str, message_data: dict):
    """Handle DEREGISTER_AGENT control message for a single agent from frontend."""
    agent_id = message_data.get('agent_id')
    if not agent_id:
        logger.warning(f"DEREGISTER_AGENT received with no agent_id from {client_id}.")
        return
    await _send_agent_command_to_agents([agent_id], websocket, client_id, "shutdown", MessageType.DEREGISTER_AGENT)

@log_function_call
async def _handle_disconnect(websocket: WebSocket, client_id: str):
    """Handle cleanup when a WebSocket connection is closed."""
    logger.info(f"Cleaning up connection for {client_id} ({getattr(websocket, 'connection_type', 'unknown')})")

    connection_type = getattr(websocket, "connection_type", "unknown")

    try:
        # Only handle frontend disconnects here explicitly
        if connection_type == "frontend":
            state.frontend_connections.discard(websocket)
            client_names.pop(client_id, None) # Clean up name mapping
            logger.info(f"Frontend client connection closed: {client_id}")
        else:
            logger.info(f"Non-frontend client {client_id} ({connection_type}) disconnected. Cleanup handled elsewhere.")

        # Log current counts
        logger.info(f"Connection counts after cleanup: {len(state.frontend_connections)} frontend")

    except Exception as e:
        logger.error(f"Error during disconnect cleanup for {client_id}: {e}")
        if connection_type == "frontend":
            state.frontend_connections.discard(websocket)

@log_function_call
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket handling endpoint - Primarily for Frontends now"""
    await websocket.accept()
    client_id = None
    connection_type = "unknown" # Track connection type

    try:
        logger.debug("New WebSocket connection attempting registration...")

        # First message should be a registration message (only frontend expected now)
        registration_msg_str = await websocket.receive_text()
        registration_msg = json.loads(registration_msg_str)

        message_type = registration_msg.get("message_type")

        if message_type == MessageType.REGISTER_FRONTEND:
            response = await _handle_register_frontend(websocket, registration_msg)
            await websocket.send_text(json.dumps(response))
            client_id = websocket.client_id # Set after successful registration
            connection_type = "frontend" # Mark as frontend
            logger.info(f"WebSocket connection registered as frontend: {client_id}")
        else:
            logger.warning(f"Invalid first message type for WebSocket: {message_type}. Expected REGISTER_FRONTEND.")
            await websocket.send_text(json.dumps({
                "message_type": MessageType.ERROR,
                "text_payload": "Invalid registration message. Only frontend registration supported via WebSocket."
            }))
            await websocket.close(code=1008) # Policy Violation
            return # Close connection immediately

        # Only proceed if registration was successful
        if not client_id:
            logger.error("Registration failed or did not set client_id. Closing WebSocket.")
            await websocket.close(code=1011) # Internal Error
            return

        # Main message loop for the registered client (frontend)
        while True:
            message_str = await websocket.receive_text()
            message_data = json.loads(message_str)

            msg_type = message_data.get("message_type")

            if msg_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                await _handle_chat_message(websocket, client_id, message_data)
            elif msg_type == MessageType.CLIENT_DISCONNECTED:
                await _handle_client_disconnected_message(websocket, client_id, message_data)
            elif msg_type == MessageType.REQUEST_AGENT_STATUS:
                await _handle_request_agent_status(websocket, client_id, message_data)
            elif msg_type == MessageType.PAUSE_ALL_AGENTS:
                await _handle_pause_all_agents(websocket, client_id, message_data)
            elif msg_type == MessageType.RESUME_ALL_AGENTS:
                await _handle_RESUME_All_agents(websocket, client_id, message_data)
            elif msg_type == MessageType.PAUSE_AGENT:
                await _handle_pause_agent(websocket, client_id, message_data)
            elif msg_type == MessageType.RESUME_AGENT:
                await _handle_RESUME_Agent(websocket, client_id, message_data)
            elif msg_type == MessageType.DEREGISTER_ALL_AGENTS:
                await _handle_deregister_all_agents(websocket, client_id, message_data)
            elif msg_type == MessageType.DEREGISTER_AGENT:
                await _handle_deregister_agent(websocket, client_id, message_data)
            else:
                await _handle_unknown_message(websocket, client_id, message_data)

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_id} ({connection_type})")
    except Exception as e:
        logger.exception(f"Error in WebSocket handler for client {client_id} ({connection_type}): {e}")
    finally:
        if client_id:
            await _handle_disconnect(websocket, client_id)
        else:
            logger.info("WebSocket disconnected before registration completed.")
        try:
            await websocket.close()
        except RuntimeError as e:
            if "WebSocket is not connected" not in str(e):
                logger.warning(f"Error closing websocket during final cleanup: {e}")