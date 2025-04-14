import signal
import sys
import asyncio

# Import state management and service functions
from shared_models import setup_logging
import state
import services

# Configure logging
logger = setup_logging(__name__)

async def shutdown_server():
    """Initiates the server shutdown sequence."""
    logger.info("Initiating server shutdown...")
    
    # 1. Stop background services
    await services.stop_services()

    # 2. Close all WebSocket connections gracefully
    all_connections = list(state.frontend_connections) + list(state.agent_connections.values())
    logger.info(f"Closing {len(all_connections)} WebSocket connections...")
    if all_connections:
        results = await asyncio.gather(
            *[ws.close(code=1001, reason="Server shutdown") for ws in all_connections],
            return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error closing WebSocket during shutdown: {result}")
    logger.info("WebSocket connections closed.")

    # 3. Clear state
    state.agent_connections.clear()
    state.frontend_connections.clear()
    state.agent_statuses.clear()
    state.agent_status_history.clear()
    logger.debug("Server state cleared.")
    
    logger.info("Server shutdown sequence complete.")

def handle_exit(sig, frame):
    """Signal handler for SIGINT and SIGTERM."""
    logger.warning(f"Received exit signal {sig.name}. Initiating graceful shutdown...")
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop found during signal handling. Exiting forcefully.")
        sys.exit(1)

    if loop.is_running():
        shutdown_task = loop.create_task(shutdown_server())
        
        def stop_loop_callback(fut):
            logger.info("Shutdown task finished. Stopping event loop.")
            loop.stop()

        shutdown_task.add_done_callback(stop_loop_callback)
    else:
        logger.warning("Event loop not running during signal handling. Exiting forcefully.")
        sys.exit(1)

def setup_signal_handlers():
    """Sets up signal handlers for graceful shutdown."""
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_exit, sig, None)
        logger.info("Signal handlers registered for SIGINT and SIGTERM.")
    except NotImplementedError:
        logger.warning("asyncio.add_signal_handler not supported, falling back to signal.signal.")
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, handle_exit) 