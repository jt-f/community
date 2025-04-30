"""Default configuration values for the agent."""
from typing import Optional, Tuple
from shared_models import setup_logging
import uuid
import os

logger = setup_logging(__name__)

###DEFAULTS###
# Interval in seconds for sending status updates to the server
AGENT_STATUS_UPDATE_INTERVAL = 45

# Sleep duration in seconds for the main agent loop
AGENT_MAIN_LOOP_SLEEP = 5

# Sleep duration in seconds when the message consumer is paused
AGENT_PAUSED_CONSUMER_SLEEP = 0.1

# Default gRPC host if not set by environment variable
GRPC_HOST_DEFAULT = "localhost"

# Default gRPC port if not set by environment variable
GRPC_PORT_DEFAULT = 50051

# gRPC Keepalive settings (milliseconds)
GRPC_KEEPALIVE_TIME_MS = 45 * 1000
GRPC_KEEPALIVE_TIMEOUT_MS = 15 * 1000
GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS = 1

# gRPC call timeout settings (seconds)
GRPC_CALL_TIMEOUT = 10.0

# Heartbeat interval (seconds) 
HEARTBEAT_INTERVAL_SECONDS = 30.0

# gRPC Readiness Check settings
GRPC_READINESS_CHECK_TIMEOUT = 15.0
GRPC_READINESS_CHECK_RETRIES = 3
GRPC_READINESS_CHECK_RETRY_DELAY = 2.0

# Default Mistral model if not set by environment variable
MISTRAL_MODEL_DEFAULT = "mistral-small-latest"

# Default RabbitMQ host if not set by environment variable
RABBITMQ_HOST_DEFAULT = "localhost"

# Default RabbitMQ port if not set by environment variable
RABBITMQ_PORT_DEFAULT = 5672

# RabbitMQ connection settings
RABBITMQ_CONNECTION_ATTEMPTS = 3
RABBITMQ_RETRY_DELAY = 5
RABBITMQ_CONSUME_INACTIVITY_TIMEOUT = 1

# Timeout for joining the consumer thread during cleanup
MQ_CLEANUP_JOIN_TIMEOUT = 5
################

###ENV OVERRIDES###
# Default Agent Name if not set by environment variable
DEFAULT_AGENT_NAME = os.getenv("DEFAULT_AGENT_NAME", "Unknown_Agent")

# gRPC Debug Flag
GRPC_DEBUG = os.getenv("GRPC_DEBUG","0") == "1"

# gRPC Host
GRPC_HOST = os.getenv("GRPC_HOST", GRPC_HOST_DEFAULT)

# gRPC Port
GRPC_PORT = int(os.getenv("GRPC_PORT", GRPC_PORT_DEFAULT))

# Mistral API Key
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", None)

# Mistral Model
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", MISTRAL_MODEL_DEFAULT)

# RabbitMQ Host
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", RABBITMQ_HOST_DEFAULT)

# RabbitMQ Port
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", RABBITMQ_PORT_DEFAULT))

################

def create_agent_metadata(agent_name:Optional[str]=None) -> Tuple[str, str]:
    """Create a dictionary containing agent metadata."""
    agent_id = 'agent_'+str(uuid.uuid4())
    agent_name = agent_name or f"Agent_+{agent_id}"

    return agent_id, agent_name