"""
gRPC server implementation for broker registration service
"""
import logging
import time

# Import generated gRPC code
from generated.broker_registration_service_pb2 import BrokerRegistrationResponse
from generated.broker_registration_service_pb2_grpc import (
    BrokerRegistrationServiceServicer, add_BrokerRegistrationServiceServicer_to_server
)

# Import shared modules
from shared_models import setup_logging
import state

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)


class BrokerRegistrationServicer(BrokerRegistrationServiceServicer):
    """Implementation of the BrokerRegistrationService."""

    async def RegisterBroker(self, request, context):
        """
        Register a broker with the server.

        This unary RPC records the broker's ID and updates its last seen time.
        """
        broker_id = request.broker_id
        broker_name = request.broker_name

        logger.info(f"Registering broker: ID='{broker_id}', Name='{broker_name}'")

        async with state.broker_status_lock:
            state.broker_statuses[broker_id] = {
                "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "broker_name": broker_name # Store name as well
            }

        # Return successful response
        return BrokerRegistrationResponse(
            success=True,
            message=f"Broker '{broker_name}' registered successfully with ID '{broker_id}'."
        )


def start_registration_service(server):
    """Add the BrokerRegistrationServiceServicer to the given gRPC server."""
    logger.info("Adding broker registration service to gRPC server")
    add_BrokerRegistrationServiceServicer_to_server(BrokerRegistrationServicer(), server)
