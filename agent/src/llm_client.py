"""Client for interacting with a Large Language Model (LLM), specifically Mistral AI."""
import logging
import os
from typing import Any, Dict, Optional

from mistralai import Mistral

import agent_config
from shared_models import setup_logging
from state import AgentState

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)
logger.propagate = False # Prevent duplicate logging if root logger is configured


class LLMClient:
    """Client for interacting with the Mistral LLM API."""

    def __init__(self, state_updater: AgentState):
        """Initialize the Mistral client using configuration and update agent state."""
        self.api_key: Optional[str] = agent_config.MISTRAL_API_KEY
        self.model: str = agent_config.MISTRAL_MODEL
        self.client: Optional[Mistral] = None
        self._state_updater: AgentState = state_updater

        if not self.api_key:
            logger.warning("MISTRAL_API_KEY environment variable not set. LLMClient will be disabled.")
            self._state_updater.set_llm_client_status('not_configured')
            return

        if not self.model:
            logger.warning("MISTRAL_MODEL not configured. Using default may not be intended. LLMClient will be disabled.")
            self._state_updater.set_llm_client_status('not_configured')
            return

        try:
            self.client = Mistral(api_key=self.api_key)
            logger.info(f"Mistral client initialized successfully for model: {self.model}")
            self._state_updater.set_llm_client_status('configured')
        except Exception as e:
            logger.error(f"Failed to initialize Mistral client: {e}", exc_info=True)
            self.client = None
            self._state_updater.set_llm_client_status('error')

    def is_configured(self) -> bool:
        """Check if the client is configured with an API key and model."""
        return bool(self.api_key and self.model and self.client)

    def generate_response(self, prompt: str, **kwargs: Any) -> str:
        """
        Generate a response from the configured Mistral model.

        Args:
            prompt: The input prompt for the LLM.
            **kwargs: Additional arguments to pass to the Mistral API's chat.complete method.

        Returns:
            The generated text response from the LLM, or an error message.
        """
        if not self.is_configured():
            logger.error("LLMClient is not configured or failed initialization. Cannot generate response.")
            return "Error: LLM Client not available."

        logger.info(f"Generating LLM response for prompt (first 100 chars): {prompt[:100]}...")
        try:
            # Ensure self.client is not None before calling methods
            if self.client:
                chat_response = self.client.chat.complete(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    **kwargs
                )
                logger.debug(f"Raw LLM response: {chat_response}")

                if chat_response.choices:
                    response_content = chat_response.choices[0].message.content
                    logger.info("LLM response received successfully.")
                    return response_content
                else:
                    logger.warning("Mistral API returned no choices in the response.")
                    return "Error: No response choices from LLM."
            else:
                # This case should ideally not be reached if is_configured() works correctly
                logger.error("LLMClient.client is None despite is_configured() being True. Cannot generate response.")
                return "Error: LLM Client internal state error."

        except Exception as e:
            logger.error(f"Error during Mistral API call: {e}", exc_info=True)
            self._state_updater.set_llm_client_status('error') # Update state on API error
            return f"Error: Exception during LLM API call: {e}"

    def cleanup(self):
        """Clean up resources, though the Mistral client might not require explicit cleanup."""
        if self.client:
            logger.info("Cleaning up LLMClient resources.")
            # The Mistral client itself might not have an explicit close/cleanup method.
            # Setting to None helps with garbage collection.
            self.client = None
            self._state_updater.set_llm_client_status('disconnected') # Or an appropriate final state
            logger.info("LLMClient resources released.")