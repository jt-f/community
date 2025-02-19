"""
Main FastAPI application entry point.
"""
import signal
import asyncio
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.websocket import router as ws_router
from .api.rest import router as rest_router
from .core.server import agent_server
from .utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="Agent Community API",
    description="A scalable multi-agent system with real-time communication",
    version="0.1.0"
)

# Add CORS middleware with explicit configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,  # Needed for WebSocket
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
    expose_headers=["*"],  # Expose all headers
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Include routers
app.include_router(ws_router)
app.include_router(rest_router)

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info(f"Received exit signal {signal.name}...")
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    for task in tasks:
        task.cancel()
    
    logger.info("Stopping agent server...")
    await agent_server.stop()
    
    logger.info(f"Waiting for {len(tasks)} tasks to cancel")
    await asyncio.gather(*tasks, return_exceptions=True)
    
    loop.stop()
    logger.info("Shutdown complete.")

def handle_exception(loop, context):
    """Handle exceptions that escape the async loop."""
    msg = context.get("exception", context["message"])
    logger.error(f"Caught exception: {msg}")
    logger.info("Shutting down...")
    asyncio.create_task(shutdown(signal.SIGTERM, loop))

@app.on_event("startup")
async def startup_event():
    """Start the agent server on application startup."""
    # Get the current event loop
    loop = asyncio.get_running_loop()
    
    # Add signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s, loop))
        )
    
    # Set up exception handler
    loop.set_exception_handler(handle_exception)
    
    # Start the agent server
    await agent_server.start()
    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the agent server on application shutdown."""
    await agent_server.stop()
    logger.info("Application shutdown complete")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        loop="uvloop",
        use_colors=True
    ) 