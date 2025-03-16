import logging
import time
from typing import Optional, Dict, Union
import asyncio
from ollama import AsyncClient
from ..utils.logger import get_logger

logger = get_logger(__name__)

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", max_retries: int = 3):
        self.base_url = base_url
        self.max_retries = max_retries
        self.client = AsyncClient(host=base_url)
        self.DEFAULT_TIMEOUT = 300.0  # 5 minutes
        logger.debug(f"Initialized OllamaClient with base_url: {base_url}")

    async def __aenter__(self):
        # Asynchronous setup code here
        return self  # Or some other object

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Asynchronous cleanup code here
        pass

    async def ensure_model_loaded(self, model: str) -> bool:
        """Ensure model is loaded."""
        try:
            # Check if model exists
            await self.client.show(model)
            logger.debug(f"Model {model} is available")
            return True
        except Exception as e:
            if "model not found" in str(e).lower():
                logger.debug(f"Model {model} not found, pulling...")
                try:
                    await self.client.pull(model)
                    logger.debug(f"Successfully pulled model {model}")
                    return True
                except Exception as pull_error:
                    logger.error(f"Error pulling model {model}: {pull_error}")
                    return False
            else:
                logger.error(f"Error checking model {model}: {e}")
                return False
    
    async def generate(self, prompt: str = "Say a funny thing", model: str = "mistral", parameters: Optional[Dict] = None) -> Union[str, Dict[str, str]]:
        """Generate a response using the Ollama client."""
        try:
            logger.debug(f"Generating response for prompt: {prompt} {model} {parameters}")
            # First ensure model is loaded
            if not await self.ensure_model_loaded(model):
                return {
                    'error': f'Failed to load model {model}',
                    'details': 'Model could not be loaded or pulled'
                }

            logger.debug(f"Sending request to Ollama")
            response = await self.client.generate(
                model=model,
                prompt=prompt,
                options=parameters or {}
            )
            logger.debug(f"Received response from Ollama {response}")
            if not response or not response.response:
                return {
                    'error': 'No response from Ollama',
                    'details': 'Empty response received'
                }
            
            return response.response
            
        except Exception as e:
            logger.error(f"Error in generate: {e}")
            return {
                'error': str(e),
                'details': 'Error generating response'
            }

# Create a singleton instance for the application
ollama_client = OllamaClient()