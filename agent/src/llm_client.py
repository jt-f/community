"""Client for interacting with a Large Language Model (LLM), specifically Mistral AI."""
import os
from mistralai import Mistral
from typing import Optional # Add Optional type hint
from shared_models import setup_logging
from state import AgentState # Import the refactored AgentState

logger = setup_logging(__name__)
logger.propagate = False

class LLMClient:
    """
    Generic LLM client abstraction for agent message processing.
    Handles Mistral AI implementation details.
    Uses the AgentState object for state updates.
    """
    def __init__(self, state_updater: Optional[AgentState] = None):
        """Initialize the LLM client with configuration and state update callback."""
        self.api_key = os.getenv("MISTRAL_API_KEY")
        self.model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
        self.client = None
        self._state_updater = state_updater # Store the state object
        if self.is_configured():
            try:
                self.client = Mistral(api_key=self.api_key)
                logger.info(f"Mistral client initialized for model: {self.model}")
                if self._state_updater:
                    self._state_updater.set_llm_status('configured') # Use state object setter
            except Exception as e:
                logger.error(f"Failed to initialize Mistral client: {e}")
                self.client = None
        else:
            logger.warning("Mistral API key or model not configured. LLMClient disabled.")
            if self._state_updater:
                self._state_updater.set_llm_status('not_configured')

    def is_configured(self):
        """Return True if the client is properly configured."""
        return bool(self.api_key and self.model)

    def generate_response(self, prompt, **kwargs):
        """
        Generate a response from the configured Mistral model.
        """
        if not self.client:
            logger.error("LLMClient is not configured or failed to initialize.")
            return "Error: LLM Client not configured."
        logger.info(f"Generating response for prompt: {prompt}")
        chat_response = self.client.chat.complete(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        logger.info(f"Response: {chat_response}")
        if chat_response.choices:
            return chat_response.choices[0].message.content
        logger.warning("Mistral API returned no choices.")
        return "Error: No response from LLM."

    def cleanup(self):
        """Cleanup any resources if necessary."""
        if self.client:
            logger.info("Cleaning up Mistral client resources.")
            self.client = None
        if self._state_updater:
            self._state_updater.set_llm_status('not_configured') # Use state object setter
        logger.info("LLMClient cleaned up and deconfigured.")
        return True