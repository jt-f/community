"""
WebSocket router for real-time communication.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import asyncio
from ..core.models import Message, WebSocketMessage
from ..utils.logger import get_logger
from ..utils.message_utils import truncate_message
from ..core.instances import agent_server

logger = get_logger(__name__)

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    try:
        await websocket.accept()
        logger.debug("New WebSocket connection established")
        
        # Register the WebSocket with the agent server
        if asyncio.iscoroutinefunction(agent_server.register_websocket):
            await agent_server.register_websocket(websocket)
        else:
            logger.debug("Using non-coroutine method for agent_server.register_websocket")
            agent_server.register_websocket(websocket)
        
        # Send initial agent list
        try:
            agent_list = []
            all_agents = list(agent_server.agent_manager.available_agents) + list(agent_server.agent_manager.thinking_agents)
            logger.debug(f"WebSocket connected. Sending {len(all_agents)} agents to client.")
            
            for agent in all_agents:
                agent_data = {
                    "id": agent.agent_id,
                    "name": agent.name,
                    "type": agent.__class__.__name__.replace("Agent", "").lower(),
                    "status": "thinking" if agent in agent_server.agent_manager.thinking_agents else "idle",
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
        except Exception as e:
            logger.error(f"Error sending initial agent list: {str(e)}")
            return
            
        while True:
            if websocket.application_state != WebSocketState.CONNECTED:
                logger.error("WebSocket connection lost")
                break

            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=1.0  # Increased timeout
                )

                # Validate message structure
                if not isinstance(data, dict):
                    logger.error(f"Invalid message format: {truncate_message(data)}")
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
                        
                        # Log the message details for debugging
                        logger.debug(f"Created message object: sender={message.sender_id}, receiver={message.receiver_id}, content={truncate_message(message.content)}")
                        
                        # Route the message to the appropriate agent
                        for agent in list(agent_server.agent_manager.available_agents) + list(agent_server.agent_manager.thinking_agents):
                            if agent.agent_id == message.receiver_id:
                                await agent.message_queue.put(message)
                                logger.info(f"Agent {agent.name} received message: {truncate_message(message.content.get('text','None'))}")
                                break
            except asyncio.TimeoutError:
                if websocket.application_state != WebSocketState.CONNECTED:
                    break
                continue
            except asyncio.CancelledError:
                logger.debug("WebSocket operation cancelled")
                break
            except WebSocketDisconnect:
                logger.debug("WebSocket connection closed by client")
                break
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {str(e)}")
                if websocket.application_state != WebSocketState.CONNECTED:
                    break
                continue
                
    except WebSocketDisconnect:
        logger.debug("WebSocket connection closed during handshake")
    except asyncio.CancelledError:
        logger.debug("WebSocket connection cancelled")
    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
    finally:
        logger.debug("Cleaning up WebSocket connection")
        try:
            # Modified to handle non-coroutine method
            if asyncio.iscoroutinefunction(agent_server.unregister_websocket):
                await agent_server.unregister_websocket(websocket)
            else:
                agent_server.unregister_websocket(websocket)
        except Exception as e:
            logger.error(f"Error during WebSocket cleanup: {str(e)}")