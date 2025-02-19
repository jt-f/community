"""
Default agent implementations.
"""
import asyncio
from typing import Optional, AsyncGenerator
from datetime import datetime

from .base import BaseAgent
from ..models import Message
from ...utils.logger import get_logger

logger = get_logger(__name__)

class SystemAgent(BaseAgent):
    """System agent for managing and monitoring the community."""
    
    def __init__(self):
        super().__init__(
            name="System",
            capabilities=[
                "system_monitoring",
                "agent_management",
                "status_reporting"
            ]
        )
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process system-related messages."""
        if "status" in message.content:
            return Message(
                sender_id=self.id,
                receiver_id=message.sender_id,
                content={"text": "System is operational", "status": "healthy"},
                message_type="status_report"
            )
        return None
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Periodically check system status."""
        while True:
            # Broadcast system status every 60 seconds
            yield Message(
                sender_id=self.id,
                content={
                    "text": "System health check",
                    "timestamp": datetime.now().isoformat(),
                    "status": "operational"
                },
                message_type="system_status"
            )
            await asyncio.sleep(60)

class HumanAgent(BaseAgent):
    """Human agent representing user interactions."""
    
    def __init__(self):
        super().__init__(
            name="Human",
            capabilities=[
                "text_input",
                "command_execution",
                "task_delegation"
            ]
        )
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process messages directed to the human agent."""
        # Simply acknowledge receipt of messages
        return Message(
            sender_id=self.id,
            receiver_id=message.sender_id,
            content={
                "text": "Message received",
                "original": message.content,
                "timestamp": datetime.now().isoformat()
            },
            message_type="acknowledgment"
        )
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Human agents don't think autonomously."""
        while True:
            await asyncio.sleep(1)
            yield None

class AnalystAgent(BaseAgent):
    """Analyst agent for data analysis and insights."""
    
    def __init__(self):
        super().__init__(
            name="Analyst",
            capabilities=[
                "data_analysis",
                "pattern_recognition",
                "insight_generation",
                "report_creation"
            ]
        )
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process analysis requests and generate insights."""
        logger.info(f"(analyst_agent) Processing message: {message.content}")
        if "analyze" in message.content:
            return Message(
                sender_id=self.id,
                receiver_id=message.sender_id,
                content={
                    "text": "Analysis complete",
                    "insights": ["Insight 1", "Insight 2"],
                    "data": message.content.get("data", {}),
                    "timestamp": datetime.now().isoformat()
                },
                message_type="analysis_result"
            )
        else:
            return Message(
                sender_id=self.id,
                receiver_id=message.sender_id,
                content={
                    "text": "No analysis requested",
                    "insights": ["No Insight"],
                    "data": message.content.get("data", {}),
                    "timestamp": datetime.now().isoformat()
                },
                message_type="analysis_result"
            )
        return None
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Periodically generate insights from observed patterns."""
        logger.info(f"(analyst_agent) Running think cycle")
        while True:
            yield Message(
                sender_id=self.id,
                content={
                    "text": "Periodic insight report",
                    "timestamp": datetime.now().isoformat(),
                    "insights": ["Periodic Insight 1", "Periodic Insight 2"]
                },
                message_type="periodic_analysis"
            )
            await asyncio.sleep(10) 