"""
WebSocket router for real-time communication.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import asyncio
from ..core.models import Message, WebSocketMessage
from ..utils.logger import get_logger
from ..utils.message_utils import truncate_message
from ..utils.id_generator import generate_short_id
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
                    timeout=0.2  # Increased timeout
                )

                # Validate message structure
                if not isinstance(data, dict):
                    logger.error(f"Invalid message format: {truncate_message(data)}")
                    continue
                
                # Log the received message safely
                message_id = data.get('data', {}).get('message_id', 'unknown')
                content = data.get('data', {}).get('content', {}).get('text', '')

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
                            content=message_data.get('content', {}),
                            message_id=message_data.get('message_id', generate_short_id()),
                            in_reply_to=message_data.get('in_reply_to')
                        )
                        

                        # Use the agent_server to process the message properly through the broker
                        # This ensures routing is handled by the broker's LLM-based logic
                        logger.debug(f"Agents: {', '.join([value.name+':'+value.agent_id for key, value in agent_server.agents.items()])}")
                        # Process the message through the agent server
                        try:
                            logger.info(f"message ({message.message_id}) received by backend websocket: sender={agent_server.agents[message.sender_id].name}, receiver={agent_server.agents[message.receiver_id].name}, content={truncate_message(message.content)}")
                            async for response in agent_server.process_message(message):
                                # Send each response back to the client
                                if isinstance(response, Message):
                                    response_data = {
                                        "type": "message",
                                        "data": response.model_dump()
                                    }
                                    await websocket.send_json(response_data)

                                    response_name = agent_server.agents[response_data.get('data').get('receiver_id')].name
                                    logger.info(f"message ({response_data.get('data').get('message_id')}) sent in response to {response_name}")
                                else:
                                    logger.warning(f"Unexpected response type: {type(response)}")
                        except Exception as e:
                            logger.error(f"Error processing message: {str(e)}")
                            # Send error message back to client
                            error_message = {
                                "type": "error",
                                "data": {
                                    "message": f"Error processing message: {str(e)}",
                                    "message_id": message.message_id
                                }
                            }
                            await websocket.send_json(error_message)
                else:
                    logger.info("Unexpected structure of message received from websocket")
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
                import traceback
                logger.error(
                    f"Error handling WebSocket message:\n"
                    f"Error type: {type(e).__name__}\n"
                    f"Error message: {str(e)}\n"
                    f"Traceback:\n{traceback.format_exc()}"
                )
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