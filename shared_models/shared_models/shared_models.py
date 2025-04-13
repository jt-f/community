from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum
import random
import string
import logging
import sys

class MessageType(str, Enum):
    """Enumeration of all possible message types in the system."""
    AGENT_STATUS_UPDATE = "AGENT_STATUS_UPDATE"
    CLIENT_DISCONNECTED = "CLIENT_DISCONNECTED"
    ERROR = "ERROR"
    PING = "PING"
    PONG = "PONG"
    REGISTER_AGENT = "REGISTER_AGENT"
    REGISTER_AGENT_RESPONSE = "REGISTER_AGENT_RESPONSE"
    REGISTER_BROKER = "REGISTER_BROKER"
    REGISTER_BROKER_RESPONSE = "REGISTER_BROKER_RESPONSE"
    REGISTER_FRONTEND = "REGISTER_FRONTEND"
    REGISTER_FRONTEND_RESPONSE = "REGISTER_FRONTEND_RESPONSE"
    REQUEST_AGENT_STATUS = "REQUEST_AGENT_STATUS"
    REPLY = "REPLY"
    SERVER_AVAILABLE = "SERVER_AVAILABLE"
    SERVER_HEARTBEAT = "SERVER_HEARTBEAT"
    SHUTDOWN = "SHUTDOWN"
    SYSTEM = "SYSTEM"
    TEXT = "TEXT"

class ResponseStatus(str, Enum):
    """Enumeration of possible response statuses."""
    SUCCESS = "success"
    ERROR = "error"

class ChatMessage(BaseModel):
    """Model for chat messages in the system."""
    message_id: str
    sender_id: str
    text_payload: str
    send_timestamp: str
    message_type: MessageType
    in_reply_to_message_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        sender_id: str,
        text_payload: str,
        message_type: MessageType = MessageType.TEXT,
        in_reply_to_message_id: Optional[str] = None
    ) -> "ChatMessage":
        """Create a new chat message with a random ID."""
        return cls(
            message_id=''.join(random.choices(string.ascii_lowercase + string.digits, k=6)),
            sender_id=sender_id,
            text_payload=text_payload,
            send_timestamp=datetime.now().strftime("%H:%M:%S"),
            message_type=message_type,
            in_reply_to_message_id=in_reply_to_message_id
        )
        
    def to_dict(self) -> dict:
        """Convert the ChatMessage to a dictionary for JSON serialization."""
        return {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "text_payload": self.text_payload,
            "send_timestamp": self.send_timestamp,
            "message_type": self.message_type,
            "in_reply_to_message_id": self.in_reply_to_message_id,
        }
        
    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage":
        """Create a ChatMessage from a dictionary."""
        return cls(
            message_id=data.get("message_id", ""),
            sender_id=data.get("sender_id", ""),
            text_payload=data.get("text_payload", ""),
            send_timestamp=data.get("send_timestamp", ""),
            message_type=data.get("message_type", MessageType.TEXT),
            in_reply_to_message_id=data.get("in_reply_to_message_id")
        )

class AgentRegistrationMessage(BaseModel):
    """Message sent by an agent to register with the broker."""
    agent_id: str
    agent_name: str
    message_type: MessageType = MessageType.REGISTER_AGENT
    
    def to_dict(self) -> dict:
        """Convert the AgentRegistrationMessage to a dictionary for JSON serialization."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "message_type": self.message_type
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentRegistrationMessage":
        """Create an AgentRegistrationMessage from a dictionary."""
        return cls(
            agent_id=data.get("agent_id", ""),
            agent_name=data.get("agent_name", ""),
            message_type=data.get("message_type", MessageType.REGISTER_AGENT)
        )

class AgentRegistrationResponse(BaseModel):
    """Response to an agent registration request."""
    status: ResponseStatus
    agent_id: str
    message: str
    message_type: MessageType = MessageType.REGISTER_AGENT_RESPONSE
    
    def to_dict(self) -> dict:
        """Convert the AgentRegistrationResponse to a dictionary for JSON serialization."""
        return {
            "status": self.status,
            "agent_id": self.agent_id,
            "message": self.message,
            "message_type": self.message_type
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentRegistrationResponse":
        """Create an AgentRegistrationResponse from a dictionary."""
        return cls(
            status=data.get("status", ResponseStatus.ERROR),
            agent_id=data.get("agent_id", ""),
            message=data.get("message", ""),
            message_type=data.get("message_type", MessageType.REGISTER_AGENT_RESPONSE)
        )

def create_text_message(sender_id: str, text_payload: str, 
                        in_reply_to_message_id: Optional[str] = None,
                        message_type: MessageType = MessageType.TEXT) -> ChatMessage:
    """Create a new text message with a random ID."""
    return ChatMessage(
        message_id=''.join(random.choices(string.ascii_lowercase + string.digits, k=8)),
        sender_id=sender_id,
        text_payload=text_payload,
        send_timestamp=datetime.now().isoformat(),
        message_type=message_type,
        in_reply_to_message_id=in_reply_to_message_id
    )

def create_reply_message(original_message: ChatMessage, sender_id: str, text_payload: str) -> ChatMessage:
    """Create a reply to an existing message."""
    return ChatMessage(
        message_id=''.join(random.choices(string.ascii_lowercase + string.digits, k=8)),
        sender_id=sender_id,
        text_payload=text_payload,
        send_timestamp=datetime.now().isoformat(),
        message_type=MessageType.REPLY,
        in_reply_to_message_id=original_message.message_id
    )

class AgentStatus(BaseModel):
    """Represents the status of a single agent."""
    agent_id: str
    agent_name: str
    is_online: bool = True
    last_seen: str = datetime.now().strftime("%H:%M:%S")

class AgentStatusUpdate(BaseModel):
    """Message containing the current status of all registered agents."""
    message_type: MessageType = MessageType.AGENT_STATUS_UPDATE
    agents: list[AgentStatus]
    
    def to_dict(self) -> dict:
        """Convert the AgentStatusUpdate to a dictionary for JSON serialization."""
        return {
            "message_type": self.message_type,
            "agents": [agent.model_dump() for agent in self.agents]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentStatusUpdate":
        """Create an AgentStatusUpdate from a dictionary."""
        return cls(
            message_type=data.get("message_type", MessageType.AGENT_STATUS_UPDATE),
            agents=[AgentStatus(**agent) for agent in data.get("agents", [])]
        )
    
def setup_logging(
    name: str,
    level: int = logging.INFO,
    stream: Optional[logging.StreamHandler] = None
) -> logging.Logger:
    """Set up logging with a consistent format across all modules."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and configure handler
    if stream is None:
        stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(stream)
    
    return logger 