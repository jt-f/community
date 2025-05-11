from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum
import random
import string
import logging
import sys
import colorlog
import contextlib
import os

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

@contextlib.contextmanager
def temporary_formatter(new_formatter: logging.Formatter):
    """
    Temporarily sets a different formatter for the root logger's console handler.

    Args:
        new_formatter: The new logging.Formatter instance to use temporarily.
    """
    root_logger = logging.getLogger()
    original_formatter = None
    console_handler = None

    # Find the console handler
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream in (sys.stdout, sys.stderr):
            console_handler = handler
            original_formatter = console_handler.formatter
            break # Assume only one console handler

    if console_handler is None:
        # Handle the case where no console handler is found (e.g., logging not set up with a console handler)
        # You might want to log a warning or raise an error here, depending on desired behavior.
        # For now, we'll just just proceed without changing anything.
        print("Warning: No console stream handler found to change formatter.")
        yield # Yield immediately if no handler is found
        return # Exit the context manager

    try:
        # Set the new formatter
        console_handler.setFormatter(new_formatter)
        yield # Code inside the 'with' block will execute here
    finally:
        # Restore the original formatter
        if original_formatter is not None and console_handler is not None:
            console_handler.setFormatter(original_formatter)

def setup_logging(
    level: int = logging.INFO,
) -> None: # Doesn't need to return a logger
    """Set up root logging with a consistent format and level.
    Adds a console handler only if one doesn't already exist.
    Uses colorlog for colored output.
    """
    log_formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
        log_colors={
            'DEBUG':    'bold_cyan',
            'INFO':     'bold_green',
            'WARNING':  'bold_yellow',
            'ERROR':    'bold_red',
            'CRITICAL': 'bold_red,bg_white', # CRITICAL is already very visible
        }
    )
    root_logger = logging.getLogger() # Get the root logger
    root_logger.setLevel(level) # Set the overall minimum level

    # Check if a console handler already exists on the root logger
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) and h.stream in (sys.stdout, sys.stderr)
        for h in root_logger.handlers
    )

    if not has_console_handler:
        console_handler = colorlog.StreamHandler(sys.stdout) # Use colorlog's StreamHandler
        console_handler.setLevel(level)
        console_handler.setFormatter(log_formatter)
        root_logger.addHandler(console_handler)
    else:
        for h in root_logger.handlers:
            if isinstance(h, logging.StreamHandler) and h.stream in (sys.stdout, sys.stderr):
                if not isinstance(h.formatter, colorlog.ColoredFormatter):
                    h.setFormatter(log_formatter)
                    root_logger.debug("Updated existing console handler formatter to ColoredFormatter.")
                if h.level > level:
                    root_logger.warning(f"Existing console handler level ({logging.getLevelName(h.level)}) is higher than requested ({logging.getLevelName(level)}). Some logs may not appear on console.")
                break

    # Add FileHandler for services that define LOG_FILE
    log_file_path = os.getenv('LOG_FILE')
    if log_file_path:
        # Ensure the directory for the log file exists
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
                root_logger.info(f"Created log directory: {log_dir}")
            except OSError as e:
                root_logger.error(f"Failed to create log directory {log_dir}: {e}")
                # Fallback or skip file logging if directory creation fails
                log_file_path = None # Prevent trying to use the path

        if log_file_path:
            # Check if a FileHandler for the same path already exists
            has_file_handler_for_path = any(
                isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file_path)
                for h in root_logger.handlers
            )
            if not has_file_handler_for_path:
                try:
                    file_handler = logging.FileHandler(log_file_path, mode='a') # Append mode
                    file_handler.setLevel(level) # Set level for file handler
                    # Use a simpler formatter for file logs, or the same colored one if preferred
                    file_log_formatter = logging.Formatter(
                        '%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s'
                    )
                    file_handler.setFormatter(file_log_formatter)
                    root_logger.addHandler(file_handler)
                    root_logger.info(f"Added FileHandler for {log_file_path} with level {logging.getLevelName(level)}")
                except Exception as e:
                    # Log to console if file handler setup fails
                    root_logger.error(f"Failed to set up FileHandler for {log_file_path}: {e}")
            else:
                root_logger.debug(f"FileHandler for {log_file_path} already exists.")
    else:
        root_logger.debug("LOG_FILE environment variable not set. Skipping file logging configuration.")