from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum
import random
import string

class MessageType(str, Enum):
    TEXT = "TEXT"
    REPLY = "REPLY"
    SYSTEM = "SYSTEM"
    ERROR = "ERROR"
    REGISTER_AGENT = "REGISTER_AGENT"
    REGISTER_AGENT_RESPONSE = "REGISTER_AGENT_RESPONSE"
    PING = "PING"
    PONG = "PONG"
    SHUTDOWN = "SHUTDOWN"
    CLIENT_DISCONNECTED = "CLIENT_DISCONNECTED"
    AGENT_STATUS_UPDATE = "AGENT_STATUS_UPDATE"
    REGISTER_FRONTEND = "REGISTER_FRONTEND"
    REQUEST_AGENT_STATUS = "REQUEST_AGENT_STATUS"

class ResponseStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"

class ChatMessage(BaseModel):
    message_id: str
    sender_id: str
    receiver_id: str
    text_payload: str
    send_timestamp: str
    message_type: MessageType
    in_reply_to_message_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        sender_id: str,
        receiver_id: str,
        text_payload: str,
        message_type: MessageType = MessageType.TEXT,
        in_reply_to_message_id: Optional[str] = None
    ) -> "ChatMessage":
        return cls(
            message_id=''.join(random.choices(string.ascii_lowercase + string.digits, k=6)),
            sender_id=sender_id,
            receiver_id=receiver_id,
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
            "receiver_id": self.receiver_id,
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
            receiver_id=data.get("receiver_id", ""),
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

def create_text_message(sender_id: str, receiver_id: str, text_payload: str, 
                        in_reply_to_message_id: Optional[str] = None,
                        message_type: MessageType = MessageType.TEXT) -> ChatMessage:
    """Helper function to create a new text message."""
    return ChatMessage(
        message_id=''.join(random.choices(string.ascii_lowercase + string.digits, k=8)),
        sender_id=sender_id,
        receiver_id=receiver_id,
        text_payload=text_payload,
        send_timestamp=datetime.now().isoformat(),
        message_type=message_type,
        in_reply_to_message_id=in_reply_to_message_id
    )

def create_reply_message(original_message: ChatMessage, sender_id: str, text_payload: str) -> ChatMessage:
    """Helper function to create a reply to an existing message."""
    return ChatMessage(
        message_id=''.join(random.choices(string.ascii_lowercase + string.digits, k=8)),
        sender_id=sender_id,
        receiver_id=original_message.sender_id,  # Reply goes back to the original sender
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