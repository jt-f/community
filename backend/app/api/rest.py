"""
REST API router for HTTP endpoints.
"""
from typing import Dict, Optional, List, Any
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, HTTPException, status, Body
from pydantic import BaseModel, validator
from fastapi import Request  # Add this import

from ..core.instances import agent_server
from ..core.models import Message, AgentConfig
from ..utils.logger import get_logger
from ..utils.message_utils import truncate_message
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address
from ..utils.model_client import ModelProvider

from ..core.agents.config import ANALYST_CONFIG

logger = get_logger(__name__)

# Add MessageAPI class definition before it's used
class MessageAPI(BaseModel):
    """API model for HTTP message endpoints."""
    sender_id: str
    content: str
    recipient_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict] = None

    class Config:
        json_schema_extra = {
            "example": {
                "sender_id": "human",
                "content": "Hello, World!",
                "recipient_id": None,
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
router = APIRouter(prefix="/api", tags=["api"])

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
        
        logger.debug(f"Processing API message: {truncate_message(msg)}")
        
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
        logger.error(f"(post_message) Error processing message: {e} for message: {truncate_message(message.content)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/test")
async def test_endpoint():
    """Simple test endpoint to verify the API server is working."""
    return {"status": "ok", "message": "API server is working"}

@router.get("/agent-options")
async def get_agent_options():
    """Get available options for creating new agents."""
    
    # Log that this endpoint was called
    logger.debug("Agent options endpoint called")
    
    # Available agent types
    agent_types = [
        {"id": "analyst", "name": "Analyst Agent", "description": "Processes analysis requests and generates insights"}
    ]
    
    # Available model providers
    providers = [{"id": p.value, "name": p.name.capitalize()} for p in ModelProvider]
    
    # Available models per provider
    models = {
        "ollama": ["deepseek-r1:1.5b", "llama3:8b", "mistral:7b", "phi3:mini"],
        "mistral": ["mistral-tiny", "mistral-small", "mistral-medium", "mistral-large-latest"],
        "anthropic": ["claude-3-haiku-20240307", "claude-3-sonnet-20240229", "claude-3-opus-20240229"],
        "openai": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
        "together": ["mistralai/Mistral-7B-Instruct-v0.2", "meta-llama/Llama-2-70b-chat-hf"]
    }
    
    # Available capabilities
    capabilities = [
        {"id": "data_analysis", "name": "Data Analysis", "description": "Analyze data and extract insights"},
        {"id": "insight_generation", "name": "Insight Generation", "description": "Generate insights from information"},
        {"id": "llm_inference", "name": "LLM Inference", "description": "Run inference using language models"},
        {"id": "code_generation", "name": "Code Generation", "description": "Generate code based on requirements"},
        {"id": "text_summarization", "name": "Text Summarization", "description": "Summarize long texts"},
        {"id": "question_answering", "name": "Question Answering", "description": "Answer questions based on knowledge"}
    ]
    
    # Log the response
    logger.debug(f"Returning agent options: {len(agent_types)} agent types, {len(providers)} providers, {len(models)} model groups, {len(capabilities)} capabilities")
    
    return {
        "agent_types": agent_types,
        "providers": providers,
        "models": models,
        "capabilities": capabilities
    }

@router.post("/agents")
async def create_agent(agent_config: AgentConfig = Body(...)):
    """Create a new agent with the specified configuration."""
    try:
        # Create the agent based on the type
        if agent_config.agent_type == "analyst":
            from ..core.agents.analyst import AnalystAgent
            
            # Create a new analyst agent with the specified configuration
            agent = AnalystAgent(name=agent_config.name)
            
            # Set the model and provider
            agent.default_model = agent_config.model
            agent.model_provider = ModelProvider(agent_config.provider)
            
            # Set capabilities
            agent.capabilities = agent_config.capabilities
            
            # Register the agent with the agent server (this also adds it to the agent manager)
            await agent_server.register_agent(agent)
            
            # Log the successful agent creation
            logger.info(f"Created new agent: {agent.name} ({agent.agent_id}) of type {agent_config.agent_type}")
            
            return {"status": "success", "agent_id": agent.agent_id, "message": f"Agent {agent_config.name} created successfully"}
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported agent type: {agent_config.agent_type}")
    except Exception as e:
        logger.error(f"Failed to create agent: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")