from typing import Optional, AsyncGenerator
import asyncio
import time
from datetime import datetime
import logging

from ..models import Message, WebSocketMessage
from .base import BaseAgent

logger = logging.getLogger(__name__)

class SystemAgent(BaseAgent):
    """System agent for monitoring and system-level operations."""
    
    def __init__(self, name: str = "System"):
        super().__init__(name=name)
        self.last_think_time = time.time()
        # Increase the think interval from default (likely 5-10 seconds) to 60 seconds
        self.think_interval = 300  # seconds between thinking cycles
        self.capabilities = [
            "system_monitoring",
            "status_reporting",
            "error_handling"
        ]
        self.status_check_count = 0
        self.agent_server = None  # Will be set by the agent_manager
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message and generate a system response."""
        try:
            logger.info(f"System agent processing message: {message.content}")
            
            # Simple response for now
            response = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"System received your message: {message.content['text']}"},
                message_type="response",
                timestamp=datetime.now().isoformat()
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing message in SystemAgent: {str(e)}")
            error_message = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"Error processing system message: {str(e)}"},
                message_type="error",
                timestamp=datetime.now().isoformat()
            )
            
            return error_message
    
    def should_think(self) -> bool:
        """Determine if the agent should run a thinking cycle."""
        current_time = time.time()
        # Check if enough time has passed since the last thinking cycle
        return (current_time - self.last_think_time) > self.think_interval
    
    async def think_once(self) -> Optional[Message]:
        """Run a thinking cycle for the agent."""
        self.last_think_time = time.time()
        
        # For now, just a simple status update
        status_message = Message(
            sender_id=self.agent_id,
            message_type="status",
            content={"text": f"System status: All systems operational at {datetime.now().isoformat()}"},
            timestamp=datetime.now().isoformat()
        )
        
        return status_message
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Generate system status updates periodically."""
        while True:
            if self.should_think():
                yield await self.think_once()
            await asyncio.sleep(5)  # Check if we should think every 5 seconds 