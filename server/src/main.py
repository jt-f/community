import logging
import asyncio
import uvicorn
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import local modules
import config
import websocket_handler
import services
import utils
import rabbitmq_utils # Needed for initial connection check/advertisement

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
logger.info("Pika library logging level set to WARNING.")

# --- Lifespan Management --- 
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic --- 
    logger.info("Server starting up (lifespan)...")
    # Ensure RabbitMQ connection is attempted before starting services
    rabbitmq_utils.get_rabbitmq_connection()
    # Start background services (response consumer, pinger, etc.)
    await services.start_services()
    # Advertise server availability via RabbitMQ
    rabbitmq_utils.publish_server_advertisement()
    # Setup signal handlers for graceful shutdown
    utils.setup_signal_handlers()
    logger.info("Server startup complete (lifespan).")
    
    yield # The application runs while yielding
    
    # --- Shutdown Logic --- 
    logger.info("Server shutting down (lifespan)...")
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
    return {"message": "Agent Communication Server is running."}

# --- Main Execution --- 
if __name__ == "__main__":
    logger.info(f"Starting Agent Communication Server on port {os.getenv('WEBSOCKET_PORT', '8765')}...")
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