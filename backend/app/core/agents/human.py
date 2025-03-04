"""
Human agent implementation.
"""
import asyncio
from typing import Optional, AsyncGenerator
from datetime import datetime
import logging

from .base import BaseAgent
from ..models import Message, WebSocketMessage
from ...utils.logger import get_logger

logger = logging.getLogger(__name__)

class HumanAgent(BaseAgent):
    """Human agent representing user interactions."""
    
    def __init__(self, name: str = "Human"):
        super().__init__(name=name)
        self.agent_server = None  # Will be set by the agent_manager
        self.capabilities = [
            "text_input",
            "command_execution",
            "task_delegation"
        ]
    
    def should_think(self) -> bool:
        """Human agents never think autonomously."""
        return False
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message and acknowledge receipt."""
        try:
            logger.info(f"Human agent processing message: {message.content}")
            
            # Human agents simply acknowledge receipt of messages
            response = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"Acknowledged"},
                message_type="response",
                timestamp=datetime.now().isoformat()
            )
            
            # Return the response - routing and broadcasting will be handled by the agent_manager
            return response
            
        except Exception as e:
            logger.error(f"Error processing message in HumanAgent: {str(e)}")
            error_message = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"Error processing message: {str(e)}"},
                message_type="error",
                timestamp=datetime.now().isoformat()
            )
            
            # Return the error message - routing and broadcasting will be handled by the agent_manager
            return error_message
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Human agents do not think autonomously."""
        yield None
