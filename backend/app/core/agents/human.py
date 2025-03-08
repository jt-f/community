"""
Human agent implementation.
"""
import asyncio
from typing import Optional, AsyncGenerator
from datetime import datetime
import logging
import time

from .base import BaseAgent
from ..models import Message, WebSocketMessage
from ...utils.logger import get_logger

logger = logging.getLogger(__name__)

class HumanAgent(BaseAgent):
    """Human agent for representing user interactions."""
    
    def __init__(self, name: str = "Human"):
        super().__init__(name=name)
        self.agent_server = None  # Will be set by the agent_manager
        self.capabilities = [
            "user_interaction",
            "message_sending",
            "command_execution",
            "task_delegation"
        ]
    
    def should_think(self) -> bool:
        """Human agents don't need to think autonomously."""
        return False
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message sent to the human agent.
        
        For human agents, we don't need to automatically acknowledge messages.
        The human will respond naturally through the UI when they want to.
        """
        # Log that we received a message
        logger.info(f"Human agent received message: {message.content}")
        
        # Don't automatically send an acknowledgment
        # Just return None to indicate no automatic response
        return None
    
    async def think_once(self) -> Optional[Message]:
        """Human agents don't think autonomously."""
        return None
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Human agents don't think autonomously."""
        yield None
