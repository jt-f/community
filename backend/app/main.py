"""
Main FastAPI application entry point.
"""
import signal
import asyncio
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from .api.websocket import router as ws_router
from .api.rest import router as rest_router

from .utils.logger import get_logger

from .core.instances import agent_server
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

# Store active websocket connections
active_connections = set()

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.debug(f"Received exit signal {signal.name}...")
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    logger.debug(f"Cancelling {len(tasks)} outstanding tasks")
    for task in tasks:
        task.cancel()
    
    logger.debug("Stopping agent server...")
    await agent_server.stop()
    
    logger.debug(f"Waiting for {len(tasks)} tasks to cancel")
    await asyncio.gather(*tasks, return_exceptions=True)
    
    loop.stop()
    logger.debug("Shutdown complete.")

def handle_exception(loop, context):
    """Handle exceptions that escape the async loop."""
    msg = context.get("exception", context["message"])
    logger.error(f"Caught exception: {msg}")
    logger.debug("Shutting down...")
    asyncio.create_task(shutdown(signal.SIGTERM, loop))

@app.on_event("startup")
async def startup_event():
    """Start the agent server on application startup."""
    logger.info("Application startup...")
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
    agent_manager = agent_server.agent_manager

    # Ensure agent_manager has server reference
    if agent_manager.agent_server is None:
        agent_manager.agent_server = agent_server

    # Create and register default agents
    from .core.agents.human import HumanAgent
    from .core.agents.system import SystemAgent
    from .core.agents.analyst import AnalystAgent
    
    # Create default agents
    human_agent = HumanAgent(name="Human")
    await agent_server.register_agent(human_agent)
    logger.debug(f"Created default Human agent: {human_agent.agent_id}")
    
    system_agent = SystemAgent(name="System")
    await agent_server.register_agent(system_agent)
    logger.debug(f"Created default System agent: {system_agent.agent_id}")
    
    analyst_agent = AnalystAgent(name="Analyst")
    await agent_server.register_agent(analyst_agent)
    logger.debug(f"Created default Analyst agent: {analyst_agent.agent_id}")

    # Start the agent manager in the background
    asyncio.create_task(agent_manager.run())

    logger.info("Application startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the agent server on application shutdown."""
    await agent_server.stop()

    logger.debug("Application shutdown complete")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        use_colors=True
    ) 