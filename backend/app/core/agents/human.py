"""
Human agent implementation.
"""
from typing import AsyncGenerator, ClassVar, List, Optional
from datetime import datetime
import asyncio

from ..models import Message, WebSocketMessage
from .base import BaseAgent
from ...utils.logger import get_logger

logger = get_logger(__name__)

class HumanAgent(BaseAgent):
    """
    Human agent representing a user of the system.
    This agent doesn't run autonomously but serves as a proxy for real human users.
    """
    
    name: ClassVar[str] = "Human"
    agent_type: ClassVar[str] = "human"
    description: ClassVar[str] = "Human user of the system"
    capabilities: ClassVar[List[str]] = [
        "text_input", 
        "file_upload", 
        "human_feedback",
        "natural_language",
        "reasoning",
        "learning",
        "creativity"
    ]
    
    def __init__(self, name: str = "Human", think_interval: float = 3600.0):
        """Initialize human agent with a very long think interval since humans don't auto-think."""
        super().__init__(name=name, think_interval=think_interval)
    
    async def process_message(self, message: Message) -> AsyncGenerator[Message, None]:
        """
        Process a message sent to the human agent.
        
        For human agents, we don't auto-respond, but this method could be used
        to generate automatic acknowledgements or out-of-office messages.
        """
        # Human agents don't automatically respond to messages
        # We could implement auto-responses here if desired
        logger.debug(f"Human agent {self.name} received message: '{message.content.get('text')}'")
        
        # Since we don't generate a response, we need to return an empty AsyncGenerator
        if False:  # This condition never executes but makes it a valid AsyncGenerator
            yield Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": "Auto-response from human agent (disabled)"},
                reply_to_id=message.message_id
            )
    
    async def _think(self) -> AsyncGenerator[Message, None]:
        """
        Human agents don't think autonomously in the system.
        
        This is just a placeholder implementation.
        """
        # No autonomous thinking for human agents
        return
        yield  # This line will never be reached, but makes it a valid generator
        
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """
        Human agents don't think autonomously.
        This method is required by the BaseAgent abstract class but is a no-op for humans.
        """
        while True:
            yield None
            await asyncio.sleep(60)  # Just sleep, humans don't think autonomously
