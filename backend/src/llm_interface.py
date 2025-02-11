from typing import Dict, Optional
import aiohttp
import logging
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the logging level from the .env file
logging_level = os.getenv('LOGGING_LEVEL', 'INFO').upper()

# Set up logging configuration
logging.basicConfig(
    level=getattr(logging, logging_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class LLMInterface:
    def __init__(self, **kwargs):
        # self.base_url = base_url
        self.model='unknown'
        for key, value in kwargs.items():
            logger.info(f'Adding {key}={value} to LLM interface')
            setattr(self, key, value)
        
    async def generate_response(self, 
                              prompt: str, 
                              model: str = "mistral", 
                              parameters: Optional[Dict] = None) -> str:
        """Generate a response from the LLM"""
        logger.debug(f"Generating response from LLM with prompt: {prompt}, model: {model}")
        async with aiohttp.ClientSession() as session:
            data = {
                "model": model,
                "prompt": prompt,
                **(parameters or {})
            }
            logger.debug(f"Sending request to LLM with data: {data}")
            async with session.post(f"{self.base_url}/api/generate", json=data) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type')
                    if 'application/json' in content_type:
                        return await response.json()
                    elif 'application/x-ndjson' in content_type:
                        data = await response.text()
                        logger.debug(f"LLM raw response: {data}")    
                        model_response = "".join([json.loads(line).get('response', '') for line in data.splitlines()])
                        logger.debug(f"LLM parsed response: {model_response}")
                        return model_response
                    else:
                        raise ValueError('Unexpected Content-Type for JSON response')
                else:
                    raise Exception(f"LLM request failed with status {response.status}") 