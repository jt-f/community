"""Default configuration values and environment variable overrides for the agent."""
import logging
import os
import uuid
from typing import Optional, Tuple

from dotenv import load_dotenv


from dotenv import load_dotenv

from shared_models import setup_logging

# Load environment variables from .env file, if it exists
load_dotenv()

# Load environment variables from .env file, if it exists
load_dotenv()

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

# --- Default Configuration Values ---

setup_logging()
logger = logging.getLogger(__name__)

# --- Default Configuration Values ---

# Interval in seconds for sending status updates to the server
AGENT_STATUS_UPDATE_INTERVAL: int = 45
AGENT_STATUS_UPDATE_INTERVAL: int = 45

# Sleep duration in seconds for the main agent loop when idle
AGENT_MAIN_LOOP_SLEEP: float = 5.0
# Sleep duration in seconds for the main agent loop when idle
AGENT_MAIN_LOOP_SLEEP: float = 5.0

# Sleep duration in seconds when the message consumer is paused
AGENT_PAUSED_CONSUMER_SLEEP: float = 0.1
AGENT_PAUSED_CONSUMER_SLEEP: float = 0.1

# Default gRPC host if not set by environment variable
GRPC_HOST_DEFAULT: str = "localhost"
GRPC_HOST_DEFAULT: str = "localhost"

# Default gRPC port if not set by environment variable
GRPC_PORT_DEFAULT: int = 50051
GRPC_PORT_DEFAULT: int = 50051

# gRPC Keepalive settings (milliseconds)
GRPC_KEEPALIVE_TIME_MS: int = 45 * 1000
GRPC_KEEPALIVE_TIMEOUT_MS: int = 15 * 1000
GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS: int = 1 # Boolean represented as 1 (True)
GRPC_KEEPALIVE_TIME_MS: int = 45 * 1000
GRPC_KEEPALIVE_TIMEOUT_MS: int = 15 * 1000
GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS: int = 1 # Boolean represented as 1 (True)

# gRPC call timeout settings (seconds)
GRPC_CALL_TIMEOUT: float = 10.0
GRPC_CALL_TIMEOUT: float = 10.0

# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL_SECONDS: float = 30.0
# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL_SECONDS: float = 30.0

# gRPC Readiness Check settings
GRPC_READINESS_CHECK_TIMEOUT: float = 15.0
GRPC_READINESS_CHECK_RETRIES: int = 3
GRPC_READINESS_CHECK_RETRY_DELAY: float = 2.0
GRPC_READINESS_CHECK_TIMEOUT: float = 15.0
GRPC_READINESS_CHECK_RETRIES: int = 3
GRPC_READINESS_CHECK_RETRY_DELAY: float = 2.0

# Default Mistral model if not set by environment variable
MISTRAL_MODEL_DEFAULT: str = "mistral-small-latest"
MISTRAL_MODEL_DEFAULT: str = "mistral-small-latest"

# Default RabbitMQ host if not set by environment variable
RABBITMQ_HOST_DEFAULT: str = "localhost"
RABBITMQ_HOST_DEFAULT: str = "localhost"

# Default RabbitMQ port if not set by environment variable
RABBITMQ_PORT_DEFAULT: int = 5672
RABBITMQ_PORT_DEFAULT: int = 5672

# RabbitMQ connection settings
RABBITMQ_CONNECTION_ATTEMPTS: int = 3
RABBITMQ_RETRY_DELAY: int = 5 # Seconds
RABBITMQ_CONSUME_INACTIVITY_TIMEOUT: float = 1.0 # Seconds
RABBITMQ_CONNECTION_ATTEMPTS: int = 3
RABBITMQ_RETRY_DELAY: int = 5 # Seconds
RABBITMQ_CONSUME_INACTIVITY_TIMEOUT: float = 1.0 # Seconds

# Timeout for joining the consumer thread during cleanup (seconds)
MQ_CLEANUP_JOIN_TIMEOUT: float = 5.0

# Timeout for joining the consumer thread during cleanup (seconds)
MQ_CLEANUP_JOIN_TIMEOUT: float = 5.0

# Default Agent Name if not set by environment variable
DEFAULT_AGENT_NAME_DEFAULT: str = "Unknown_Agent"

# --- Environment Variable Overrides ---

# Agent Name
DEFAULT_AGENT_NAME: str = os.getenv("DEFAULT_AGENT_NAME", DEFAULT_AGENT_NAME_DEFAULT)
DEFAULT_AGENT_NAME_DEFAULT: str = "Unknown_Agent"

# --- Environment Variable Overrides ---

# Agent Name
DEFAULT_AGENT_NAME: str = os.getenv("DEFAULT_AGENT_NAME", DEFAULT_AGENT_NAME_DEFAULT)

