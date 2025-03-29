from typing import Optional, AsyncGenerator, ClassVar, List
import asyncio
import time
from datetime import datetime
import logging
import psutil

from ..models import Message, WebSocketMessage
from .base import BaseAgent
from ...utils.logger import get_logger

logger = get_logger(__name__)

class SystemAgent(BaseAgent):
    """System agent for monitoring and managing the agent community."""
    
    name: ClassVar[str] = "System"
    agent_type: ClassVar[str] = "system"
    description: ClassVar[str] = "System agent for monitoring and managing the agent community"
    capabilities: ClassVar[List[str]] = [
        "system_monitoring",
        "status_reporting",
        "error_handling"
    ]
    
    def __init__(self, name: str = "System", think_interval: float = 300.0):
        super().__init__(name=name, think_interval=think_interval)
        self.last_status_update = time.time()
        self.status_check_count = 0

    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """
        Perform periodic system checks and report on system status.
        This method is required by the BaseAgent abstract class.
        """
        while True:
            if await self._should_think():
                # Get system stats
                cpu_percent = psutil.cpu_percent()
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                status_message = f"""System Status Report #{self.status_check_count}
CPU Usage: {cpu_percent}%
Memory: {memory.percent}% used ({memory.used / (1024**3):.2f} GB / {memory.total / (1024**3):.2f} GB)
Disk: {disk.percent}% used ({disk.used / (1024**3):.2f} GB / {disk.total / (1024**3):.2f} GB)
Active Agents: {len(self.agent_server.agents) if self.agent_server else 'Unknown'}
"""
                logger.info(f"System status check: CPU {cpu_percent}%, Memory {memory.percent}%, Disk {disk.percent}%")
                
                # Increment counter and update last think time
                self.status_check_count += 1
                self.last_think_time = time.time()
                
                yield Message(
                    sender_id=self.agent_id,
                    receiver_id="broadcast",
                    content={"text": status_message, "type": "status"},
                    message_type="status"
                )
            
            # Sleep briefly to avoid busy waiting
            await asyncio.sleep(10)

    async def process_message(self, message: Message) -> AsyncGenerator[Message, None]:
        """Process incoming messages for the system agent."""
        # Extract the message text
        text = message.content.get("text", "")
        
        if "status" in text.lower() or "report" in text.lower():
            # Get system stats
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            response_text = f"""System Status Report (on demand)
CPU Usage: {cpu_percent}%
Memory: {memory.percent}% used ({memory.used / (1024**3):.2f} GB / {memory.total / (1024**3):.2f} GB)
Disk: {disk.percent}% used ({disk.used / (1024**3):.2f} GB / {disk.total / (1024**3):.2f} GB)
Active Agents: {len(self.agent_server.agents) if self.agent_server else 'Unknown'}
"""
            yield Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": response_text, "type": "status"},
                message_type="status",
                reply_to_id=message.message_id
            )
        else:
            # Default response for any other message
            yield Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": "I am the system agent. I can provide system status reports and monitor the agent community."},
                reply_to_id=message.message_id
            ) 