"""Default configuration values for the broker."""
import os
from shared_models import setup_logging

logger = setup_logging(__name__)

################
# gRPC Settings
GRPC_HOST_DEFAULT = "localhost"
GRPC_PORT_DEFAULT = 50051

GRPC_HOST = os.getenv("GRPC_HOST", GRPC_HOST_DEFAULT)
GRPC_PORT = int(os.getenv("GRPC_PORT", GRPC_PORT_DEFAULT))

# RabbitMQ Settings
RABBITMQ_HOST_DEFAULT = "localhost"
RABBITMQ_PORT_DEFAULT = 5672

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", RABBITMQ_HOST_DEFAULT)
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", RABBITMQ_PORT_DEFAULT))

# RabbitMQ connection settings (can add defaults if needed)
RABBITMQ_CONNECTION_ATTEMPTS = 3
RABBITMQ_RETRY_DELAY = 5
################