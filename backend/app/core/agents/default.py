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
        self.THINK_INTERVAL = 600  # Think every 600 iterations (~ every minute with 0.1s sleep)
    
    def should_think(self) -> bool:
        """System agent thinks every THINK_INTERVAL iterations."""
        return self._think_counter >= self.THINK_INTERVAL
    
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
        """Generate system status message."""
        yield Message(
            sender_id=self.id,
            content={
                "text": "System health check",
                "timestamp": datetime.now().isoformat(),
                "status": "operational"
            },
            message_type="system_status"
        )


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
        self.id = 'human'
    
    def should_think(self) -> bool:
        """Human agents never think autonomously."""
        return False
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process messages directed to the human agent."""
        try:
            logger.debug(f"(human_agent) Processing message: {message.content}")
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
        except Exception as e:
            logger.error(f"(human_agent) Error processing message: {str(e)}", exc_info=True)
            return None
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Human agents don't think autonomously."""
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
        self.THINK_INTERVAL = 100  # Think every 100 iterations (~ every 10 seconds with 0.1s sleep)
    
    def should_think(self) -> bool:
        """Analyst thinks every THINK_INTERVAL iterations."""
        return self._think_counter >= self.THINK_INTERVAL
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process analysis requests and generate insights."""
        logger.debug(f"(analyst_agent) Processing message: {message.content}")
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
        """Generate periodic insights."""
        logger.debug(f"(analyst_agent) Generating insights")
        yield Message(
            sender_id=self.id,
            receiver_id="human",
            content={
                "text": "Periodic insight report",
                "timestamp": datetime.now().isoformat(),
                "insights": ["Periodic Insight 1", "Periodic Insight 2"]
            },
            message_type="periodic_analysis"
        )