# gRPC Debug Flag (convert '1' to True, otherwise False)
GRPC_DEBUG: bool = os.getenv("GRPC_DEBUG", "0") == "1"
# gRPC Debug Flag (convert '1' to True, otherwise False)
GRPC_DEBUG: bool = os.getenv("GRPC_DEBUG", "0") == "1"

# gRPC Host
GRPC_HOST: str = os.getenv("GRPC_HOST", GRPC_HOST_DEFAULT)
GRPC_HOST: str = os.getenv("GRPC_HOST", GRPC_HOST_DEFAULT)

# gRPC Port (convert to int, handle potential errors)
try:
    GRPC_PORT: int = int(os.getenv("GRPC_PORT", str(GRPC_PORT_DEFAULT)))
except ValueError:
    logger.warning(f"Invalid GRPC_PORT environment variable. Using default: {GRPC_PORT_DEFAULT}")
    GRPC_PORT = GRPC_PORT_DEFAULT
# gRPC Port (convert to int, handle potential errors)
try:
    GRPC_PORT: int = int(os.getenv("GRPC_PORT", str(GRPC_PORT_DEFAULT)))
except ValueError:
    logger.warning(f"Invalid GRPC_PORT environment variable. Using default: {GRPC_PORT_DEFAULT}")
    GRPC_PORT = GRPC_PORT_DEFAULT

# Mistral API Key (required, no default)
MISTRAL_API_KEY: Optional[str] = os.getenv("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    logger.warning("MISTRAL_API_KEY environment variable is not set. LLM functionality may be limited.")
# Mistral API Key (required, no default)
MISTRAL_API_KEY: Optional[str] = os.getenv("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    logger.warning("MISTRAL_API_KEY environment variable is not set. LLM functionality may be limited.")

# Mistral Model
MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", MISTRAL_MODEL_DEFAULT)
MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", MISTRAL_MODEL_DEFAULT)

# RabbitMQ Host
RABBITMQ_HOST: str = os.getenv("RABBITMQ_HOST", RABBITMQ_HOST_DEFAULT)
RABBITMQ_HOST: str = os.getenv("RABBITMQ_HOST", RABBITMQ_HOST_DEFAULT)

# RabbitMQ Port (convert to int, handle potential errors)
try:
    RABBITMQ_PORT: int = int(os.getenv("RABBITMQ_PORT", str(RABBITMQ_PORT_DEFAULT)))
except ValueError:
    logger.warning(f"Invalid RABBITMQ_PORT environment variable. Using default: {RABBITMQ_PORT_DEFAULT}")
    RABBITMQ_PORT = RABBITMQ_PORT_DEFAULT
# RabbitMQ Port (convert to int, handle potential errors)
try:
    RABBITMQ_PORT: int = int(os.getenv("RABBITMQ_PORT", str(RABBITMQ_PORT_DEFAULT)))
except ValueError:
    logger.warning(f"Invalid RABBITMQ_PORT environment variable. Using default: {RABBITMQ_PORT_DEFAULT}")
    RABBITMQ_PORT = RABBITMQ_PORT_DEFAULT

# --- Agent Metadata --- #
# --- Agent Metadata --- #

def create_agent_metadata(agent_name_override: Optional[str] = None) -> Tuple[str, str]:
    """
    Generates a unique agent ID and determines the agent name.

    Uses the provided agent_name_override if available, otherwise falls back
    to the DEFAULT_AGENT_NAME configuration.

    Args:
        agent_name_override: An optional name to assign to the agent.

    Returns:
        A tuple containing the unique agent ID (str) and the agent name (str).
    """
    agent_id = f"agent_{uuid.uuid4()}"
    agent_name = agent_name_override if agent_name_override else DEFAULT_AGENT_NAME
    logger.info(f"Generated Agent ID: {agent_id}, Agent Name: {agent_name}")
def create_agent_metadata(agent_name_override: Optional[str] = None) -> Tuple[str, str]:
    """
    Generates a unique agent ID and determines the agent name.

    Uses the provided agent_name_override if available, otherwise falls back
    to the DEFAULT_AGENT_NAME configuration.

    Args:
        agent_name_override: An optional name to assign to the agent.

    Returns:
        A tuple containing the unique agent ID (str) and the agent name (str).
    """
    agent_id = f"agent_{uuid.uuid4()}"
    agent_name = agent_name_override if agent_name_override else DEFAULT_AGENT_NAME
    logger.info(f"Generated Agent ID: {agent_id}, Agent Name: {agent_name}")
    return agent_id, agent_name

# Log loaded configuration for debugging (optional)
logger.debug(f"Loaded configuration: GRPC_HOST={GRPC_HOST}, GRPC_PORT={GRPC_PORT}, RABBITMQ_HOST={RABBITMQ_HOST}, ...")

# Log loaded configuration for debugging (optional)
logger.debug(f"Loaded configuration: GRPC_HOST={GRPC_HOST}, GRPC_PORT={GRPC_PORT}, RABBITMQ_HOST={RABBITMQ_HOST}, ...")