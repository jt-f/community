from shared_models import setup_logging
logger = setup_logging(__name__)
logger.propagate = False # Prevent messages reaching the root logger

class AgentState:
    """
    Simple state class for agent connection and registration status.
    Use set_state/get_state to access state fields, so updates can trigger side effects.
    """
    def __init__(self):

        self._state = {
            'message_queue_status': 'not_connected',
            'grpc_status': 'not_connected',
            'llm_client_status': 'not_configured',
            'registration_status': 'not_registered',
            'internal_state': 'initializing',
        }


    def set_state(self, key, value):
        if key not in self._state:
            raise KeyError(f"Invalid state key: {key}")
        if self._state[key] != value:
            self._state[key] = value
        else:
            logger.info(f"State unchanged: {key} is already {value}")

    def get_state(self, key=None):
        if key is None:
            return self._state.copy()
        if key not in self._state:
            raise KeyError(f"Invalid state key: {key}")
        return self._state[key]

    def __repr__(self):
        return (
            f"Agent State:\n"
            f"  Message Queue: {self._state['message_queue_status']}\n"
            f"  gRPC Status:   {self._state['grpc_status']}\n"
            f"  LLM Client:    {self._state['llm_client_status']}\n"
            f"  Registration:  {self._state['registration_status']}\n"
            f"  Internal:      {self._state['internal_state']}"
        )
