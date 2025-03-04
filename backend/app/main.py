"""
Main FastAPI application entry point.
"""
import signal
import asyncio
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.websocket import router as ws_router
from .api.rest import router as rest_router
from .core.server import agent_server
from .utils.logger import get_logger
from .core.agent_manager import AgentManager

from .core.models import Message

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

# Create agent manager
agent_manager = AgentManager()


# Store active websocket connections
active_connections = set()

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

    # Start the agent manager in the background
    asyncio.create_task(agent_manager.run())

    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the agent server on application shutdown."""
    await agent_server.stop()
    agent_manager.stop()
    logger.info("Application shutdown complete")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            # Create message object
            message = Message(
                sender_id=data.get("sender_id", "user"),
                message_type=data.get("message_type", "user_message"),
                content=data.get("content", {})
            )
            
            # Send to appropriate agent
            agent_id = data.get("agent_id", "analyst")
            for agent in list(agent_manager.available_agents) + list(agent_manager.busy_agents):
                if agent.agent_id == agent_id:
                    await agent.enqueue_message(message)
                    break
    
    except WebSocketDisconnect:
        active_connections.remove(websocket)

# Function to broadcast messages to all connected clients
async def broadcast_message(message: Message):
    for connection in active_connections:
        await connection.send_json(message.dict())

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