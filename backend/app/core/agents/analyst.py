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
from ...utils.model_client import model_client, ModelProvider, GenerationParameters

# Import ANALYST_CONFIG instead of settings
from .config import ANALYST_CONFIG

logger = get_logger(__name__)

class AnalystAgent(BaseAgent):
    """Analyst agent for processing analysis requests and generating insights."""
    
    def __init__(self,  name: str = "Analyst"):
        super().__init__(name=name)
        self.agent_server = None  # Will be set by the agent_manager
        
        # Get model configuration from ANALYST_CONFIG
        self.default_model = ANALYST_CONFIG.get("model", "deepseek-r1:1.5b")
        self.model_provider = ModelProvider(ANALYST_CONFIG.get("provider", "ollama"))
        
        # Default parameters
        self.default_parameters = GenerationParameters(
            temperature=ANALYST_CONFIG.get("temperature", 0.7),
            top_p=0.9,
            max_tokens=500,
            provider=self.model_provider  # Set the provider from config
        )
        
        self.capabilities = [
            "data_analysis",
            "insight_generation",
            "llm_inference"
        ]
        
    async def _generate_response(self, prompt: str, model: str = None, parameters: Union[GenerationParameters, dict] = None) -> Union[str, dict]:
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
        
        logger.info(f"Generating response on behalf of {self.name}")
        logger.info(f"Using model: {model}")
        logger.info(f"Using parameters: {parameters}")
        logger.info(f"Using provider: {parameters.provider}")
        
        # Use the model client with the specified provider
        async with model_client as client:
            return await client.generate(prompt=prompt, model=model, parameters=parameters)
            
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message and generate an analysis response."""
        try:
            logger.info(f"Analyst agent processing message: {message}")
            
            # Safely get sender_name with a default value
            sender_name = getattr(message, 'sender_name', 'Unknown User')
            
            # Determine which prompt to use based on the message content
            prompt_key = "default"
            if message.content["text"].lower().startswith("chat-"):
                prompt_key = "chat"
            elif message.content["text"].lower().startswith("data-"):
                prompt_key = "data"
            elif message.content["text"].lower().startswith("technical-"):
                prompt_key = "technical"
            
            # Format the prompt using the template from ANALYST_CONFIG
            prompts = ANALYST_CONFIG.get("prompts", {})
            prompt_template = prompts.get(prompt_key, prompts.get("default", "Analyze this: {message}"))
            formatted_prompt = prompt_template.format(message=message.content["text"])
            
            logger.info(f"Using prompt key: {prompt_key}")
            
            # Get parameters from ANALYST_CONFIG with the configured provider
            parameters = GenerationParameters(
                temperature=ANALYST_CONFIG.get("temperature", 0.7),
                provider=self.model_provider
            )
            
            # Generate a response using the model client
            llm_response = await self._generate_response(
                prompt=formatted_prompt,
                model=self.default_model,
                parameters=parameters
            )
            
            if not llm_response or (isinstance(llm_response, dict) and "error" in llm_response):
                error_msg = llm_response.get("error", "Unknown error") if isinstance(llm_response, dict) else "Empty response"
                raise ValueError(f"Error from LLM: {error_msg}")
            
            # Create a response message
            response = Message(
                sender_id=self.agent_id,
                sender_name=self.name,
                receiver_id=message.sender_id,
                receiver_name=sender_name,
                content={"text": llm_response if isinstance(llm_response, str) else str(llm_response)},
                message_type="response",
                timestamp=datetime.now().isoformat()
            )
            
            # Return the response - routing and broadcasting will be handled by the agent_manager
            return response
            
        except Exception as e:
            logger.error(f"Error processing message in AnalystAgent: {str(e)}")
            # Safely get sender_name for error message
            sender_name = getattr(message, 'sender_name', 'Unknown User')
            error_message = Message(
                sender_id=self.agent_id,
                sender_name=self.name,
                receiver_id=message.sender_id,
                receiver_name=sender_name,
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
            message_type="thought",
            content={"text": thought if isinstance(thought, str) else str(thought)},
            timestamp=datetime.now().isoformat()
        )
        
        # Return the thought message - routing and broadcasting will be handled by the agent_manager
        return thought_message
        
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Analyst agents do not think autonomously."""
        yield None
