from dotenv import load_dotenv
load_dotenv()  # Load .env file early

import os

# --- gRPC Debug Logging ---
# Set gRPC debug env vars BEFORE any grpc import or anything that might import grpc

from shared_models import setup_logging
logger = setup_logging(__name__)  # Initialize logger early

# Add debug log to confirm GRPC_DEBUG value after loading .env
logger.info(f"GRPC_DEBUG environment variable value: {os.getenv('GRPC_DEBUG')}")
if os.getenv("GRPC_DEBUG") == "1":
    os.environ["GRPC_VERBOSITY"] = "DEBUG"
    os.environ["GRPC_TRACE"] = "keepalive,http2_stream_state,http2_ping,http2_flowctl"
else:
    logger.info("gRPC debug logging disabled")  
# --- End gRPC Debug Logging ---

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
import grpc_services
import agent_registration_service



# --- Lifespan Management --- 
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic --- 
    logger.info("Server starting up (lifespan)...")
    # Ensure RabbitMQ connection is attempted before starting services
    rabbitmq_utils.get_rabbitmq_connection()
    
    # Start gRPC server
    grpc_port = int(os.getenv('GRPC_PORT', '50051'))
    grpc_server = grpc_services.start_grpc_server(grpc_port)
    
    # Add agent registration service to the gRPC server
    agent_registration_service.start_registration_service(grpc_server)
    logger.info("Agent registration service added to gRPC server")
    
    await grpc_server.start()
    logger.info(f"gRPC server started on port {grpc_port}")
    
    # Start background services 
    await services.start_services()
    # Advertise server availability via RabbitMQ
    rabbitmq_utils.publish_server_advertisement()
    # Force a broadcast of agent statuses (empty at startup) to synchronize with brokers
    logger.info("Broadcasting initial agent status to any connecting brokers...")
    await agent_manager.broadcast_agent_status(force_full_update=True, is_full_update=True, target_websocket=None)
    # Setup signal handlers for graceful shutdown
    utils.setup_signal_handlers()
    logger.info("Server startup complete (lifespan).")
    
    yield # The application runs while yielding
    
    # --- Shutdown Logic --- 
    logger.info("Server shutting down (lifespan)...")
    # Shutdown gRPC server
    logger.info("Shutting down gRPC server...")
    await grpc_server.stop(grace=None)
    logger.info("gRPC server stopped")
    
    logger.info("Server shutdown initiated via lifespan context.")

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
logger.info(f"CORS configured with allowed origins: {config.ALLOWED_ORIGINS}")

# --- API Routes --- 
# Add the WebSocket endpoint
app.add_websocket_route("/ws", websocket_handler.websocket_endpoint)
logger.info(f"WebSocket endpoint registered at /ws")

# Basic HTTP route for health check / info
@app.get("/")
async def read_root():
    return {
        "message": "Agent Communication Server is running.",
        "services": {
            "websocket": f"ws://{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '8765')}/ws",
            "grpc": f"{os.getenv('GRPC_HOST', '0.0.0.0')}:{os.getenv('GRPC_PORT', '50051')}"
        }
    }

# --- Main Execution --- 
if __name__ == "__main__":
    logger.info(f"Starting Agent Communication Server on port {os.getenv('PORT', '8765')}...")
    logger.info(f"gRPC server will run on port {os.getenv('GRPC_PORT', '50051')}")
    logger.info("Press Ctrl+C to stop the server.")
    
    # Get host and port from environment or use defaults
    server_host = os.getenv('HOST', "0.0.0.0")
    server_port = int(os.getenv('PORT', 8765))

    # Configure uvicorn
    uvicorn_config = uvicorn.Config(
        "main:app",
        host=server_host,
        port=server_port,
        log_level="info",
        reload=False
    )
    server = uvicorn.Server(uvicorn_config)
    
    # Run the server
    server.run()

    logger.info("Server process finished.")