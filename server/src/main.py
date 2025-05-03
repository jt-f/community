from dotenv import load_dotenv
load_dotenv()  # Load .env file early

import os
import logging
# --- gRPC Debug Logging ---
# Set gRPC debug env vars BEFORE any grpc import or anything that might import grpc

from shared_models import setup_logging
setup_logging()  # Initialize logger early
logger = logging.getLogger(__name__)
# Import local modules
import config
import websocket_handler
import services
import utils
import rabbitmq_utils

import agent_manager

from grpc_server_setup import create_grpc_server
import agent_status_service
import agent_registration_service
import broker_registration_service


if config.GRPC_DEBUG: # Use config value
    os.environ["GRPC_VERBOSITY"] = "DEBUG"
    os.environ["GRPC_TRACE"] = "keepalive,http2_stream_state,http2_ping,http2_flowctl"

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn  # Import uvicorn for server configuration and execution
from fastapi.middleware.cors import CORSMiddleware

logging.getLogger("pika").setLevel(logging.WARNING)

# Import local modules
import config
import websocket_handler
import services
import utils
import rabbitmq_utils

import agent_manager



@asynccontextmanager
async def lifespan(app: FastAPI):

    rabbitmq_utils.get_rabbitmq_connection()
    grpc_server = create_grpc_server(config.GRPC_PORT)
    
    await grpc_server.start()
    
    broker_registration_service.start_registration_service(grpc_server)
    agent_registration_service.start_registration_service(grpc_server)
    agent_status_service.start_agent_status_service(grpc_server)

    await services.start_services()
    utils.setup_signal_handlers()

    rabbitmq_utils.publish_server_advertisement()

    await agent_manager.broadcast_agent_status(force_full_update=True, is_full_update=True, target_websocket=None)

    logger.info("Server startup complete")
    
    yield # The application runs while yielding
    
    logger.info("Server shutting down")
    logger.info("Shutting down gRPC server")
    await grpc_server.stop(grace=None)
    logger.info("gRPC server stopped")
    logger.info("Server shutdown complete")

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
    result = {
        "status": "service_healthy",
        "services": {
            "websocket": True,
            "grpc": True,
            "rabbitmq": rabbitmq_utils.get_rabbitmq_connection() is not None
        }
    }
    logger.info(f"Health check: {result}")
    return result
    

# --- Main Execution --- 
if __name__ == "__main__":
    logger.info(f"Starting Server") # Use config value
    
    # Get host and port from environment or use defaults
    server_host = config.HOST # Use config value
    server_port = config.PORT # Use config value

    # Configure uvicorn
    uvicorn_config = uvicorn.Config(
        "main:app",
        host=server_host,
        port=server_port,
        log_level="info",
        reload=False
    )
    server = uvicorn.Server(uvicorn_config)
    server.run()

    logger.info("Server process finished.")