import logging
import uvicorn
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import local modules
import config
import websocket_handler
import services
import utils
import rabbitmq_utils # Needed for initial connection check/advertisement
from shared_models import setup_logging
import agent_manager
import grpc_services  # Import gRPC services
import agent_registration_service  # Import agent registration service

logger = setup_logging(__name__)

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
    
    # Start background services (response consumer, pinger, etc.)
    await services.start_services()
    # Advertise server availability via RabbitMQ
    rabbitmq_utils.publish_server_advertisement()
    # Force a broadcast of agent statuses (empty at startup) to synchronize with brokers
    logger.info("Broadcasting initial agent status to any connecting brokers...")
    await agent_manager.broadcast_agent_status(force_full_update=True, is_full_update=True)
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
    
    # Graceful shutdown logic is handled by the signal handler calling utils.shutdown_server()
    # However, we can initiate it here as a fallback or if signals aren't caught.
    # Consider if utils.shutdown_server() needs to be called here if signals fail.
    # For now, logging that shutdown is initiated by lifespan context end.
    # If signals are reliable, utils.shutdown_server() might be redundant here.
    logger.info("Server shutdown initiated via lifespan context.")
    # Perform any explicit cleanup needed *after* the app stops serving requests,
    # if not covered by the signal handler's call to shutdown_server.
    # await utils.shutdown_server() # Maybe call this if signals are not the primary mechanism

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

# --- Event Handlers (REMOVED - Now handled by lifespan) --- 
# @app.on_event("startup") ...
# @app.on_event("shutdown") ...

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
    # Note: reload=True is problematic with signal handlers and async tasks.
    # It's better to restart manually during development if needed.
    uvicorn_config = uvicorn.Config(
        "main:app", # Point uvicorn to the app instance in this file
        host=server_host,
        port=server_port,
        log_level="info",
        reload=False # Important: Disable reload for stable async/signal handling
    )
    server = uvicorn.Server(uvicorn_config)
    
    # Run the server (uvicorn handles the async event loop)
    # Uvicorn will also capture SIGINT/SIGTERM and trigger the shutdown event.
    server.run()

    logger.info("Server process finished.") 