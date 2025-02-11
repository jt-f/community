from dataclasses import dataclass
from typing import Optional, Any
from datetime import datetime

@dataclass
class Message:
    sender_id: str
    sender_name: str
    content: str
    recipient_id: Optional[str] = None
    timestamp: datetime = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        # Set timestamp if not provided
        if self.timestamp is None:
            self.timestamp = datetime.now()
        
        # Initialize empty metadata dict if not provided
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        """Convert message to dictionary format."""
        return {
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "content": self.content,
            "recipient_id": self.recipient_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """Create a Message instance from a dictionary."""
        # Create a copy of the data to avoid modifying the original
        message_data = data.copy()
        
        # Map 'from' to 'sender_id' if present
        if 'from' in message_data:
            message_data['sender_id'] = message_data.pop('from')
            
        # Map 'text' to 'content' if present
        if 'text' in message_data:
            message_data['content'] = message_data.pop('text')
            
        # Set sender_name if not present
        if 'sender_name' not in message_data:
            message_data['sender_name'] = message_data.get('sender_id', 'Unknown')
            
        # Convert ISO format string back to datetime if present
        if message_data.get("timestamp"):
            message_data["timestamp"] = datetime.fromisoformat(message_data["timestamp"])
            
        # Filter out any unexpected keywords
        valid_fields = {'sender_id', 'sender_name', 'content', 'recipient_id', 'timestamp', 'metadata'}
        filtered_data = {k: v for k, v in message_data.items() if k in valid_fields}
        
        return cls(**filtered_data) 