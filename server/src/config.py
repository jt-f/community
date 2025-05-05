import os
from shared_models import setup_logging
import logging # Import logging

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module

# --- Environment Variable Loading ---
# Load environment variables with defaults

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))

# WebSocket Configuration
WEBSOCKET_HOST = os.getenv('WEBSOCKET_HOST', 'localhost')
WEBSOCKET_PORT = os.getenv('WEBSOCKET_PORT', '8765')
WEBSOCKET_URL = f"ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}/ws"

# Server Host/Port (for Uvicorn/FastAPI)
HOST = os.getenv('HOST', '0.0.0.0') # Listen on all interfaces by default
PORT = int(os.getenv('PORT', 8765))

# --- Static Configuration ---

# RabbitMQ Queues
BROKER_INPUT_QUEUE = "broker_input_queue"
#AGENT_METADATA_QUEUE = "agent_metadata_queue"
SERVER_INPUT_QUEUE = "server_input_queue"
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# Server Configuration
SERVER_ID = "server_1"
AGENT_INACTIVITY_TIMEOUT = 15 # seconds
AGENT_PING_INTERVAL = 10 # seconds
PERIODIC_STATUS_INTERVAL = 60 # seconds

# CORS Configuration (adjust as needed for production)
ALLOWED_ORIGINS = ["*"]


# --- Application-level Agent Keepalive (used in grpc_server_setup.py) ---
AGENT_KEEPALIVE_INTERVAL_SECONDS = int(os.getenv('AGENT_KEEPALIVE_INTERVAL_SECONDS', 60)) # How often to check
AGENT_KEEPALIVE_GRACE_SECONDS = int(os.getenv('AGENT_KEEPALIVE_GRACE_SECONDS', 120))    # Allowed time since last_seen before unknown_status
AGENT_UNKNOWN_OFFLINE_GRACE_SECONDS = int(os.getenv('AGENT_UNKNOWN_OFFLINE_GRACE_SECONDS', 300)) # Allowed time in unknown_status before marking offline

