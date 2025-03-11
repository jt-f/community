"""
Human agent implementation.
"""
from typing import Optional, AsyncGenerator
import asyncio
import time
from datetime import datetime

from .base import BaseAgent
from ..models import Message, WebSocketMessage
from ...utils.logger import get_logger

logger = get_logger(__name__)

class HumanAgent(BaseAgent):
    """Human agent representing a user in the system."""
    
    def __init__(self, name: str = "Human"):
        super().__init__(name=name)
        self.capabilities = [
            "user_interaction",
            "message_sending",
            "command_execution",
            "task_delegation"
        ]
        self.agent_server = None  # Will be set by the agent_manager
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message sent to the human agent."""
        # Human agents don't automatically respond to messages
        # They just receive them and the UI displays them
        
        # Log the message for debugging
        logger.info(f"Human agent {self.name} received message: {message.content}")
        
        # Return None since humans respond manually through the UI
        return None
    
    def should_think(self) -> bool:
        """Human agents don't think autonomously."""
        return False
    
    async def think_once(self) -> Optional[Message]:
        """Human agents don't think autonomously."""
        return None
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Human agents don't think autonomously."""
        while True:
            yield None
            await asyncio.sleep(60)  # Just sleep, humans don't think autonomously
