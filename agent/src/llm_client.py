import os
from mistralai import Mistral
from shared_models import setup_logging

logger = setup_logging(__name__)
logger.propagate = False

class LLMClient:
    """
    Generic LLM client abstraction for agent message processing.
    Handles Mistral AI implementation details.
    """
    def __init__(self, state_update=None):
        """Initialize the LLM client with configuration and state update callback."""
        self.api_key = os.getenv("MISTRAL_API_KEY")
        self.model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
        self.client = None
        self._state_update = state_update
        if self.is_configured():
            try:
                self.client = Mistral(api_key=self.api_key)
                logger.info(f"Mistral client initialized for model: {self.model}")
                if self._state_update:
                    self._state_update('llm_client_status', 'configured')
            except Exception as e:
                logger.error(f"Failed to initialize Mistral client: {e}")
                self.client = None
        else:
            logger.warning("Mistral API key or model not configured. LLMClient disabled.")

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
        try:
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
        except Exception as e:
            logger.error(f"Error calling Mistral API: {e}")
            return f"Error: Failed to get response from LLM - {e}"

    def cleanup(self):
        """Cleanup any resources if necessary."""
        if self.client:
            logger.info("Cleaning up Mistral client resources.")
            self.client = None
        if self._state_update:
            self._state_update('llm_client_status', 'not_configured')
        logger.info("LLMClient cleaned up and deconfigured.")
        return True