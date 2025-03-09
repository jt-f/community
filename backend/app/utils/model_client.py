"""
Generic model client for different LLM providers.
"""
import os
from dotenv import load_dotenv
import pathlib
import logging
import httpx
from typing import Dict, Any, Optional, Union, List
from enum import Enum
from pydantic import BaseModel, Field

from mistralai import Mistral

logger = logging.getLogger(__name__)

class ModelProvider(str, Enum):
    """Supported model providers."""
    OLLAMA = "ollama"
    MISTRAL = "mistral"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    TOGETHER = "together"

class GenerationParameters(BaseModel):
    """Common parameters for text generation across providers."""
    temperature: float = Field(0.7, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=1)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, ge=0)
    stop_sequences: Optional[List[str]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    provider: Optional[ModelProvider] = Field(ModelProvider.OLLAMA)
    
    # Provider-specific parameters
    provider_params: Optional[Dict[str, Any]] = Field(default_factory=dict)

class ModelClient:
    """Generic client for interacting with different LLM providers."""
    
    def __init__(self):
        # Load API keys directly from environment
        load_dotenv()
        load_dotenv(".env.api", override=True)

        self.api_keys = {
            ModelProvider.MISTRAL: os.environ.get("MISTRAL_API_KEY", ""),
            ModelProvider.ANTHROPIC: os.environ.get("ANTHROPIC_API_KEY", ""),
            ModelProvider.OPENAI: os.environ.get("OPENAI_API_KEY", ""),
            ModelProvider.TOGETHER: os.environ.get("TOGETHER_API_KEY", ""),
        }
        
        # Log available keys (without showing the actual keys)
        logger.info(f"API keys available for: {[k for k, v in self.api_keys.items() if v]}")
        
        self.base_urls = {
            ModelProvider.OLLAMA: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            ModelProvider.MISTRAL: "https://api.mistral.ai/v1",
            ModelProvider.ANTHROPIC: "https://api.anthropic.com/v1",
            ModelProvider.OPENAI: "https://api.openai.com/v1",
            ModelProvider.TOGETHER: "https://api.together.xyz/v1",
        }
    
    async def __aenter__(self):
        """Context manager entry."""
        self.client = httpx.AsyncClient(timeout=60.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.client.aclose()
    
    async def generate(self, 
                      prompt: str, 
                      model: str, 
                      parameters: Optional[Union[GenerationParameters, Dict[str, Any]]] = None) -> Union[str, Dict[str, Any]]:
        """Generate text from a prompt using the specified model and parameters."""
        if isinstance(parameters, dict):
            parameters = GenerationParameters(**parameters)
        elif parameters is None:
            parameters = GenerationParameters()
        
        # Get the provider from parameters or use default
        provider = parameters.provider
        
        # Log the API key availability (without showing the actual key)
        api_key = self.api_keys.get(provider, "")
        logger.info(f"Using provider: {provider}")
        logger.info(f"API key for {provider} is {'available' if api_key else 'NOT available'}")
        
        # Validate API key if using a remote provider
        if provider != ModelProvider.OLLAMA and not api_key:
            error_msg = f"No API key found for {provider}. Set {provider.upper()}_API_KEY in .env.api"
            logger.error(error_msg)
            return {"error": error_msg}
        
        logger.info(f"Generating with {provider} using model {model}")
        
        if provider == ModelProvider.OLLAMA:
            return await self._generate_ollama(prompt, model, parameters)
        elif provider == ModelProvider.MISTRAL:
            return await self._generate_mistral(prompt, model, parameters)
        elif provider == ModelProvider.ANTHROPIC:
            return await self._generate_anthropic(prompt, model, parameters)
        elif provider == ModelProvider.OPENAI:
            return await self._generate_openai(prompt, model, parameters)
        elif provider == ModelProvider.TOGETHER:
            return await self._generate_together(prompt, model, parameters)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    async def _generate_ollama(self, prompt: str, model: str, parameters: GenerationParameters) -> str:
        """Generate text using Ollama."""
        url = f"{self.base_urls[ModelProvider.OLLAMA]}/api/generate"
        
        # Map common parameters to Ollama-specific ones
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": parameters.temperature,
            "top_p": parameters.top_p,
            "top_k": parameters.top_k,
            "num_predict": parameters.max_tokens,
        }
        
        # Add any provider-specific parameters
        if parameters.provider_params:
            for key, value in parameters.provider_params.items():
                payload[key] = value
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except Exception as e:
            logger.error(f"Error generating with Ollama: {str(e)}")
            return {"error": str(e)}
    
    async def _generate_mistral(self, prompt: str, model: str, parameters: GenerationParameters) -> str:
        """Generate text using Mistral AI."""
        logger.info(f"Generating with Mistral using model {model}")
        logger.info(f"API key: {self.api_keys[ModelProvider.MISTRAL]}")
        client = Mistral(api_key=self.api_keys[ModelProvider.MISTRAL])
        try:
            chat_response = client.chat.complete(
                model = model,
                messages = [
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ]
            )

            logger.info(chat_response.choices[0].message.content)
            return chat_response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating with Mistral: {str(e)}")
            return {"error": str(e)}
    
    async def _generate_anthropic(self, prompt: str, model: str, parameters: GenerationParameters) -> str:
        """Generate text using Anthropic Claude."""
        url = f"{self.base_urls[ModelProvider.ANTHROPIC]}/messages"
        
        headers = {
            "x-api-key": self.api_keys[ModelProvider.ANTHROPIC],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        # For Anthropic, use their default model if not specified
        if model == "deepseek-r1:1.5b" or "ollama" in model:
            model = "claude-3-haiku-20240307"
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": parameters.temperature,
            "max_tokens": parameters.max_tokens or 1024,
        }
        
        # Add stop sequences if provided
        if parameters.stop_sequences:
            payload["stop_sequences"] = parameters.stop_sequences
        
        # Add top_p if provided
        if parameters.top_p is not None:
            payload["top_p"] = parameters.top_p
        
        # Add any provider-specific parameters
        if parameters.provider_params:
            for key, value in parameters.provider_params.items():
                payload[key] = value
        
        try:
            response = await self.client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            return result["content"][0]["text"]
        except Exception as e:
            logger.error(f"Error generating with Anthropic: {str(e)}")
            return {"error": str(e)}
    
    async def _generate_openai(self, prompt: str, model: str, parameters: GenerationParameters) -> str:
        """Generate text using OpenAI."""
        url = f"{self.base_urls[ModelProvider.OPENAI]}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_keys[ModelProvider.OPENAI]}",
            "Content-Type": "application/json"
        }
        
        # For OpenAI, use their default model if not specified
        if model == "deepseek-r1:1.5b" or "ollama" in model:
            model = "gpt-3.5-turbo"
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": parameters.temperature,
            "max_tokens": parameters.max_tokens or 1024,
            "top_p": parameters.top_p or 0.9,
        }
        
        # Add frequency and presence penalties if provided
        if parameters.frequency_penalty is not None:
            payload["frequency_penalty"] = parameters.frequency_penalty
        
        if parameters.presence_penalty is not None:
            payload["presence_penalty"] = parameters.presence_penalty
        
        # Add stop sequences if provided
        if parameters.stop_sequences:
            payload["stop"] = parameters.stop_sequences
        
        # Add any provider-specific parameters
        if parameters.provider_params:
            for key, value in parameters.provider_params.items():
                payload[key] = value
        
        try:
            response = await self.client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error generating with OpenAI: {str(e)}")
            return {"error": str(e)}
    
    async def _generate_together(self, prompt: str, model: str, parameters: GenerationParameters) -> str:
        """Generate text using Together AI."""
        url = f"{self.base_urls[ModelProvider.TOGETHER]}/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_keys[ModelProvider.TOGETHER]}",
            "Content-Type": "application/json"
        }
        
        # For Together, use their default model if not specified
        if model == "deepseek-r1:1.5b" or "ollama" in model:
            model = "mistralai/Mistral-7B-Instruct-v0.2"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": parameters.temperature,
            "max_tokens": parameters.max_tokens or 1024,
            "top_p": parameters.top_p or 0.9,
            "top_k": parameters.top_k or 40,
        }
        
        # Add stop sequences if provided
        if parameters.stop_sequences:
            payload["stop"] = parameters.stop_sequences
        
        # Add any provider-specific parameters
        if parameters.provider_params:
            for key, value in parameters.provider_params.items():
                payload[key] = value
        
        try:
            response = await self.client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["text"]
        except Exception as e:
            logger.error(f"Error generating with Together: {str(e)}")
            return {"error": str(e)}

# Create a single client instance
model_client = ModelClient() 