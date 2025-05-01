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

# gRPC Configuration
GRPC_HOST = os.getenv('GRPC_HOST', '0.0.0.0') # Listen on all interfaces by default
GRPC_PORT = int(os.getenv('GRPC_PORT', 50051))
GRPC_DEBUG = os.getenv("GRPC_DEBUG") == "1"

# Server Host/Port (for Uvicorn/FastAPI)
HOST = os.getenv('HOST', '0.0.0.0') # Listen on all interfaces by default
PORT = int(os.getenv('PORT', 8765))

# --- Static Configuration ---

# RabbitMQ Queues
BROKER_INPUT_QUEUE = "broker_input_queue"
AGENT_METADATA_QUEUE = "agent_metadata_queue"
SERVER_INPUT_QUEUE = "server_input_queue"
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# Server Configuration
SERVER_ID = "server_1"
AGENT_INACTIVITY_TIMEOUT = 15 # seconds
AGENT_PING_INTERVAL = 10 # seconds
PERIODIC_STATUS_INTERVAL = 60 # seconds

# CORS Configuration (adjust as needed for production)
ALLOWED_ORIGINS = ["*"]

logger.info(f"Loaded configuration: RabbitMQ={RABBITMQ_HOST}:{RABBITMQ_PORT}, WebSocket=ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}, gRPC={GRPC_HOST}:{GRPC_PORT}, Server={HOST}:{PORT}, gRPC Debug={GRPC_DEBUG}")