from dotenv import load_dotenv
load_dotenv()  # Load .env file early

import os
import logging
import asyncio
from contextlib import asynccontextmanager

# Third-party imports
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Local application/library specific imports
from shared_models import setup_logging
import config
import websocket_handler
import services
import utils
import message_queue_handler
import agent_manager
from grpc_server.grpc_server_setup import create_grpc_server
from grpc_server import grpc_config
import grpc_services.agent_status_service as agent_status_service
import grpc_services.agent_registration_service as agent_registration_service
import grpc_services.broker_registration_service as broker_registration_service



# Initialize logger early
setup_logging()
logger = logging.getLogger(__name__)

# Suppress verbose logging from pika
logging.getLogger("pika").setLevel(logging.WARNING)

# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages application startup and shutdown events."""

    message_queue_handler.get_rabbitmq_connection()

    grpc_server = create_grpc_server(grpc_config.GRPC_PORT)
    await grpc_server.start()
    broker_registration_service.start_registration_service(grpc_server)
    agent_registration_service.start_registration_service(grpc_server)
    agent_status_service.start_agent_status_service(grpc_server)

    await services.start_services()
    utils.setup_signal_handlers()

    message_queue_handler.publish_server_advertisement()

    await agent_manager.broadcast_agent_status_to_all_subscribers(force_full_update=True, is_full_update=True)

    # Start background tasks
    asyncio.create_task(agent_manager.agent_keepalive_checker())

    logger.info("Server startup complete")

    yield # The application runs while yielding

    logger.info("Server shutting down")
    await grpc_server.stop(grace=None)
    logger.info("gRPC server stopped")
    logger.info("Server shutdown complete")

# --- FastAPI App Initialization ---
# Create FastAPI app instance with lifespan manager
app = FastAPI(
    title="Agent Communication Server",
    description="Handles WebSocket connections for agents, frontends, and the broker.",
    version="1.0.0",
    lifespan=lifespan
)

# --- Middleware Setup ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.debug(f"CORS configured with allowed origins: {config.ALLOWED_ORIGINS}")

# --- API Routes ---
# Add the WebSocket endpoint
app.add_websocket_route("/ws", websocket_handler.websocket_endpoint)
logger.debug(f"WebSocket endpoint registered at /ws")

# Basic HTTP route for health check / info
@app.get("/")
async def read_root():
    """Provides basic server information."""
    return {
        "message": "Agent Communication Server is running.",
        "services": {
            "websocket": config.WEBSOCKET_URL, # Use config value
            "grpc": f"{config.GRPC_HOST}:{config.GRPC_PORT}" # Use config values
        }
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    """Checks the health of the server and its dependencies."""
    result = {
        "status": "service_healthy",
        "services": {
            "websocket": True,
            "grpc": True,
            "rabbitmq": message_queue_handler.get_rabbitmq_connection() is not None
        }
    }

    return result

# --- Main Execution ---
if __name__ == "__main__":
    logger.info(f"Starting Server on {config.HOST}:{config.PORT}")

    # Configure and run uvicorn server
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
        reload=False # Typically False in production/non-dev environments
    )

