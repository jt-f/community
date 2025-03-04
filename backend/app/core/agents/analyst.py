"""
Analyst agent implementation.
"""
import asyncio
from typing import Optional, AsyncGenerator, Union
import time
import logging
from datetime import datetime

from .base import BaseAgent
from ..models import Message, WebSocketMessage
from ...utils.logger import get_logger
from ...utils.ollama import ollama_client

# Import ANALYST_CONFIG instead of settings
from .config import ANALYST_CONFIG

logger = get_logger(__name__)

class AnalystAgent(BaseAgent):
    """Analyst agent for processing analysis requests and generating insights."""
    
    def __init__(self,  name: str = "Analyst"):
        super().__init__( name=name)
        self.agent_server = None  # Will be set by the agent_manager
        
        # Get parameters from ANALYST_CONFIG
        self.parameters = {
            "temperature": ANALYST_CONFIG.get("temperature", 0.7),
            "num_ctx": 4096,
            "num_predict": 2048,
            "top_p": 0.9,
            "top_k": 40
        }
        
        # Get model from ANALYST_CONFIG
        self.default_model = ANALYST_CONFIG.get("model", "deepseek-r1:1.5b")
        self.default_parameters = {
            "temperature": ANALYST_CONFIG.get("temperature", 0.7),
            "top_p": 0.9,
            "max_tokens": 500
        }
        self.capabilities = [
            "data_analysis",
            "insight_generation",
            "llm_inference"
        ]
        
    async def _generate_response(self, prompt: str, model: str = None, parameters: dict = None) -> Union[str, dict]:
        """Generate a response using the LLM."""
        model = model or self.default_model
        parameters = parameters or self.default_parameters
        logger.info(f"Generating response on behalf of {self.name}")
        async with ollama_client as client:
            return await client.generate(prompt=prompt, model=model, parameters=parameters)
            
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message and generate an analysis response."""
        try:
            logger.info(f"Analyst agent processing message: {message}")
            
            # Determine which prompt to use based on the message content
            prompt_key = "default"
            if "technical" in message.content["text"].lower():
                prompt_key = "technical"
            elif "data" in message.content["text"].lower():
                prompt_key = "data"
            
            # Format the prompt using the template from ANALYST_CONFIG
            prompts = ANALYST_CONFIG.get("prompts", {})
            prompt_template = prompts.get(prompt_key, prompts.get("default", "Analyze this: {message}"))
            formatted_prompt = prompt_template.format(message=message.content["text"])
            
            logger.info(f"Using prompt key: {prompt_key}")
            
            # Generate a response using the existing ollama_client
            ollama_response = await self._generate_response(
                prompt=formatted_prompt,
                model=self.default_model,
                parameters=self.parameters
            )
            
            if not ollama_response or (isinstance(ollama_response, dict) and "error" in ollama_response):
                error_msg = ollama_response.get("error", "Unknown error") if isinstance(ollama_response, dict) else "Empty response"
                raise ValueError(f"Error from Ollama: {error_msg}")
            
            # Create a response message
            response = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": ollama_response if isinstance(ollama_response, str) else str(ollama_response)},
                message_type="response",
                timestamp=datetime.now().isoformat()
            )
            
            # Return the response - routing and broadcasting will be handled by the agent_manager
            return response
            
        except Exception as e:
            logger.error(f"Error processing message in AnalystAgent: {str(e)}")
            error_message = Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"Error generating analysis: {str(e)}"},
                message_type="error",
                timestamp=datetime.now().isoformat()
            )
            
            # Return the error message - routing and broadcasting will be handled by the agent_manager
            return error_message

    def should_think(self) -> bool:
        """Determine if the agent should run a thinking cycle."""

        return False

    async def think_once(self) -> Optional[Message]:
        """Run a thinking cycle for the agent."""
        self.last_think_time = time.time()
        
        # Example thinking prompt
        thinking_prompt = "What are some interesting topics to explore today?"
        thought = await self._generate_response(
            prompt=thinking_prompt,
            model=self.default_model,
            parameters=self.default_parameters
        )
        
        # Create thought message
        thought_message = Message(
            sender_id=self.agent_id,
            sender_name=self.name,
            message_type="thought",
            content={"text": thought if isinstance(thought, str) else str(thought)},
            timestamp=datetime.now().isoformat()
        )
        
        # Return the thought message - routing and broadcasting will be handled by the agent_manager
        return thought_message
        
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Analyst agents do not think autonomously."""
        yield None
