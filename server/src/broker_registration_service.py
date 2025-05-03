"""
gRPC server implementation for broker registration service
"""
import time
import sys
import os
import logging

# Add the parent directory to sys.path so we can import the generated modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import generated gRPC code
from generated.broker_registration_service_pb2 import BrokerRegistrationResponse
from generated.broker_registration_service_pb2_grpc import BrokerRegistrationServiceServicer, add_BrokerRegistrationServiceServicer_to_server

# Import shared modules
from shared_models import setup_logging
import state

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module

class BrokerRegistrationServicer(BrokerRegistrationServiceServicer):
    """Implementation of the BrokerRegistrationService"""
    
    async def RegisterBroker(self, request, context):
        """
        Register a broker with the server.
        This is a unary RPC that registers a broker and returns a success status.
        """
        broker_id = request.broker_id
        broker_name = request.broker_name
        
        logger.info(f"Registering broker: {broker_id} ({broker_name})")
        
        # Update broker status
        async with state.broker_status_lock:
            state.broker_statuses[broker_id] = {
                "last_seen": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
        
        # Return successful response
        return BrokerRegistrationResponse(
            success=True,
            message="Broker registered successfully"
        )

def start_registration_service(server):
    """Add the broker registration service to the gRPC server"""
    logger.info("Adding broker registration service to gRPC server")
    add_BrokerRegistrationServiceServicer_to_server(BrokerRegistrationServicer(), server)
