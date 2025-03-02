"""
Default agent implementations.
"""
import asyncio
from typing import Optional, AsyncGenerator, Union
from datetime import datetime

from .base import BaseAgent
from ..models import Message
from ...utils.logger import get_logger
from ...utils.ollama import ollama_client
from .config import ANALYST_CONFIG

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
            # For human agents, we'll just acknowledge receipt of messages
            # but won't auto-respond to keep interaction natural
            return None
        except Exception as e:
            logger.error(f"(human_agent) Error processing message: {e}", exc_info=True)
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
        self.config = ANALYST_CONFIG


    def should_think(self) -> bool:
        """Analyst thinks every THINK_INTERVAL iterations."""
        return self._think_counter >= self.THINK_INTERVAL

    async def _generate_response(self, prompt: str, model: str, parameters: dict) -> Union[str, dict]:
        async with ollama_client as client:
            logger.info(f"Using OllamaClient to make generate call: {prompt}")
            return await client.generate(prompt=prompt, model=model, parameters=parameters)
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process analysis requests and generate insights using Ollama."""
        logger.info(f"(analyst_agent) Processing message: {message.content}")
        
        try:
            # Select prompt based on message content or use default
            prompt_key = "default"
            if "technical" in message.content.get("text", "").lower():
                prompt_key = "technical"
            elif "data" in message.content.get("text", "").lower():
                prompt_key = "data"
                
            # Format prompt with message
            prompt_template = self.config["prompts"][prompt_key]
            prompt = prompt_template.format(message=message.content.get("text", ""))
            
            logger.info(f"(analyst_agent) Sending prompt to Ollama: {prompt}")
            try:
                response = await self._generate_response(
                    prompt=prompt,
                    model=self.config["model"],
                    parameters=None
                    # {
                    #     "temperature": self.config["temperature"]
                    #     #,
                    #     # "num_ctx": 4096,  # Larger context window
                    #     # "num_predict": 1024,  # Longer responses
                    #     # "top_p": 0.9,
                    #     # "top_k": 40
                    # }
                )
            except Exception as e:
                logger.error(f"(process message) Error generating response: {e}", exc_info=True)
                return Message(
                    sender_id=self.id,
                    receiver_id=message.sender_id,
                    content={
                        "text": "Sorry, I encountered an error while processing your message.",
                        "error": str(e),
                        "details": "An error occurred while generating the response",
                        "timestamp": datetime.now().isoformat()
                    },
                    message_type="error"
                )
            
            logger.info(f"(Analyst Agent) Ollama response: {response}")
            
            # Check if response is an error dict
            if isinstance(response, dict) and "error" in response:
                logger.error(f"Error from Ollama: {response['error']}")
                return Message(
                    sender_id=self.id,
                    receiver_id=message.sender_id,
                    content={
                        "text": "Sorry, I encountered an error while processing your message.",
                        "error": response["error"],
                        "details": response.get("details", "No additional details"),
                        "timestamp": datetime.now().isoformat()
                    },
                    message_type="error"
                )
            
            # Response should be a string if successful
            if not isinstance(response, str):
                logger.error(f"Unexpected response type from Ollama: {type(response)}")
                return Message(
                    sender_id=self.id,
                    receiver_id=message.sender_id,
                    content={
                        "text": "Sorry, I received an unexpected response format.",
                        "error": "Invalid response format",
                        "timestamp": datetime.now().isoformat()
                    },
                    message_type="error"
                )
            
            return Message(
                sender_id=self.id,
                receiver_id=message.sender_id,
                content={
                    "text": response,
                    "prompt_used": prompt_key,
                    "timestamp": datetime.now().isoformat()
                },
                message_type="analysis_result"
            )
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return Message(
                sender_id=self.id,
                receiver_id=message.sender_id,
                content={
                    "text": "An error occurred while processing your message.",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                },
                message_type="error"
            )
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Generate periodic insights."""
        logger.debug(f"(analyst_agent) Generating insights")
        # For now, we'll keep the periodic insights simple
        yield Message(
            sender_id=self.id,
            receiver_id="human",
            content={
                "text": "Periodic insight report",
                "timestamp": datetime.now().isoformat(),
                "insights": ["System is operating normally", "No anomalies detected"]
            },
            message_type="periodic_analysis"
        )