"""
REST API router for HTTP endpoints.
"""
from typing import Dict, Optional
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, validator
from fastapi import Request  # Add this import

from ..core.server import agent_server
from ..core.models import Message
from ..utils.logger import get_logger
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = get_logger(__name__)

# Add MessageAPI class definition before it's used
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

# Define APIResponse model
class APIResponse(BaseModel):
    status: str
    data: Optional[Dict] = None
    error: Optional[str] = None

# Create router instance
router = APIRouter(prefix="/api")

# Setup rate limiter and API key
limiter = Limiter(key_func=get_remote_address)
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != "your-secret-key":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return api_key

# Then modify your routes to include rate limiting and authentication
@router.post("/messages", response_model=APIResponse)
@limiter.limit("5/minute")  # Adjust rate limit as needed
async def post_message(
    request: Request,  # Add request parameter
    message: MessageAPI,
    api_key: str = Depends(verify_api_key)
):
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
        failed_agents = []
        for agent in agent_server.agents.values():
            try:
                await agent.add_message(msg)
            except Exception as e:
                failed_agents.append(agent.id)
                logger.error(f"Failed to send message to agent {agent.id}: {e}")
        
        if failed_agents:
            return APIResponse(
                status="partial_success",
                data={"message_id": msg.id},
                error=f"Failed to deliver to agents: {', '.join(failed_agents)}"
            )
            
        return APIResponse(
            status="success",
            data={"message_id": msg.id}
        )
    except Exception as e:
        logger.error(f"(post_message) Error processing message: {e} for message: {message.content}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )