"""
Analyst agent implementation.
"""
import asyncio
from typing import Optional, AsyncGenerator, Union, Dict, Any, ClassVar, List
import time
import logging
from datetime import datetime
import json
import random

from .base import BaseAgent
from ..models import Message, WebSocketMessage
from ...utils.logger import get_logger
from ...utils.model_client import model_client, ModelProvider, GenerationParameters
from ...utils.message_utils import truncate_message

# Import ANALYST_CONFIG instead of settings
from .config import ANALYST_CONFIG

logger = get_logger(__name__)

class AnalystAgent(BaseAgent):
    """
    Analyst agent responsible for analyzing data and providing insights.
    """
    
    name: ClassVar[str] = "Analyst"
    agent_type: ClassVar[str] = "analyst"
    description: ClassVar[str] = "Analyzes data and provides insights"
    capabilities: ClassVar[List[str]] = [
        "data_analysis",
        "trend_detection",
        "pattern_recognition",
        "report_generation",
        "statistical_modeling"
    ]
    
    def __init__(self, name: str = "Analyst", think_interval: float = 120.0):
        """Initialize the analyst agent."""
        super().__init__(name=name, think_interval=think_interval)
        self.metrics = {
            "messages_analyzed": 0,
            "insights_generated": 0,
            "reports_created": 0
        }
        self.default_model = ANALYST_CONFIG.get("model", "mistral-large-latest")
        self.model_provider = ModelProvider(ANALYST_CONFIG.get("provider", "mistral"))
        self.default_parameters = GenerationParameters(
            temperature=ANALYST_CONFIG.get("temperature", 0.7),
            top_p=0.9,
            max_tokens=500,
            provider=self.model_provider  # Set the provider from config
        )
        self.prompts = ANALYST_CONFIG.get("prompts", {})
        self.agent_server = None  # Will be set by the agent_manager
    
    async def process_message(self, message: Message) -> AsyncGenerator[Message, None]:
        """Process a message sent to the analyst agent."""
        text = message.content.get("text", "")
        
        # Increment metrics
        self.metrics["messages_analyzed"] += 1
        
        # Check if this is a data analysis request
        if "analyze" in text.lower() or "data" in text.lower():
            logger.info(f"Analyst agent@ {self.name} processing 'analyze' or 'data' message ({message.message_id})")
            # Simulate data analysis
            await asyncio.sleep(1)  # Simulate processing time
            
            analysis_result = self._generate_mock_analysis()
            self.metrics["insights_generated"] += 1
            
            yield Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={
                    "text": f"Analysis completed. Here are the insights:\n\n{analysis_result}",
                    "data": {"analysis": analysis_result}
                },
                message_type="analysis",
                reply_to_id=message.message_id
            )
        
        # Check if this is a report request
        elif "report" in text.lower():
            logger.info(f"Analyst agent processing 'report' message ({message.message_id})")
            # Simulate report generation
            await asyncio.sleep(2)  # Simulate processing time
            
            report = self._generate_mock_report()
            self.metrics["reports_created"] += 1
            
            yield Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={
                    "text": f"Report generated:\n\n{report}",
                    "data": {"report": report}
                },
                message_type="report",
                reply_to_id=message.message_id
            )
        
        # Default response - use the model client
        else:
            # Format the prompt for the model
            prompt = self._format_prompt(message)
            
            # Generate a response using the LLM
            response_text = await self._generate_response(
                prompt=prompt,
                model=self.default_model,
                parameters=self.default_parameters
            )
            
            yield Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={
                    "text": response_text
                },
                reply_to_id=message.message_id
            )
    
    async def _think(self) -> AsyncGenerator[Message, None]:
        """Periodically provide insights based on accumulated data."""
        if self.message_queue.empty():
            self.last_think_time = datetime.now().timestamp()
            
            # Only generate insights if we've analyzed some messages
            if self.metrics["messages_analyzed"] > 0:
                insight = self._generate_random_insight()
                
                # Find all human agents
                human_agents = [
                    agent_id for agent_id, agent in self.agent_server.agents.items()
                    if agent.state.type.lower() == 'human'
                ]
                
                # Send insight to each human agent
                for human_agent_id in human_agents:
                    yield Message(
                        sender_id=self.agent_id,
                        receiver_id=human_agent_id,
                        content={
                            "text": f"Proactive Insight: {insight}",
                            "data": {"insight": insight}
                        },
                        message_type="insight"
                    )
    
    def _generate_mock_analysis(self) -> str:
        """Generate a mock data analysis result."""
        analysis_templates = [
            "The data shows a significant upward trend with a correlation coefficient of {correlation:.2f}.",
            "Analysis indicates a cyclical pattern with period of {period} units.",
            "Statistical analysis reveals a {percent:.1f}% increase in activity over the baseline.",
            "Data clustering shows {clusters} distinct groups with clear separation.",
            "Time series analysis indicates seasonality with peaks every {seasonality} units."
        ]
        
        template = random.choice(analysis_templates)
        filled_template = template.format(
            correlation=random.uniform(0.7, 0.99),
            period=random.randint(3, 12),
            percent=random.uniform(5.0, 45.0),
            clusters=random.randint(2, 5),
            seasonality=random.randint(4, 24)
        )
        
        return filled_template
    
    def _generate_mock_report(self) -> str:
        """Generate a mock report."""
        report_template = """
# Analysis Report

## Overview
{overview}

## Key Findings
1. {finding1}
2. {finding2}
3. {finding3}

## Recommendations
- {recommendation1}
- {recommendation2}

## Metrics
- Confidence Level: {confidence}%
- Reliability Index: {reliability}/10
- Data Quality Score: {quality}/10
"""
        
        report = report_template.format(
            overview="Analysis of recent data shows several notable patterns and opportunities.",
            finding1=self._generate_mock_analysis(),
            finding2=self._generate_mock_analysis(),
            finding3=self._generate_mock_analysis(),
            recommendation1="Implement continuous monitoring of the identified trends.",
            recommendation2="Further analyze segment {segment} for optimization opportunities.".format(
                segment=random.choice(["A", "B", "C", "D"])
            ),
            confidence=random.randint(85, 99),
            reliability=random.randint(7, 10),
            quality=random.randint(6, 10)
        )
        
        return report
    
    def _generate_random_insight(self) -> str:
        """Generate a random insight to share proactively."""
        insights = [
            "Recent activity patterns suggest an emerging trend in the system interaction dynamics.",
            "A correlation analysis suggests a potential optimization opportunity in the messaging flow.",
            "I've detected an unusual pattern that might be worth investigating further.",
            "Based on historical data, we might expect increased activity in the next cycle.",
            "Recent exchanges show a marked improvement in response quality and relevance."
        ]
        return random.choice(insights)

    async def _generate_response(self, prompt: str, model: str = None, parameters: Union[Dict[str, Any], GenerationParameters] = None) -> str:
        """Generate a response using the LLM."""
        model = model or self.default_model
        
        # If parameters is None, use default parameters with the configured provider
        if parameters is None:
            parameters = self.default_parameters
        # If parameters is a dict, ensure it includes the provider
        elif isinstance(parameters, dict):
            if "provider" not in parameters:
                parameters["provider"] = self.model_provider
            parameters = GenerationParameters(**parameters)
        # If parameters is a GenerationParameters object, ensure provider is set
        else:
            if parameters.provider is None:
                parameters.provider = self.model_provider
        
        logger.debug(f"Generating response on behalf of {self.name}")
        logger.debug(f"Using model: {model}")
        logger.debug(f"Using parameters: {parameters}")
        logger.debug(f"Using provider: {parameters.provider}")
        
        # Use the model client with the specified provider
        async with model_client as client:
            return await client.generate(prompt=prompt, model=model, parameters=parameters)
    
    async def generate_thought(self, context: str) -> Message:
        """Generate a thought based on the current context."""
        # Create a thinking prompt
        thinking_prompt = f"As an analyst, think about the following context and share your thoughts: {context}"
        
        # Generate a thought using the LLM
        thought = await self._generate_response(
            prompt=thinking_prompt,
            model=self.default_model,
            parameters=self.default_parameters
        )
        
        # Create thought message
        thought_message = Message(
            sender_id=self.agent_id,
            message_type="thought",
            content={"text": thought if isinstance(thought, str) else str(thought)},
            timestamp=datetime.now().isoformat()
        )
        
        # Return the thought message - routing and broadcasting will be handled by the agent_manager
        return thought_message
        
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """
        Periodically provide insights based on accumulated data.
        This method is required by the BaseAgent abstract class.
        """
        while True:
            if await self._should_think():
                if self.metrics["messages_analyzed"] > 0:
                    insight = self._generate_random_insight()
                    
                    yield Message(
                        sender_id=self.agent_id,
                        receiver_id="broadcast",
                        content={
                            "text": f"Proactive Insight: {insight}",
                            "data": {"insight": insight}
                        },
                        message_type="insight"
                    )
                
                # Update last think time
                self.last_think_time = datetime.now().timestamp()
            
            # Sleep to avoid busy waiting
            await asyncio.sleep(10)

    def _format_prompt(self, message: Message) -> str:
        """Format the prompt based on the message type."""
        # Extract the message text
        message_text = message.content.get("text", "")
        
        # Select the appropriate prompt template based on message type
        prompt_template = self.prompts.get(
            message.message_type, 
            self.prompts.get("default", "You are a helpful assistant. Please respond to the following: {message}")
        )
        
        # Format the prompt with the message text
        return prompt_template.format(message=message_text)
