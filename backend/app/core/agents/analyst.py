"""
Analyst agent implementation.
"""
import asyncio
from typing import Optional, AsyncGenerator, Union, Dict, Any
import time
import logging
from datetime import datetime

from .base import BaseAgent
from ..models import Message, WebSocketMessage
from ...utils.logger import get_logger
from ...utils.model_client import model_client, ModelProvider, GenerationParameters
from ...utils.message_utils import truncate_message

# Import ANALYST_CONFIG instead of settings
from .config import ANALYST_CONFIG

logger = get_logger(__name__)

class AnalystAgent(BaseAgent):
    """Agent that analyzes data and provides insights."""
    
    def __init__(self, name: str = "Analyst"):
        super().__init__(name=name)
        self.capabilities = [
            "data_analysis",
            "insight_generation",
            "llm_inference"
        ]
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
    
    async def process_message(self, message: Message) -> Optional[Message]:
        """
        Process a message and generate a response.
        
        Note: The agent doesn't set receiver_id - that's the broker's responsibility.
        The agent only sets sender_id and creates the response content.
        """
        try:
            # Set status to thinking
            await self.set_status("thinking")

            # Log the message
            logger.debug(f"Analyst agent {self.name} processing message: {truncate_message(message)}")
            
            # Format the prompt based on the message type
            prompt = self._format_prompt(message)
            
            # Generate a response
            response_text = await self._generate_response(prompt)
            
            # Set status to responding
            await self.set_status("responding")
            
            # Create a response message - note we don't set receiver_id
            # The message broker will determine where this should be routed
            response = Message(
                sender_id=self.agent_id,
                receiver_id="broadcast",
                content={"text": response_text},
                message_type="text",
                in_reply_to=message.message_id if hasattr(message, 'message_id') else None
            )
            
            logger.debug(f"Analyst agent {self.name} generated response: {truncate_message(response)}")
            
            # Set status back to idle
            await self.set_status("idle")
            
            return response
        except Exception as e:
            logger.error(f"Error processing message in analyst agent: {e}", exc_info=True)
            
            # Set status back to idle on error
            await self.set_status("idle")
            
            # Return an error message - without setting receiver_id
            return Message(
                sender_id=self.agent_id,
                # No receiver_id set here - broker's responsibility
                content={"text": f"I encountered an error: {str(e)}"},
                message_type="error",
                in_reply_to=message.message_id if hasattr(message, 'message_id') else None
            )
    
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
        """Analyst agents do not think autonomously."""
        yield None

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
