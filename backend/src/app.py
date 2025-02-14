from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import json
from typing import List, Dict, Optional, Set
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from message import Message as CommunityMessage
from community import Community

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize community
community = Community("Main Community")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize and start the community
    logger.info("Starting up community...")
    await community.start()
    logger.info("Community started successfully")
    yield
    # Shutdown: Clean up resources
    logger.info("Shutting down community...")
    await community.stop()
    logger.info("Community shutdown complete")

app = FastAPI(title="Community Flow", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Message model for API
class MessageAPI(BaseModel):
    sender_id: str
    sender_name: str
    content: str
    recipient_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict] = None

    class Config:
        json_schema_extra = {
            "example": {
                "sender_id": "human",
                "sender_name": "Human",
                "content": "Hello, World!",
                "recipient_id": None,
                "timestamp": datetime.now().isoformat(),
                "metadata": {}
            }
        }

@app.get("/")
async def root():
    return {
        "status": "Server is running",
        "community_name": community.name,
        "agents": len(community.agents),
        "connections": len(community.active_connections)
    }

@app.get("/agents")
async def list_agents():
    """List all agents in the community"""
    return {
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "capabilities": agent.capabilities
            }
            for agent in community.agents.values()
        ]
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await community.connect(websocket)
        
        # Send welcome message
        welcome_msg = CommunityMessage(
            sender_id="system",
            sender_name="System",
            content="Connected to server",
            timestamp=datetime.now()
        )
        await community.route_message(welcome_msg)
        
        # Handle messages
        while True:
            try:
                data = await websocket.receive_json()
                logger.debug(f"Received message: {data}")
                message = CommunityMessage(**data)
                await community.route_message(message)
            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                continue
            except WebSocketDisconnect:
                logger.debug("WebSocket disconnected normally")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                break
                
    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected during setup")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # First disconnect the websocket
        await community.disconnect(websocket)
        
        # Only try to broadcast disconnect message if we still have active connections
        if community.active_connections:
            try:
                disconnect_msg = CommunityMessage(
                    sender_id="system",
                    sender_name="System",
                    content="Client disconnected",
                    timestamp=datetime.now()
                )
                await community.route_message(disconnect_msg)
            except Exception as e:
                logger.error(f"Error sending disconnect message: {e}")

@app.post("/message")
async def post_message(message: MessageAPI):
    """Send a message through HTTP POST"""
    try:
        # Convert MessageAPI to CommunityMessage
        community_message = CommunityMessage(
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            content=message.content,
            recipient_id=message.recipient_id,
            timestamp=message.timestamp or datetime.now(),
            metadata=message.metadata or {}
        )
        
        logger.debug(f"Received HTTP message: {community_message}")
        await community.route_message(community_message)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    import signal
    import sys

    def signal_handler(sig, frame):
        logger.info("Shutdown signal received, stopping server...")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    config = uvicorn.Config(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    
    try:
        logger.debug("Starting server on http://172.19.36.55:8000")
        server.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal, stopping server...")
    finally:
        logger.info("Server shutdown complete") 