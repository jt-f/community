from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import json
from typing import List, Dict, Optional, Set
import asyncio
from datetime import datetime
from community import Community
from message import Message as CommunityMessage
from test_agents import create_test_agents

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Community Flow")

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

# Connection manager
class ConnectionManager:
    def __init__(self):
        self.reset_state()
        
    def reset_state(self):
        """Reset all state to initial values"""
        self.active_connections = set()
        self.community = Community("Main Community")
        self.started = False
        logger.info("Connection manager state reset")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")
        
        # If this is the first connection after a reset, initialize the community
        if not self.started:
            await self.initialize_community()
            
        # Send current state to the new client
        try:
            current_state = {
                "type": "state_update",
                "data": {
                    agent.id: {
                        "id": agent.id,
                        "name": agent.name,
                        "status": "idle",  # We should track this in the agent class
                        "queue_size": len(agent.message_queue),
                        "capabilities": agent.capabilities,
                        "last_activity": datetime.now().isoformat()
                    }
                    for agent in self.community.agents.values()
                }
            }
            logger.debug(f"Sending current state to new client: {current_state}")
            await websocket.send_json(current_state)
        except Exception as e:
            logger.error(f"Error sending current state: {e}")
            await self.disconnect(websocket)

    async def initialize_community(self):
        """Initialize the community with fresh agents"""
        # Clear any existing agents
        self.community = Community("Main Community")
        
        # Create fresh test agents
        test_agents = create_test_agents()
        for agent in test_agents:
            self.community.add_agent(agent)
            logger.info(f"Added agent {agent.name} to community")
        
        # Start the community
        await self.community.start()
        asyncio.create_task(self.community.run())
        self.started = True
        logger.info(f"Community initialized with {len(self.community.agents)} agents")

    async def disconnect(self, websocket: WebSocket):
        """Safely disconnect a WebSocket connection"""
        try:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                try:
                    await websocket.close()
                except RuntimeError as e:
                    # Ignore "Already closed" errors
                    if "already completed" not in str(e):
                        logger.error(f"Error closing websocket: {e}")
                logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")
                
                # If this was the last connection, reset the state
                if not self.active_connections:
                    self.reset_state()
                    logger.info("Last client disconnected, state reset")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            # Ensure connection is removed even if there's an error
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: CommunityMessage):
        # Add timestamp if not present
        if not message.timestamp:
            message.timestamp = datetime.now()
            
        # Send to monitoring
        flow_message = {
            "type": "message",
            "data": {
                "sender_id": message.sender_id,
                "sender_name": message.sender_name,
                "content": message.content,
                "recipient_id": message.recipient_id,
                "timestamp": message.timestamp.isoformat()
            }
        }
            
        # Make a copy of connections to safely iterate
        current_connections = self.active_connections.copy()
        dead_connections = set()
        
        # Send to WebSocket clients
        for connection in current_connections:
            try:
                if connection in self.active_connections:  # Double check connection is still active
                    await connection.send_json(flow_message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                dead_connections.add(connection)
                
        # Clean up dead connections
        for dead_conn in dead_connections:
            await self.disconnect(dead_conn)
                
        # Send to community
        await self.community.broadcast_message(message)

manager = ConnectionManager()

@app.get("/")
async def root():
    return {
        "status": "Server is running",
        "community_name": manager.community.name,
        "agents": len(manager.community.agents),
        "connections": len(manager.active_connections)
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
            for agent in manager.community.agents.values()
        ]
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await manager.connect(websocket)
        
        # Send welcome message
        welcome_msg = CommunityMessage(
            sender_id="system",
            sender_name="System",
            content="Connected to server",
            timestamp=datetime.now()
        )
        await manager.broadcast(welcome_msg)
        
        # Handle messages
        while True:
            try:
                data = await websocket.receive_json()
                logger.info(f"Received message: {data}")
                message = CommunityMessage(**data)
                await manager.broadcast(message)
            except json.JSONDecodeError:
                logger.error("Invalid JSON received")
                continue
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected normally")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during setup")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # First disconnect the websocket
        await manager.disconnect(websocket)
        
        # Only try to broadcast disconnect message if we still have active connections
        if manager.active_connections:
            try:
                disconnect_msg = CommunityMessage(
                    sender_id="system",
                    sender_name="System",
                    content="Client disconnected",
                    timestamp=datetime.now()
                )
                await manager.broadcast(disconnect_msg)
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
        
        logger.info(f"Received HTTP message: {community_message}")
        await manager.broadcast(community_message)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server on http://172.19.36.55:8000")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    ) 