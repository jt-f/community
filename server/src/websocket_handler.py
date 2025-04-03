import logging
import json
import uuid
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

# Import shared models, config, state, and utils
from shared_models import MessageType, ResponseStatus, AgentRegistrationResponse, ChatMessage
import config
import state
import rabbitmq_utils
import agent_manager

logger = logging.getLogger(__name__)

async def websocket_endpoint(websocket: WebSocket):
    """Handles incoming WebSocket connections and messages."""
    await websocket.accept()
    # Assign a unique ID for tracking/debugging
    client_id = f"client_{uuid.uuid4().hex[:8]}"
    websocket.client_id = client_id  
    websocket.connection_type = "unknown" # Updated upon registration
    state.active_connections.add(websocket)
    logger.info(f"WebSocket connection accepted: {client_id}")

    try:
        while True:
            message_text = await websocket.receive_text()
            try:
                message_data = json.loads(message_text)
            except json.JSONDecodeError:
                logger.warning(f"Received invalid JSON from {client_id}: {message_text}")
                # Optionally send an error message back
                await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
                continue # Skip processing this message

            message_type = message_data.get("message_type")
            logger.debug(f"Received message from {client_id}: Type={message_type}")

            # Add client_id for potential response routing via RabbitMQ consumer
            message_data["_client_id"] = client_id
            
            # --- Message Handling Logic --- 
            
            if message_type == MessageType.REGISTER_BROKER:
                websocket.connection_type = "broker"
                state.broker_connection = websocket
                logger.info(f"Broker registered: {client_id}")
                # Send current ACTIVE agent status list to the newly connected broker
                await agent_manager.send_agent_status_to_broker()
            
            elif message_type == MessageType.REGISTER_AGENT:
                websocket.connection_type = "agent"
                agent_id = message_data.get("agent_id")
                agent_name = message_data.get("agent_name", "UnknownAgent")
                
                if not agent_id:
                    logger.error(f"Agent registration from {client_id} missing agent_id.")
                    # Send error response
                    await websocket.send_text(json.dumps({"error": "Missing agent_id"}))
                    continue

                # Store agent connection
                state.agent_connections[agent_id] = websocket
                logger.info(f"Agent {agent_name} ({agent_id}) registered via WebSocket: {client_id}")
                
                # Update agent status (now managed by agent_manager)
                agent_manager.update_agent_status(agent_id, agent_name, is_online=True)
                
                # Forward registration message to broker via RabbitMQ
                rabbitmq_utils.publish_to_agent_metadata_queue(message_data)
                
                # Send registration success response back to agent
                response = AgentRegistrationResponse(
                    status=ResponseStatus.SUCCESS,
                    agent_id=agent_id,
                    message="Agent registered with server successfully"
                )
                await websocket.send_text(response.model_dump_json())
                
                # Broadcast updated status (full update) to all clients/broker
                await agent_manager.broadcast_agent_status(force_full_update=True)
                    
            elif message_type == MessageType.REGISTER_FRONTEND:
                websocket.connection_type = "frontend"
                state.frontend_connections.add(websocket)
                logger.info(f"Frontend client registered: {client_id}")
                # Send full agent status immediately upon registration
                await agent_manager.broadcast_agent_status(force_full_update=True)
                    
            elif message_type == MessageType.PONG:
                agent_id = message_data.get("agent_id")
                if agent_id:
                     agent_manager.handle_pong(agent_id)
                else:
                     logger.warning(f"Received PONG without agent_id from {client_id}")
                    
            # Handle standard chat/reply/system messages
            elif message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                # Add connection type metadata before forwarding
                message_data["_connection_type"] = websocket.connection_type 
                logger.debug(f"Forwarding {message_type} message from {client_id} ({websocket.connection_type}) to incoming queue.")
                if not rabbitmq_utils.publish_to_incoming_queue(message_data):
                    logger.error(f"Failed to publish incoming message from {client_id} to RabbitMQ.")
                    # Optionally notify sender of the error
                    error_resp = ChatMessage.create(
                        sender_id="server",
                        receiver_id=message_data.get("sender_id", client_id), # Send back to sender
                        text_payload="Error: Could not forward message to broker.",
                        message_type=MessageType.ERROR
                    )
                    try: await websocket.send_text(error_resp.model_dump_json()) 
                    except: pass # Ignore error sending error message
            
            # Handle other known message types if necessary (e.g., CLIENT_DISCONNECTED? unlikely from client)
            elif message_type == MessageType.CLIENT_DISCONNECTED:
                 logger.warning(f"Received unexpected CLIENT_DISCONNECTED message from {client_id}. Ignoring.")

            # Handle unrecognized message types
            else:
                logger.warning(f"Received unhandled message type '{message_type}' from {client_id}. Data: {message_data}")
                # Optionally send an error message back
                error_resp = ChatMessage.create(
                    sender_id="server",
                    receiver_id=message_data.get("sender_id", client_id),
                    text_payload=f"Error: Unsupported message type '{message_type}' received.",
                    message_type=MessageType.ERROR
                )
                try: await websocket.send_text(error_resp.model_dump_json()) 
                except: pass
                
    except WebSocketDisconnect as e:
        logger.info(f"WebSocket disconnected: {client_id} (Code: {e.code}, Reason: {e.reason})")
        # Handle cleanup in finally block
    except Exception as e:
        # Log unexpected errors during the connection loop
        logger.exception(f"Unexpected error in WebSocket handler for {client_id}: {e}")
        # Ensure cleanup happens even if loop breaks unexpectedly
    finally:
        # --- WebSocket Cleanup Logic --- 
        logger.info(f"Cleaning up connection for {client_id} ({websocket.connection_type})")
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
            # Find agent_id associated with this websocket
            for agent_id, ws in list(state.agent_connections.items()):
                if ws == websocket:
                    disconnected_agent_id = agent_id
                    del state.agent_connections[agent_id]
                    logger.info(f"Agent connection closed: {client_id} (Agent ID: {agent_id})")
                    break # Found the agent
            
            if disconnected_agent_id:
                 # Mark agent as offline in the central status dict
                 agent_manager.mark_agent_offline(disconnected_agent_id)
                 needs_status_broadcast = True
                 
                 # Notify broker about agent disconnection via RabbitMQ
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

        # If an agent disconnected, broadcast the updated status
        if needs_status_broadcast:
            logger.info(f"Broadcasting status update after agent {disconnected_agent_id} disconnect.")
            await agent_manager.broadcast_agent_status()
        
        # Attempt to close if not already closed (though usually handled by disconnect exception)
        try:
            await websocket.close()
        except RuntimeError as e:
            # Ignore errors like "WebSocket is already closed"
             if "closed" not in str(e).lower(): 
                  logger.debug(f"Error during final WebSocket close for {client_id}: {e}")
        except Exception as e:
             logger.debug(f"Unexpected error during final WebSocket close for {client_id}: {e}") 