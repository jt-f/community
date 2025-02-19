"""
REST API router for HTTP endpoints.
"""
from typing import Dict, Optional
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.server import agent_server
from ..core.models import Message
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")

class MessageAPI(BaseModel):
    """API model for HTTP message endpoints."""
    sender_id: str
    sender_name: str
    content: str
    recipient_id: Optional[str] = None
    recipient_name: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict] = None

    class Config:
        json_schema_extra = {
            "example": {
                "sender_id": "human",
                "sender_name": "Human",
                "content": "Hello, World!",
                "recipient_id": None,
                "recipient_name": None,
                "timestamp": datetime.now().isoformat(),
                "metadata": {}
            }
        }

@router.get("/")
async def root():
    """Get server status."""
    return {
        "status": "Server is running",
        "agents": len(agent_server.agents),
        "connections": len(agent_server.active_connections)
    }

@router.get("/agents")
async def list_agents():
    """List all agents in the system."""
    return {
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "capabilities": agent.capabilities
            }
            for agent in agent_server.agents.values()
        ]
    }

@router.post("/messages")
async def post_message(message: MessageAPI):
    """Send a message through HTTP POST."""
    try:
        msg = Message(
            id=str(uuid4()),
            timestamp=message.timestamp or datetime.now(),
            sender_id=message.sender_id,
            receiver_id=message.recipient_id,
            content={"text": message.content},
            message_type="text",
            metadata=message.metadata or {}
        )
        
        # Broadcast to all agents
        for agent in agent_server.agents.values():
            await agent.add_message(msg)
            
        return {"status": "success", "message_id": msg.id}
    except Exception as e:
        logger.error(f"(post_message) Error processing message: {e} for message: {message.content}")
        raise HTTPException(status_code=500, detail=str(e)) 