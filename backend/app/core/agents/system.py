from typing import Optional, AsyncGenerator
import asyncio
import time
from datetime import datetime
import logging
import psutil

from ..models import Message, WebSocketMessage
from .base import BaseAgent

logger = logging.getLogger(__name__)

class SystemAgent(BaseAgent):
    """System agent for monitoring and managing the agent community."""
    
    def __init__(self, name: str = "System"):
        super().__init__(name=name)
        self.last_status_update = time.time()
        self.status_interval = 300  # 5 minutes between status updates
        self.capabilities = [
            "system_monitoring",
            "status_reporting",
            "error_handling"
        ]
        self.status_check_count = 0
        self.agent_server = None  # Will be set by the agent_manager
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message sent to the system agent."""
        # Handle system commands
        if message.message_type == "command":
            command = message.content.get("command")
            if command == "status":
                return await self._generate_status_message()
            elif command == "restart":
                # Implement restart logic
                return Message(
                    sender_id=self.agent_id,
                    message_type="system_response",
                    content={"text": "System restart initiated"}
                )
        
        # Default response for unhandled messages
        return Message(
            sender_id=self.agent_id,
            message_type="system_response",
            content={"text": f"Received message: {message.content}"}
        )
    
    async def _generate_status_message(self) -> Message:
        """Generate a status message with system information."""
        # Get system stats
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return Message(
            sender_id=self.agent_id,
            message_type="system_status",
            content={
                "cpu": cpu_percent,
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent
                },
                "disk": {
                    "total": disk.total,
                    "free": disk.free,
                    "percent": disk.percent
                },
                "timestamp": datetime.now().isoformat()
            }
        )
    
    def should_think(self) -> bool:
        """Determine if the system agent should run a status update."""
        return time.time() - self.last_status_update > self.status_interval
    
    async def think_once(self) -> Optional[Message]:
        """Generate a system status update."""
        self.last_status_update = time.time()
        return await self._generate_status_message()
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Periodically generate system status updates."""
        while True:
            if self.should_think():
                yield await self.think_once()
            await asyncio.sleep(10)  # Check every 10 seconds 