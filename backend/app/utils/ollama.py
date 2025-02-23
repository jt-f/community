import logging
from typing import Optional, Dict, Union
import ollama
from ..utils.logger import get_logger

logger = get_logger(__name__)

class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", max_retries: int = 3):
        self.base_url = base_url
        self.max_retries = max_retries
        self.client = ollama.Client(host=base_url)
        self.DEFAULT_TIMEOUT = 300.0  # 5 minutes
        logger.info(f"Initialized OllamaClient with base_url: {base_url}")
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
        
    def generate(self, prompt: str = "Say a funny thing", model: str = "mistral", parameters: Optional[Dict] = None) -> Union[str, Dict[str, str]]:
        """Generate a response using the Ollama client."""
        try:
            # Send request to Ollama
            response = self.client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options=parameters or {}
            )
            
            if not response or not response.message:
                return {
                    'error': 'No response from Ollama',
                    'details': 'Empty response received'
                }
                
            return response.message.content
                
        except Exception as e:
            logger.error(f"Error in generate: {e}")
            return {
                'error': str(e),
                'details': 'Error generating response'
            }

# Create a singleton instance for the application
ollama_client = OllamaClient() 