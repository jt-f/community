import os

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
INCOMING_QUEUE = "incoming_messages_queue"
BROKER_CONTROL_QUEUE = "broker_control_queue"
SERVER_RESPONSE_QUEUE = "server_response_queue"
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