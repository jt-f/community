"""Module responsible for creating and configuring the main gRPC server instance."""
import asyncio
import grpc
from concurrent import futures
import logging
import grpc_server.grpc_config as grpc_config

# Local imports
import state  # Needed for agent state access

logger = logging.getLogger(__name__)

# --- Keepalive Settings ---
# Values sourced from grpc_config or defined here if preferred
grpc_options = [
    ('grpc.keepalive_time_ms', grpc_config.GRPC_KEEPALIVE_TIME_MS),
    ('grpc.keepalive_timeout_ms', grpc_config.GRPC_KEEPALIVE_TIMEOUT_MS),
    ('grpc.keepalive_permit_without_calls', grpc_config.GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS),
    ('grpc.http2.max_pings_without_data', grpc_config.GRPC_MAX_PINGS_WITHOUT_DATA),
    ('grpc.http2.min_ping_interval_without_data_ms', grpc_config.GRPC_MIN_PING_INTERVAL_WITHOUT_DATA_MS),
]
# --- End Keepalive Settings ---

def create_grpc_server(port):
    """Creates and configures the gRPC server instance without starting it."""
    logger.info(f"Creating gRPC server instance")
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=grpc_config.GRPC_MAX_WORKERS), # Use config
        options=grpc_options
    )

    # Bind to ports
    listen_addr_ipv4 = f'0.0.0.0:{port}'
    listen_addr_ipv6 = f'[::]:{port}'
    server.add_insecure_port(listen_addr_ipv4)
    server.add_insecure_port(listen_addr_ipv6)


    return server
