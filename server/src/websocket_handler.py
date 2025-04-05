import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any

from fastapi import WebSocket, WebSocketDisconnect

# Import shared models, config, state, and utils
from shared_models import MessageType, ResponseStatus, AgentRegistrationResponse, ChatMessage
import config
import state
import rabbitmq_utils
import agent_manager
# Revert to direct import as main.py is run directly
import services

logger = logging.getLogger(__name__)

# --- WebSocket Send Helper (_safe_send_websocket is now in services.py) ---

# --- Error Response Helper (Removed as previous request was rejected) ---

# --- Helper Functions for Message Handling ---

async def _handle_register_broker(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles broker registration."""
    websocket.connection_type = "broker"
    state.broker_connection = websocket
    logger.info(f"Broker registered: {client_id}")
    # Send current ACTIVE agent status list to the newly connected broker
    await agent_manager.send_agent_status_to_broker()

async def _handle_register_agent(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles agent registration."""
    websocket.connection_type = "agent"
    agent_id = message_data.get("agent_id")
    agent_name = message_data.get("agent_name", "UnknownAgent")
    
    if not agent_id:
        logger.error(f"Agent registration from {client_id} missing agent_id.")
        await websocket.send_text(json.dumps({"error": "Missing agent_id"}))
        return

    state.agent_connections[agent_id] = websocket
    logger.info(f"Agent {agent_name} ({agent_id}) registered via WebSocket: {client_id}")
    
    agent_manager.update_agent_status(agent_id, agent_name, is_online=True)
    rabbitmq_utils.publish_to_agent_metadata_queue(message_data)
    
    response = AgentRegistrationResponse(
        status=ResponseStatus.SUCCESS,
        agent_id=agent_id,
        message="Agent registered with server successfully"
    )
    await websocket.send_text(response.model_dump_json())
    await agent_manager.broadcast_agent_status(force_full_update=True)

async def _handle_register_frontend(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles frontend client registration."""
    websocket.connection_type = "frontend"
    state.frontend_connections.add(websocket)
    logger.info(f"Frontend client registered: {client_id}")
    # Send ACK back to frontend with its assigned client_id
    ack_message = {
        "message_type": "REGISTER_FRONTEND_ACK",
        "client_id": client_id,
        "status": "success"
    }
    try:
        await services._safe_send_websocket(websocket, json.dumps(ack_message), f"frontend client {client_id}")
        logger.info(f"Sent REGISTER_FRONTEND_ACK to {client_id}")
    except Exception as e:
        logger.error(f"Failed to send REGISTER_FRONTEND_ACK to {client_id}: {e}")
        # Proceed with status broadcast even if ACK fails

    # Send full agent status immediately upon registration
    await agent_manager.broadcast_agent_status(force_full_update=True)

async def _handle_pong(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles pong messages from agents."""
    agent_id = message_data.get("agent_id")
    if agent_id:
         agent_manager.handle_pong(agent_id)
    else:
         logger.warning(f"Received PONG without agent_id from {client_id}")

async def _handle_chat_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles standard chat, reply, and system messages.

    Also broadcasts these messages to all connected frontends before sending to RabbitMQ.
    """
    message_type = message_data.get("message_type", "UNKNOWN")
    # Add connection type metadata before forwarding
    message_data["_connection_type"] = getattr(websocket, "connection_type", "unknown")
    logger.debug(f"Processing {message_type} from {client_id} ({message_data['_connection_type']}).")

    # --- Broadcast to all connected Frontends FIRST --- 
    payload_str = json.dumps(message_data)
    disconnected_frontend = set()
    frontend_count = len(state.frontend_connections)
    if frontend_count > 0:
        logger.info(f"Broadcasting incoming {message_type} from {client_id} to {frontend_count} frontend clients.")
        for fe_ws in list(state.frontend_connections):
            fe_client_desc = f"frontend client {getattr(fe_ws, 'client_id', '?')}"
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
        # Reverted: Optionally notify sender of the error
        error_resp = ChatMessage.create(
            sender_id="server",
            receiver_id=message_data.get("sender_id", client_id), # Send back to sender
            text_payload="Error: Could not forward message to broker.",
            message_type=MessageType.ERROR
        )
        try: 
            await websocket.send_text(error_resp.model_dump_json()) 
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
    """Handles agent status requests specifically from the broker."""
    if getattr(websocket, 'connection_type', None) == "broker":
        logger.info(f"Broker ({client_id}) requested agent status via WebSocket.")
        # Call the function that now sends the response via WebSocket
        await agent_manager.send_agent_status_to_broker()
    else:
        logger.warning(f"Received REQUEST_AGENT_STATUS from non-broker client: {client_id} ({getattr(websocket, 'connection_type', 'unknown')}). Ignoring.")
        # Optionally send an error back to the sender
        error_resp = {
            "message_type": MessageType.ERROR,
            "text_payload": "Only the broker can request agent status.",
            "sender_id": "server"
        }
        try:
            await websocket.send_text(json.dumps(error_resp))
        except Exception as e:
             logger.error(f"Failed to send 'broker only' error to client {client_id}: {e}")

# --- Helper Function for Disconnect Cleanup ---

async def _handle_disconnect(websocket: WebSocket, client_id: str):
    """Handles cleanup when a WebSocket connection is closed."""
    logger.info(f"Cleaning up connection for {client_id} ({getattr(websocket, 'connection_type', 'unknown')})")
    state.active_connections.discard(websocket)
    
    connection_type = getattr(websocket, "connection_type", "unknown")
    needs_status_broadcast = False
    disconnected_agent_id = None
    
    if connection_type == "broker" and websocket == state.broker_connection:
        state.broker_connection = None
        logger.info(f"Broker connection closed: {client_id}")
        
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
             disconnect_message = {
                 "message_type": MessageType.CLIENT_DISCONNECTED,
                 "agent_id": disconnected_agent_id,
                 "connection_type": "agent",
             }
             rabbitmq_utils.publish_to_agent_metadata_queue(disconnect_message)
             logger.info(f"Published disconnect notification for agent {disconnected_agent_id} to agent metadata queue.")
        else:
             logger.warning(f"Could not find agent_id for disconnected agent websocket {client_id}")

    else: # connection_type unknown
        logger.warning(f"Connection closed for client {client_id} with unknown type.")

    if needs_status_broadcast:
        logger.info(f"Broadcasting status update after agent {disconnected_agent_id} disconnect.")
        await agent_manager.broadcast_agent_status()
    
    # Attempt to close gracefully
    try:
        await websocket.close()
    except RuntimeError as e:
         if "closed" not in str(e).lower(): 
              logger.debug(f"Error during final WebSocket close for {client_id}: {e}")
    except Exception as e:
         logger.debug(f"Unexpected error during final WebSocket close for {client_id}: {e}")

# --- Main WebSocket Endpoint ---

async def websocket_endpoint(websocket: WebSocket):
    """Handles incoming WebSocket connections and messages."""
    await websocket.accept()
    client_id = f"client_{uuid.uuid4().hex[:8]}"
    websocket.client_id = client_id  # type: ignore [attr-defined] # Add custom attribute
    websocket.connection_type = "unknown" # type: ignore [attr-defined] # Updated upon registration
    state.active_connections.add(websocket)
    logger.info(f"WebSocket connection accepted: {client_id}")

    # Map message types to handler functions
    message_handlers = {
        MessageType.REGISTER_BROKER: _handle_register_broker,
        MessageType.REGISTER_AGENT: _handle_register_agent,
        MessageType.REGISTER_FRONTEND: _handle_register_frontend,
        MessageType.REQUEST_AGENT_STATUS: _handle_request_agent_status,
        MessageType.PONG: _handle_pong,
        MessageType.TEXT: _handle_chat_message,
        MessageType.REPLY: _handle_chat_message,
        MessageType.SYSTEM: _handle_chat_message,
        MessageType.CLIENT_DISCONNECTED: _handle_client_disconnected_message, 
    }

    try:
        while True:
            message_text = await websocket.receive_text()
            message_data = None # Initialize for error handling scope
            try:
                message_data = json.loads(message_text)
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from {client_id}: {message_text}")
                # Reverted: Optionally send an error message back
                try: await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
                except Exception as e: logger.error(f"Failed to send invalid JSON error to {client_id}: {e}")
                continue # Skip processing this message

            message_type_str = message_data.get("message_type")
            logger.debug(f"Received message from {client_id}: Type={message_type_str}")

            # Add client_id for potential response routing via RabbitMQ consumer
            message_data["_client_id"] = client_id
            
            # --- Dispatch to appropriate handler ---
            try:
                # Attempt to convert string to MessageType Enum
                message_type_enum = MessageType(message_type_str)
                handler = message_handlers.get(message_type_enum, _handle_unknown_message)
            except ValueError:
                # Handle cases where message_type_str is not a valid member of MessageType
                error_text = f"Error: Invalid message type value '{message_type_str}' received."
                logger.warning(f"{error_text} from {client_id}")
                # Reverted: Send simple error back
                error_resp = ChatMessage.create(
                    sender_id="server",
                    receiver_id=message_data.get("sender_id", client_id),
                    text_payload=error_text,
                    message_type=MessageType.ERROR
                 )
                try: await websocket.send_text(error_resp.model_dump_json())
                except Exception as e: logger.error(f"Failed to send invalid message type error to {client_id}: {e}")
                continue # Skip further processing for this invalid message type

            await handler(websocket, client_id, message_data)
                
    except WebSocketDisconnect as e:
        logger.info(f"WebSocket disconnected: {client_id} (Code: {e.code}, Reason: {e.reason})")
    except Exception as e:
        logger.exception(f"Unexpected error in WebSocket handler for {client_id}: {e}")
    finally:
        await _handle_disconnect(websocket, client_id) 