import os

# gRPC Configuration
GRPC_HOST = os.getenv('GRPC_HOST', '0.0.0.0')  # Listen on all interfaces by default
GRPC_PORT = int(os.getenv('GRPC_PORT', 50051))
GRPC_DEBUG = os.getenv('GRPC_DEBUG') == '1'

# gRPC Keepalive Configuration
GRPC_KEEPALIVE_TIME_MS = int(os.getenv('GRPC_KEEPALIVE_TIME_MS', 60 * 1000))  # 60 seconds
GRPC_KEEPALIVE_TIMEOUT_MS = int(os.getenv('GRPC_KEEPALIVE_TIMEOUT_MS', 20 * 1000))  # 20 seconds
GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS = int(os.getenv('GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS', 1))
GRPC_MAX_PINGS_WITHOUT_DATA = int(os.getenv('GRPC_MAX_PINGS_WITHOUT_DATA', 3))
GRPC_MIN_PING_INTERVAL_WITHOUT_DATA_MS = int(os.getenv('GRPC_MIN_PING_INTERVAL_WITHOUT_DATA_MS', 30 * 1000))  # 30 seconds
GRPC_MAX_WORKERS = int(os.getenv('GRPC_MAX_WORKERS', 10))  # Max workers for the gRPC thread pool


# --- gRPC Debug Logging ---
# Set gRPC debug env vars BEFORE any grpc import or anything that might import grpc
if GRPC_DEBUG:
    os.environ["GRPC_VERBOSITY"] = "DEBUG"
    os.environ["GRPC_TRACE"] = "keepalive,http2_stream_state,http2_ping,http2_flowctl"