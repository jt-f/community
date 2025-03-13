from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import uuid

class ModelProvider(str, Enum):
    """Supported model providers."""
    OLLAMA = "ollama"
    MISTRAL = "mistral"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    TOGETHER = "together"

class AgentConfig(BaseModel):
    """Configuration for creating a new agent."""
    name: str
    agent_type: str
    model: str
    provider: str
    capabilities: List[str]
    parameters: Optional[Dict[str, Any]] = None

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/test")
async def test_endpoint():
    """Simple test endpoint."""
    return {"status": "ok", "message": "API server is working"}

@app.get("/api/agent-options")
async def get_agent_options():
    """Get available options for creating new agents."""
    
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
    
    return {
        "agent_types": agent_types,
        "providers": providers,
        "models": models,
        "capabilities": capabilities
    }

@app.post("/api/agents")
async def create_agent(agent_config: AgentConfig = Body(...)):
    """Create a new agent with the specified configuration."""
    try:
        # Just return a success response with a generated agent ID
        agent_id = str(uuid.uuid4())
        return {"status": "success", "agent_id": agent_id, "message": f"Agent {agent_config.name} created successfully"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 