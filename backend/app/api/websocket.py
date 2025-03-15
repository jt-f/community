"""
WebSocket router for real-time communication.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import asyncio
from ..core.server import agent_server
from ..core.models import Message, WebSocketMessage
from ..utils.logger import get_logger
from ..core.instances import agent_manager

logger = get_logger(__name__)

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    try:
        await websocket.accept()
        logger.info("New WebSocket connection established")
        
        # Register the WebSocket with the agent server
        agent_server.register_websocket(websocket)
        
        # Send initial agent list
        agent_list = []
        all_agents = list(agent_manager.available_agents) + list(agent_manager.thinking_agents)
        logger.info(f"WebSocket connected. Sending {len(all_agents)} agents to client.")
        
        for agent in all_agents:
            agent_data = {
                "id": agent.agent_id,
                "name": agent.name,
                "type": agent.__class__.__name__.replace("Agent", "").lower(),
                "status": "thinking" if agent in agent_manager.thinking_agents else "idle",
                "capabilities": agent.capabilities if hasattr(agent, "capabilities") else [],
                "model": getattr(agent, "default_model", None),
                "provider": getattr(agent, "model_provider", None)
            }
            agent_list.append(agent_data)
            logger.debug(f"Adding agent to list: {agent_data}")
        
        message = {
            "type": "agent_list",
            "data": {
                "agents": agent_list
            }
        }
        logger.debug(f"Sending agent list: {message}")
        await websocket.send_json(message)
        
        # Ensure the connection is properly established
        if websocket.application_state != WebSocketState.CONNECTED:
            logger.error("WebSocket not in CONNECTED state after accept")
            return
            
        while True:
            try:
                # Check connection state before receiving
                if websocket.application_state != WebSocketState.CONNECTED:
                    logger.error("WebSocket connection lost")
                    break

                # Use asyncio.wait_for to add a timeout to receive_json
                try:
                    logger.debug("Waiting for message...")
                    data = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=0.1  # 100ms timeout
                    )
                    logger.info(f"Received WebSocket message: {data}")
                    
                    # Validate message structure
                    if not isinstance(data, dict):
                        logger.error(f"Invalid message format: {data}")
                        continue
                        
                    # Check if the message has the expected structure
                    if 'type' in data and 'data' in data:
                        # Handle the message based on its type
                        if data['type'] == 'message':
                            # Extract the message data
                            message_data = data['data']
                            
                            # Create a Message object
                            message = Message(
                                sender_id=message_data.get('sender_id', 'unknown'),
                                receiver_id=message_data.get('receiver_id'),
                                message_type=message_data.get('message_type', 'text'),
                                content=message_data.get('content', {})
                            )
                            
                            # Route the message to the appropriate agent
                            for agent in list(agent_manager.available_agents) + list(agent_manager.thinking_agents):
                                if agent.agent_id == message.receiver_id:
                                    await agent.enqueue_message(message)
                                    logger.info(f"Routed message to agent {agent.name} ({agent.agent_id})")
                                    break
                    else:
                        # For backward compatibility, try to handle the old format
                        logger.warning(f"Message missing 'type' or 'data' fields: {data}")
                        
                        # Try to create a Message object directly from the data
                        try:
                            message = Message(
                                sender_id=data.get('sender_id', 'unknown'),
                                receiver_id=data.get('receiver_id'),
                                message_type=data.get('message_type', 'text'),
                                content=data.get('content', {})
                            )
                            
                            # Route the message to the appropriate agent
                            for agent in list(agent_manager.available_agents) + list(agent_manager.thinking_agents):
                                if agent.agent_id == message.receiver_id:
                                    await agent.enqueue_message(message)
                                    logger.info(f"Routed message to agent {agent.name} ({agent.agent_id})")
                                    break
                        except Exception as e:
                            logger.error(f"Error handling legacy message format: {e}")

                except asyncio.TimeoutError:
                    # This is expected, just continue the loop
                    continue
                except WebSocketDisconnect:
                    logger.info("WebSocket connection closed by client")
                    break
                        
            except WebSocketDisconnect:
                logger.info("WebSocket connection closed by client")
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                if websocket.application_state != WebSocketState.CONNECTED:
                    logger.info("Connection lost during message handling")
                    break
                continue
                
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed during handshake")
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        logger.info("Cleaning up WebSocket connection")
        try:
            # Unregister the WebSocket from the agent server
            agent_server.unregister_websocket(websocket)
            # Don't try to close the connection here, it's already closed or will be closed by FastAPI
        except Exception as e:
            logger.error(f"Error during WebSocket cleanup: {e}") 