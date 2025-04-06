import logging
import signal
import sys
import asyncio

# Import state management and service functions
import state
import services
import rabbitmq_utils


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("utils")

async def shutdown_server():
    """Initiates the server shutdown sequence."""
    logger.info("Initiating server shutdown...")
    
    # 1. Stop background services
    await services.stop_services()

    # 2. Close all active WebSocket connections gracefully
    logger.info(f"Closing {len(state.active_connections)} active WebSocket connections...")
    # Create a list to avoid modifying the set during iteration
    connections_to_close = list(state.active_connections)
    if connections_to_close:
        results = await asyncio.gather(
            *[ws.close(code=1001, reason="Server shutdown") for ws in connections_to_close],
            return_exceptions=True # Prevent one error from stopping others
        )
        for result in results:
             if isinstance(result, Exception):
                  # Log errors during close, but continue shutdown
                  logger.error(f"Error closing WebSocket during shutdown: {result}")
    logger.info("WebSocket connections closed.")

    # 3. Clear state (optional, helps with clean restart if applicable)
    state.active_connections.clear()
    state.agent_connections.clear()
    state.frontend_connections.clear()
    state.broker_connection = None
    state.agent_statuses.clear()
    state.agent_status_history.clear()
    logger.debug("Server state cleared.")

    # 4. RabbitMQ connection is closed in stop_services() 
    
    logger.info("Server shutdown sequence complete.")

def handle_exit(sig, frame):
    """Signal handler for SIGINT and SIGTERM."""
    logger.warning(f"Received exit signal {sig.name}. Initiating graceful shutdown...")
    
    # Get the running event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
         logger.error("No running event loop found during signal handling. Exiting forcefully.")
         sys.exit(1)

    # Schedule the shutdown coroutine in the event loop
    # Use call_soon_threadsafe if called from a different thread, 
    # but signal handlers usually run in the main thread.
    if loop.is_running():
        # Create a task to run the shutdown
        shutdown_task = loop.create_task(shutdown_server())
        
        # Add a callback to stop the loop once shutdown is complete
        def stop_loop_callback(fut):
            logger.info("Shutdown task finished. Stopping event loop.")
            loop.stop()

        shutdown_task.add_done_callback(stop_loop_callback)
        
        # If loop is not stopping on its own, might need loop.stop() called after shutdown completes
        # This ensures the program exits after shutdown.
    else:
         logger.warning("Event loop not running during signal handling. Attempting synchronous shutdown call (may not work correctly).")
         # Attempting sync call might be problematic in async context
         # asyncio.run(shutdown_server()) # Avoid running a new loop
         sys.exit(1) # Exit if loop isn't running

    # Note: We don't call sys.exit(0) here. The loop stopping should allow the program to exit naturally.

def setup_signal_handlers():
    """Sets up signal handlers for graceful shutdown."""
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Use add_signal_handler for async compatibility
            loop.add_signal_handler(sig, handle_exit, sig, None)
        logger.info(f"Signal handlers registered for SIGINT and SIGTERM.")
    except NotImplementedError:
        # Windows might not support add_signal_handler, fallback to signal.signal
        logger.warning("asyncio.add_signal_handler not supported, falling back to signal.signal (may have limitations).")
        for sig in (signal.SIGINT, signal.SIGTERM):
             signal.signal(sig, handle_exit) # Note: This handler needs to be careful about async calls 