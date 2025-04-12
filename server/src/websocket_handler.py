import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Set, Optional
import asyncio

from fastapi import WebSocket, WebSocketDisconnect

# Import shared models, config, state, and utils
from shared_models import MessageType, ResponseStatus, ChatMessage, setup_logging

import state
import rabbitmq_utils
import agent_manager
# Revert to direct import as main.py is run directly
import services


logger = setup_logging(__name__)

# Store client names
client_names: Dict[str, str] = {}

def generate_unique_id(client_type: str) -> str:
    """Generate a unique ID for a client based on their type."""
    unique_id = str(uuid.uuid4())[:8]  # Take first 8 characters of UUID
    return f"{client_type}_{unique_id}"



async def _handle_register_broker(websocket: WebSocket, message: dict) -> dict:
    """Handle broker registration."""
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
    
    # Create registration response
    response = {
        "message_type": MessageType.REGISTER_BROKER_RESPONSE,
        "status": ResponseStatus.SUCCESS,
        "broker_id": broker_id,
        "broker_name": broker_name,
        "message": "Broker registered successfully"
    }
    
    logger.debug(f"Sending registration response to broker: {response}")
    
    # Send a full agent status update immediately to this specific broker
    logger.info(f"Sending immediate full agent status update to new broker {broker_id}")
    await agent_manager.send_agent_status_to_broker()
    
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
    
    logger.debug(f"Broadcasting agent status after registration (full update)")
    await agent_manager.broadcast_agent_status(force_full_update=True, is_full_update=True)
    
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

    Also broadcasts these messages to all connected frontends before sending to RabbitMQ.
    """
    message_type = message_data.get("message_type", "UNKNOWN")
    # Add connection type metadata before forwarding
    message_data["_connection_type"] = getattr(websocket, "connection_type", "unknown")
    # Add client_id to the message
    message_data["_client_id"] = client_id
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
    """Main WebSocket endpoint handler."""
    client_id = None
    try:
        await websocket.accept()
        logger.info("New WebSocket connection accepted")
        
        # Add to active connections
        state.active_connections.add(websocket)
        
        # Initialize connection type
        websocket.connection_type = "unknown"
        
        # Main message loop
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                message_type = message.get("message_type")
                
                # Get client_id from websocket attribute or message
                client_id = getattr(websocket, "client_id", None) or message.get("client_id")
                
                if not client_id:
                    # Handle registration messages
                    if message_type == MessageType.REGISTER_AGENT:
                        logger.info(f"Received REGISTER_AGENT message from unregistered client: {message}")
                        response = await _handle_register_agent(websocket, message)
                        logger.info(f"Sending registration response to agent: {response}")
                        await websocket.send_text(json.dumps(response))
                    elif message_type == MessageType.REGISTER_BROKER:
                        logger.info(f"Received REGISTER_BROKER message from unregistered client")
                        response = await _handle_register_broker(websocket, message)
                        await websocket.send_text(json.dumps(response))
                    elif message_type == MessageType.REGISTER_FRONTEND:
                        logger.info(f"Received REGISTER_FRONTEND message from unregistered client")
                        response = await _handle_register_frontend(websocket, message)
                        await websocket.send_text(json.dumps(response))
                    else:
                        logger.warning(f"Received unregistered message type: {message_type}")
                        await websocket.send_text(json.dumps({
                            "message_type": MessageType.ERROR,
                            "text_payload": "Client must register first"
                        }))
                else:
                    # Handle registered client messages
                    if message_type == MessageType.PONG:
                        await _handle_pong(websocket, client_id, message)
                    elif message_type == MessageType.PING:
                        # Just respond with a PONG message
                        await websocket.send_text(json.dumps({
                            "message_type": MessageType.PONG,
                            "sender_id": "server"
                        }))
                        logger.debug(f"Received PING from {client_id}, sent PONG response")
                    elif message_type == MessageType.REQUEST_AGENT_STATUS:
                        await _handle_request_agent_status(websocket, client_id, message)
                    # Handle chat-related messages
                    elif message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                        await _handle_chat_message(websocket, client_id, message)
                    else:
                        logger.warning(f"Unknown message type from {client_id}: {message_type}")
                        
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from {client_id or 'unknown client'}")
                await websocket.send_text(json.dumps({
                    "message_type": MessageType.ERROR,
                    "text_payload": "Invalid JSON format"
                }))
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected during message handling: {client_id or 'unknown client'}")
                break
            except Exception as e:
                logger.error(f"Error processing message from {client_id or 'unknown client'}: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected during connection setup: {client_id or 'unknown client'}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Ensure proper cleanup is always performed
        logger.info(f"Performing cleanup for client: {client_id or 'unknown'}")
        if client_id:
            try:
                await _handle_disconnect(websocket, client_id)
            except Exception as e:
                logger.error(f"Error during disconnect handling for {client_id}: {e}")
        
        # Always make sure to remove from active connections
        state.active_connections.discard(websocket)
        state.frontend_connections.discard(websocket)
        
        # Log final confirmation of cleanup
        logger.info(f"WebSocket connection cleanup completed for: {client_id or 'unknown'}")