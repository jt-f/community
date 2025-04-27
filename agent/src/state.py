from shared_models import setup_logging

logger = setup_logging(__name__)
logger.propagate = False  # Prevent messages reaching the root logger

class AgentState:
    """
    Simple state class for agent connection and registration status.
    Use set_state/get_state to access state fields, so updates can trigger side effects.
    """
    def __init__(self):
        """Initialize the agent state with default values."""
        self._state = {
            'message_queue_status': 'not_connected',
            'grpc_status': 'not_connected',
            'llm_client_status': 'not_configured',
            'registration_status': 'not_registered',
            'internal_state': 'initializing',
        }

    def set_state(self, key, value):
        """Set the value for a given state key, logging changes."""
        if key not in self._state:
            raise KeyError(f"Invalid state key: {key}")
        if self._state[key] != value:
            self._state[key] = value
        else:
            logger.info(f"State unchanged: {key} is already {value}")

    def get_state(self, key=None):
        """Get the value for a given state key, or all state if key is None."""
        if key is None:
            return self._state.copy()
        if key not in self._state:
            raise KeyError(f"Invalid state key: {key}")
        return self._state[key]

    def __repr__(self):
        """Return a string representation of the agent state."""
        state_lines = ["State:"]
        for key, value in self._state.items():
            state_lines.append(f"  {key}: {value}")
        return "\n".join(state_lines)
