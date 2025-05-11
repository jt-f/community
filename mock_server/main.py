import asyncio
import logging

import grpc

import sys
import os
# Adjust Python path to include the project root directory
# This allows importing modules from sibling directories like 'agent'
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from agent.src.generated import agent_registration_service_pb2_grpc, agent_registration_service_pb2
from agent.src.generated import agent_status_service_pb2_grpc, agent_status_service_pb2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mock_server")

class MockAgentRegistrationService(agent_registration_service_pb2_grpc.AgentRegistrationServiceServicer):
    async def RegisterAgent(self, request, context):
        logger.info(f"RegisterAgent called: agent_id={request.agent_id}, agent_name={request.agent_name}")
        return agent_registration_service_pb2.AgentRegistrationResponse(success=True, message="Registered (mock)")

    async def UnregisterAgent(self, request, context):
        logger.info(f"UnregisterAgent called: agent_id={request.agent_id}")
        return agent_registration_service_pb2.AgentUnregistrationResponse(success=True, message="Unregistered (mock)")

    async def ReceiveCommands(self, request, context):
        logger.info(f"ReceiveCommands called: agent_id={request.agent_id}")
        await asyncio.sleep(0.1)
        return

    async def SendCommandResult(self, request, context):
        logger.info(f"SendCommandResult called: command_id={request.command_id}")
        return agent_registration_service_pb2.CommandResultResponse(success=True, message="Result received (mock)")

    async def SendHeartbeat(self, request, context):
        logger.info(f"SendHeartbeat called: agent_id={request.agent_id}")
        return agent_registration_service_pb2.HeartbeatResponse(success=True, message="Heartbeat received (mock)")

class MockAgentStatusService(agent_status_service_pb2_grpc.AgentStatusServiceServicer):
    async def SendAgentStatus(self, request, context):
        logger.info(f"SendAgentStatus called: agent_id={request.agent.agent_id}, metrics={dict(request.agent.metrics)}")
        return agent_status_service_pb2.AgentStatusUpdateResponse(success=True, message="Status received (mock)")

    async def SubscribeToAgentStatus(self, request, context):
        logger.info(f"SubscribeToAgentStatus called")
        await asyncio.sleep(0.1)
        return

    async def GetAgentStatus(self, request, context):
        logger.info(f"GetAgentStatus called")
        return agent_status_service_pb2.AgentStatusResponse()

async def serve(port=50051):
    server = grpc.aio.server()
    agent_registration_service_pb2_grpc.add_AgentRegistrationServiceServicer_to_server(
        MockAgentRegistrationService(), server)
    agent_status_service_pb2_grpc.add_AgentStatusServiceServicer_to_server(
        MockAgentStatusService(), server)
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)
    logger.info(f"Mock gRPC server listening on {listen_addr}")
    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run a mock gRPC server for agent testing.")
    parser.add_argument("--port", type=int, default=50051, help="Port to listen on (default: 50051)")
    args = parser.parse_args()
    asyncio.run(serve(port=args.port))
