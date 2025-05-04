"""Module for centralizing the addition of gRPC services to the server."""

import logging
# Import Servicer Implementations
from grpc_services.agent_status_service import AgentStatusServicer
from grpc_services.agent_registration_service import AgentRegistrationServicer
from grpc_services.broker_registration_service import BrokerRegistrationServicer
# Import generated add functions
from generated.agent_status_service_pb2_grpc import add_AgentStatusServiceServicer_to_server
from generated.agent_registration_service_pb2_grpc import add_AgentRegistrationServiceServicer_to_server
from generated.broker_registration_service_pb2_grpc import add_BrokerRegistrationServiceServicer_to_server


logger = logging.getLogger(__name__)

def add_all_services_to_server(server):
    """Instantiates and adds all gRPC servicers to the server instance."""
    logger.info("Adding gRPC services to the server")

    # Instantiate servicers 
    agent_status_servicer = AgentStatusServicer()
    agent_reg_servicer = AgentRegistrationServicer()
    broker_reg_servicer = BrokerRegistrationServicer()

    # Add servicers to the server
    add_AgentStatusServiceServicer_to_server(agent_status_servicer, server)
    add_AgentRegistrationServiceServicer_to_server(agent_reg_servicer, server)
    add_BrokerRegistrationServiceServicer_to_server(broker_reg_servicer, server)

    logger.info("All gRPC services added to server")
