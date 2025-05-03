"""Module responsible for creating and configuring the main gRPC server instance."""
import asyncio
import grpc
from concurrent import futures
import logging
import datetime

# Local imports (assuming config holds keepalive settings)
import config
import state # Needed for agent_keepalive_checker

logger = logging.getLogger(__name__)

# --- Keepalive Settings ---
# Values sourced from config or defined here if preferred
KEEPALIVE_TIME_MS = config.GRPC_KEEPALIVE_TIME_MS
KEEPALIVE_TIMEOUT_MS = config.GRPC_KEEPALIVE_TIMEOUT_MS
KEEPALIVE_PERMIT_WITHOUT_CALLS = config.GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS
MAX_PINGS_WITHOUT_DATA = config.GRPC_MAX_PINGS_WITHOUT_DATA
MIN_PING_INTERVAL_WITHOUT_DATA_MS = config.GRPC_MIN_PING_INTERVAL_WITHOUT_DATA_MS

grpc_options = [
    ('grpc.keepalive_time_ms', KEEPALIVE_TIME_MS),
    ('grpc.keepalive_timeout_ms', KEEPALIVE_TIMEOUT_MS),
    ('grpc.keepalive_permit_without_calls', KEEPALIVE_PERMIT_WITHOUT_CALLS),
    ('grpc.http2.max_pings_without_data', MAX_PINGS_WITHOUT_DATA),
    ('grpc.http2.min_ping_interval_without_data_ms', MIN_PING_INTERVAL_WITHOUT_DATA_MS),
]
# --- End Keepalive Settings ---

# --- Application-level keepalive settings ---
AGENT_KEEPALIVE_INTERVAL_SECONDS = config.AGENT_KEEPALIVE_INTERVAL_SECONDS
AGENT_KEEPALIVE_GRACE_SECONDS = config.AGENT_KEEPALIVE_GRACE_SECONDS

async def agent_keepalive_checker():
    """Periodically checks agent last_seen times and marks inactive agents."""
    while True:
        await asyncio.sleep(AGENT_KEEPALIVE_INTERVAL_SECONDS) # Check interval first
        now = datetime.datetime.now(datetime.timezone.utc)
        agents_to_update = []
        try:
            # Use items() for safe iteration if state might change elsewhere (though updates should be async safe)
            current_agent_states = state.agent_states.copy() # Copy for iteration safety
            for agent_id, agent_state in current_agent_states.items():
                try:
                    last_seen_str = agent_state.last_seen
                    if not last_seen_str:
                        # Should not happen if agent is registered, but handle defensively
                        logger.warning(f"Agent {agent_id} has no last_seen timestamp.")
                        continue

                    last_seen = datetime.datetime.fromisoformat(last_seen_str)
                    # Ensure timezone awareness for comparison
                    if last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)

                    delta = (now - last_seen).total_seconds()

                    # Check if grace period exceeded AND status is not already 'unknown_status'
                    if delta > AGENT_KEEPALIVE_GRACE_SECONDS and agent_state.metrics.get("internal_state") != "unknown_status":
                        logger.warning(f"Agent {agent_id} ({agent_state.agent_name}) missed keepalive window ({delta:.1f}s > {AGENT_KEEPALIVE_GRACE_SECONDS}s). Marking as unknown_status.")
                        # Collect agents that need updating
                        agents_to_update.append((agent_id, agent_state.agent_name))

                except ValueError as ve:
                    logger.error(f"Error parsing last_seen for agent {agent_id} ('{last_seen_str}'): {ve}")
                except Exception as e:
                    logger.error(f"Unexpected error in keepalive check loop for agent {agent_id}: {e}", exc_info=True)

            # Perform state updates outside the iteration loop
            if agents_to_update:
                logger.info(f"Updating status for {len(agents_to_update)} potentially inactive agents...")
                tasks = [
                    state.update_agent_metrics(agent_id, agent_name, {"internal_state": "unknown_status"})
                    for agent_id, agent_name in agents_to_update
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True) # Log errors if update fails
                for result, (agent_id, _) in zip(results, agents_to_update):
                     if isinstance(result, Exception):
                           logger.error(f"Failed to update status for agent {agent_id}: {result}")


        except Exception as e:
             logger.error(f"Error during agent keepalive check cycle: {e}", exc_info=True)


def create_grpc_server(port):
    """Creates and configures the gRPC server instance without starting it."""
    logger.info(f"Creating gRPC server instance")
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=config.GRPC_MAX_WORKERS), # Use config
        options=grpc_options
    )

    # Bind to ports
    listen_addr_ipv4 = f'0.0.0.0:{port}'
    listen_addr_ipv6 = f'[::]:{port}'
    server.add_insecure_port(listen_addr_ipv4)
    logger.debug(f"gRPC server configured to listen on {listen_addr_ipv4}")
    server.add_insecure_port(listen_addr_ipv6)
    logger.debug(f"gRPC server configured to listen on {listen_addr_ipv6}")

    # Start background tasks associated with the server lifecycle
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(agent_keepalive_checker())
    except RuntimeError:
         logger.warning("No running event loop found, cannot start agent keepalive checker automatically.")
         # Consider alternative ways to start this task if running outside an existing loop context

    return server
