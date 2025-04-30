"""Client for interacting with a Large Language Model (LLM), specifically Mistral AI."""
import os
from mistralai import Mistral
from typing import Optional # Add Optional type hint
from shared_models import setup_logging
from state import AgentState # Import the refactored AgentState
import agent_config # Import agent configuration

logger = setup_logging(__name__)
logger.propagate = False

class LLMClient:
    """Client for interacting with the LLM API."""
    def __init__(self, state_updater: AgentState):
        self.api_key = agent_config.MISTRAL_API_KEY # Use config value
        self.model = agent_config.MISTRAL_MODEL # Use config value
        if not self.api_key:
            logger.error("MISTRAL_API_KEY environment variable not set.")
        self.client = None
        self._state_updater = state_updater 
        if self.is_configured():
            try:
                self.client = Mistral(api_key=self.api_key)
                logger.info(f"Mistral client initialized for model: {self.model}")
                if self._state_updater:
                    self._state_updater.set_llm_client_status('configured')
            except Exception as e:
                logger.error(f"Failed to initialize Mistral client: {e}")
                self.client = None
        else:
            self._state_updater.set_llm_client_status('not_configured')
            logger.error("Mistral API key or model not configured. LLMClient disabled.")


    def is_configured(self):
        """Return True if the client is properly configured."""
        return bool(self.api_key and self.model)

    def generate_response(self, prompt, **kwargs):
        """
        Generate a response from the configured Mistral model.
        """
        logger.info(f"Generating response for prompt: {prompt}")
        if not self.client:
            logger.error("LLMClient is not configured or failed to initialize.")
            return "Error: LLM Client not configured."

        chat_response = self.client.chat.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )

        logger.debug(f"Response: {chat_response}")
        if chat_response.choices:
            logger.info("LLM response received")
            return chat_response.choices[0].message.content
        logger.warning("Mistral API returned no choices.")
        return "Error: No response from LLM."

    def cleanup(self):
        """Cleanup any resources if necessary."""
        if self.client:
            logger.info("Cleaning up Mistral client resources.")
            self.client = None
        if self._state_updater:
            self._state_updater.set_llm_client_status('not_configured') # Use state object setter
        logger.info("LLMClient cleaned up and deconfigured.")
        return True