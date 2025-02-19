"""
WebSocket router for real-time communication.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import asyncio
from ..core.server import agent_server
from ..core.models import Message, WebSocketMessage
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    try:
        await websocket.accept()
        logger.info("New WebSocket connection established")
        
        # Register with agent server after accepting the connection
        await agent_server.connect(websocket)
        logger.info("Connected to agent server")
        
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
                        
                    if 'type' not in data or 'data' not in data:
                        logger.error(f"Missing required fields in message: {data}")
                        continue
                    
                    # Create WebSocket message
                    message = None
                    try:
                        message = WebSocketMessage(
                            type=data['type'],
                            data=data['data']
                        )
                        
                        if message.type == "message":
                            # Handle agent messages
                            msg_data = Message(**message.data)
                            # Route the message to appropriate agents
                            await agent_server.route_message(msg_data)
                            # Broadcast the message to all WebSocket clients
                            await agent_server.broadcast(message)
                            logger.info("Message processed and broadcast complete")
                            
                    except Exception as e:
                        error_msg = f"Error processing message: {e}"
                        if message:
                            error_msg += f" for message: {message.data}"
                        logger.error(error_msg)
                        continue

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
        # Always ensure we clean up the connection
        try:
            logger.info("Cleaning up WebSocket connection")
            await agent_server.disconnect(websocket)
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close()
            logger.info("WebSocket connection cleaned up")
        except Exception as e:
            logger.error(f"Error during WebSocket cleanup: {e}") 