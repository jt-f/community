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

logger = logging.getLogger(__name__)

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
    await agent_manager.broadcast_agent_status(force_full_update=True)

async def _handle_pong(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles pong messages from agents."""
    agent_id = message_data.get("agent_id")
    if agent_id:
         agent_manager.handle_pong(agent_id)
    else:
         logger.warning(f"Received PONG without agent_id from {client_id}")

async def _handle_chat_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles standard chat, reply, and system messages."""
    message_type = message_data.get("message_type", "UNKNOWN")
    message_data["_connection_type"] = websocket.connection_type
    logger.debug(f"Forwarding {message_type} message from {client_id} ({websocket.connection_type}) to broker input queue.")
    if not rabbitmq_utils.publish_to_broker_input_queue(message_data):
        logger.error(f"Failed to publish incoming message from {client_id} to RabbitMQ.")
        error_resp = ChatMessage.create(
            sender_id="server",
            receiver_id=message_data.get("sender_id", client_id),
            text_payload="Error: Could not forward message to broker.",
            message_type=MessageType.ERROR
        )
        try: await websocket.send_text(error_resp.model_dump_json())
        except Exception: pass # Ignore error sending error message

async def _handle_client_disconnected_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles (unexpected) client disconnected messages."""
    logger.warning(f"Received unexpected CLIENT_DISCONNECTED message from {client_id}. Ignoring.")

async def _handle_unknown_message(websocket: WebSocket, client_id: str, message_data: Dict[str, Any]):
    """Handles unrecognized message types."""
    message_type = message_data.get("message_type", "UNKNOWN")
    logger.warning(f"Received unhandled message type '{message_type}' from {client_id}. Data: {message_data}")
    error_resp = ChatMessage.create(
        sender_id="server",
        receiver_id=message_data.get("sender_id", client_id),
        text_payload=f"Error: Unsupported message type '{message_type}' received.",
        message_type=MessageType.ERROR
    )
    try: await websocket.send_text(error_resp.model_dump_json())
    except Exception: pass

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
        MessageType.PONG: _handle_pong,
        MessageType.TEXT: _handle_chat_message,
        MessageType.REPLY: _handle_chat_message,
        MessageType.SYSTEM: _handle_chat_message,
        MessageType.CLIENT_DISCONNECTED: _handle_client_disconnected_message, 
    }

    try:
        while True:
            message_text = await websocket.receive_text()
            try:
                message_data = json.loads(message_text)
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from {client_id}: {message_text}")
                await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
                continue

            message_type_str = message_data.get("message_type")
            logger.debug(f"Received message from {client_id}: Type={message_type_str}")

            # Add client_id for potential response routing via RabbitMQ consumer
            message_data["_client_id"] = client_id
            
            # --- Dispatch to appropriate handler ---
            try:
                message_type = MessageType(message_type_str) # Validate against Enum
                handler = message_handlers.get(message_type, _handle_unknown_message)
            except ValueError: # Handle if message_type_str is not a valid MessageType member
                logger.warning(f"Received message with invalid message_type enum value: {message_type_str} from {client_id}")
                handler = _handle_unknown_message
            
            await handler(websocket, client_id, message_data)
                
    except WebSocketDisconnect as e:
        logger.info(f"WebSocket disconnected: {client_id} (Code: {e.code}, Reason: {e.reason})")
    except Exception as e:
        logger.exception(f"Unexpected error in WebSocket handler for {client_id}: {e}")
    finally:
        await _handle_disconnect(websocket, client_id) 