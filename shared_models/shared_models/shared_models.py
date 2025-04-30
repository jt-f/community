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
    REGISTER_FRONTEND = "REGISTER_FRONTEND"
    REGISTER_FRONTEND_RESPONSE = "REGISTER_FRONTEND_RESPONSE"
    REQUEST_AGENT_STATUS = "REQUEST_AGENT_STATUS"
    REPLY = "REPLY"
    SYSTEM = "SYSTEM"
    TEXT = "TEXT"
    PAUSE_AGENT = "PAUSE_AGENT"
    RESUME_AGENT = "RESUME_AGENT"
    DEREGISTER_AGENT = "DEREGISTER_AGENT"
    REREGISTER_AGENT = "REREGISTER_AGENT"
    PAUSE_ALL_AGENTS = "PAUSE_ALL_AGENTS"
    RESUME_ALL_AGENTS = "RESUME_ALL_AGENTS"
    DEREGISTER_ALL_AGENTS = "DEREGISTER_ALL_AGENTS"
    REREGISTER_ALL_AGENTS = "REREGISTER_ALL_AGENTS"
    RESET_ALL_QUEUES = "RESET_ALL_QUEUES"

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

class AgentStatus(BaseModel):
    """Represents the status of a single agent."""
    agent_id: str
    agent_name: str
    last_seen: str = datetime.now().strftime("%H:%M:%S")
    metrics: Optional[dict[str, str]] = None  # New metrics map for internal_state and other metrics

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
    level: int = logging.INFO,
) -> None: # Doesn't need to return a logger
    """Set up root logging with a consistent format and level.
    Adds a console handler only if one doesn't already exist.
    """
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    root_logger = logging.getLogger() # Get the root logger
    root_logger.setLevel(level) # Set the overall minimum level

    # Check if a console handler already exists on the root logger
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) and h.stream in (sys.stdout, sys.stderr)
        for h in root_logger.handlers
    )

    if not has_console_handler:
        console_handler = logging.StreamHandler(sys.stdout)
        # Explicitly set the HANDLER's level to match the root logger's level
        # This prevents the handler filtering messages the logger allows
        console_handler.setLevel(level)
        console_handler.setFormatter(log_formatter)
        root_logger.addHandler(console_handler)
        # Optional: Log a message indicating handler was added
        # root_logger.debug(f"Root console handler added with level {logging.getLevelName(level)}")
    else:
        # Optional: Check if existing handler level is too high
        for h in root_logger.handlers:
            if isinstance(h, logging.StreamHandler) and h.stream in (sys.stdout, sys.stderr):
                if h.level > level:
                    # Log a warning if the existing handler might filter messages
                    root_logger.warning(f"Existing console handler level ({logging.getLevelName(h.level)}) is higher than requested ({logging.getLevelName(level)}). Some logs may not appear on console.")
                    # Optionally force the level down (use with caution):
                    # h.setLevel(level)
                break # Assume only one console handler

    # No need to return the logger, modules will use logging.getLogger(__name__)