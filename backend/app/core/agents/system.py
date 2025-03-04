from typing import Optional, AsyncGenerator
import asyncio
import time
from datetime import datetime
import logging

from ..models import Message, WebSocketMessage
from .base import BaseAgent

logger = logging.getLogger(__name__)

class SystemAgent(BaseAgent):
    """System agent for processing messages and generating responses."""
    
    def __init__(self, name: str = "System"):
        super().__init__(name=name)
        self.status_check_count = 0
        self.agent_server = None  # Will be set by the agent_manager
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message and generate a response."""
        try:
            logger.info(f"System agent processing message: {message.content}")
            
            # Create a response message
            response = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"Received: {message.content['text']}"},
                message_type="response",
                timestamp=datetime.now().isoformat()
            )
            
            # Return the response - routing and broadcasting will be handled by the agent_manager
            return response
            
        except Exception as e:
            logger.error(f"Error processing message in SystemAgent: {str(e)}")
            error_message = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"Error processing message: {str(e)}"},
                message_type="error",
                timestamp=datetime.now().isoformat()
            )
            
            # Return the error message - routing and broadcasting will be handled by the agent_manager
            return error_message
    
    async def think_once(self) -> Optional[Message]:
        # Override to include our counter increment
        self.last_think_time = time.time()
        self._think_counter += 1
        
        # Create system status message
        thought_message = Message(
            sender_id=self.agent_id,
            message_type="thought",
            content={
                "text": f"System status check #{self._think_counter}",
                "timestamp": datetime.now().isoformat(),
                "status": "operational"
            },
            timestamp=datetime.now().isoformat()
        )
        
        # Return the thought message - routing and broadcasting will be handled by the agent_manager
        return thought_message
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Generate system thoughts."""
        thought = await self.think_once()
        yield thought 