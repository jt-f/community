"""Default configuration values for the agent."""
from typing import Optional
from shared_models import setup_logging
import uuid

logger = setup_logging(__name__)

################
# Interval in seconds for sending status updates to the server
AGENT_STATUS_UPDATE_INTERVAL = 45

# Sleep duration in seconds for the main agent loop
AGENT_MAIN_LOOP_SLEEP = 5

# Sleep duration in seconds when the message consumer is paused
AGENT_PAUSED_CONSUMER_SLEEP = 0.1
################

def create_agent_metadata(agent_name:Optional[str]=None) -> (str, str):
    """Create a dictionary containing agent metadata."""
    agent_id = 'agent_'+str(uuid.uuid4())
    agent_name = agent_name or f"Agent_+{agent_id}"

    return agent_id, agent_name