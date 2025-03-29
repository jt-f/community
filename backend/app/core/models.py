"""
Core data models for the agent system.
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator
from app.utils.id_generator import generate_short_id

class MessageType(str, Enum):
    TEXT = "text"
    ERROR = "error"
    STATUS = "status"
    THINKING = "thinking"
    
class Message(BaseModel):
    """Message model for communication between agents."""
    sender_id: str
    receiver_id: Optional[str] = None
    content: Dict[str, Any]
    message_type: str = MessageType.TEXT
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    message_id: str = Field(default_factory=generate_short_id)
    in_reply_to: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @model_validator(mode='before')
    @classmethod
    def validate_datetime(cls, data: Dict) -> Dict:
        """Convert datetime objects to ISO format strings."""
        if isinstance(data.get('timestamp'), datetime):
            data['timestamp'] = data['timestamp'].isoformat()
        
        # Also check content and metadata for datetime objects
        if 'content' in data and isinstance(data['content'], dict):
            for key, value in data['content'].items():
                if isinstance(value, datetime):
                    data['content'][key] = value.isoformat()
        
        if 'metadata' in data and isinstance(data['metadata'], dict):
            for key, value in data['metadata'].items():
                if isinstance(value, datetime):
                    data['metadata'][key] = value.isoformat()
        
        return data

class AgentState(BaseModel):
    """Agent state model."""
    id: str
    name: str
    type: str
    status: str  # Now supports 'idle', 'responding', 'thinking'
    capabilities: List[str] = []
    model: Optional[str] = None
    provider: Optional[str] = None
    queue_size: int = 0
    last_activity: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Optional[Dict] = None
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "id": "agent-123",
                "name": "Assistant",
                "type": "assistant",
                "status": "idle",
                "capabilities": ["conversation", "search"],
                "model": "gpt-4",
                "provider": "openai",
                "queue_size": 0,
                "last_activity": "2023-01-01T00:00:00.000000"
            }
        }

    @model_validator(mode='before')
    @classmethod
    def validate_datetime(cls, data: Dict) -> Dict:
        """Convert datetime objects to ISO format strings."""
        if isinstance(data.get('last_activity'), datetime):
            data['last_activity'] = data['last_activity'].isoformat()
        
        if 'metadata' in data and isinstance(data['metadata'], dict):
            for key, value in data['metadata'].items():
                if isinstance(value, datetime):
                    data['metadata'][key] = value.isoformat()
        
        return data

class AgentConfig(BaseModel):
    """Configuration for creating a new agent."""
    name: str
    agent_type: str
    model: str
    provider: str
    capabilities: List[str]
    parameters: Optional[Dict[str, Any]] = None

class WebSocketMessage(BaseModel):
    """WebSocket message model for client-server communication."""
    type: str
    data: Dict[str, Any]

    @model_validator(mode='before')
    @classmethod
    def validate_datetime(cls, data: Dict) -> Dict:
        """Convert datetime objects to ISO format strings in nested data."""
        if 'data' in data and isinstance(data['data'], dict):
            for key, value in data['data'].items():
                if isinstance(value, datetime):
                    data['data'][key] = value.isoformat()
                elif isinstance(value, dict):
                    for k, v in value.items():
                        if isinstance(v, datetime):
                            value[k] = v.isoformat()
        return data 