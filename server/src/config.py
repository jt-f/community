import os

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
BROKER_INPUT_QUEUE = "broker_input_queue"
AGENT_METADATA_QUEUE = "agent_metadata_queue"
BROKER_OUTPUT_QUEUE = "broker_output_queue"
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# WebSocket Configuration
WEBSOCKET_URL = f"ws://{os.getenv('WEBSOCKET_HOST', 'localhost')}:{os.getenv('WEBSOCKET_PORT', '8765')}/ws"

# Server Configuration
SERVER_ID = "server_1"
AGENT_INACTIVITY_TIMEOUT = 15 # seconds
AGENT_PING_INTERVAL = 10 # seconds
PERIODIC_STATUS_INTERVAL = 60 # seconds

# CORS Configuration (adjust as needed for production)
ALLOWED_ORIGINS = ["*"] 