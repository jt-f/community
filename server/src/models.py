from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum
import uuid

class MessageType(str, Enum):
    TEXT = "TEXT"
    REPLY = "REPLY"
    SYSTEM = "SYSTEM"
    ERROR = "ERROR"

class ChatMessage(BaseModel):
    message_id: str
    sender_id: str
    receiver_id: str
    text_payload: str
    send_timestamp: str  # ISO 8601 format
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
            message_id=str(uuid.uuid4()),
            sender_id=sender_id,
            receiver_id=receiver_id,
            text_payload=text_payload,
            send_timestamp=datetime.utcnow().isoformat(),
            message_type=message_type,
            in_reply_to_message_id=in_reply_to_message_id
        ) 