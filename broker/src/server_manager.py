import os
import asyncio
import random
import grpc
from typing import Callable, Optional
from shared_models import setup_logging, MessageType

logger = setup_logging(__name__)

# Import generated gRPC code
try:
    from generated.agent_status_service_pb2 import AgentStatusRequest
    from generated.agent_status_service_pb2_grpc import AgentStatusServiceStub
    from generated.broker_registration_service_pb2 import BrokerRegistrationRequest, BrokerRegistrationResponse
    from generated.broker_registration_service_pb2_grpc import BrokerRegistrationServiceStub
    GRPC_IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.warning(f"gRPC generated code not found. Please run generate_grpc.py first. Error: {e}")


class ServerManager:
    """
    Handles all gRPC communication for the broker: registration, agent status requests, and agent status subscription.
    Keeps the broker.py clean and focused on message routing/state.
    """
    def __init__(self, broker_id, state_update=None, command_callback=None):
        self.broker_id = broker_id
        self.state_update = state_update
        self.command_callback = command_callback
        self.logger = setup_logging(__name__)
        self.grpc_host = os.getenv("GRPC_HOST", "localhost")
        self.grpc_port = int(os.getenv("GRPC_PORT", "50051"))
        self._grpc_task = None

    async def register(self):
        if not GRPC_IMPORTS_SUCCESSFUL:
            self.logger.error("gRPC imports failed. Cannot register broker.")
            if self.state_update:
                self.state_update('registration_status', 'failed')
            return False

        max_retries = 5
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                channel = grpc.aio.insecure_channel(f"{self.grpc_host}:{self.grpc_port}")
                stub = BrokerRegistrationServiceStub(channel)
                request = BrokerRegistrationRequest(
                    broker_id=self.broker_id,
                    broker_name="BrokerService"
                )
                response = await stub.RegisterBroker(request)
                await channel.close()
                if response.success:
                    self.logger.info(f"Broker registered successfully with ID: {self.broker_id}")
                    self.start_agent_status_subscription()
                    if self.state_update:
                        self.state_update('registration_status', 'registered')
                    return True
                else:
                    self.logger.error(f"Broker registration failed: {response.message}")
                    if self.state_update:
                        self.state_update('registration_status', 'failed')
                    return False

            except grpc.RpcError as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed to register broker: {e}. Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    self.logger.error(f"Error registering broker after {max_retries} attempts: {e}")
                    if self.state_update:
                        self.state_update('registration_status', 'failed')
                    return False
            except Exception as e:
                self.logger.error(f"Unexpected error registering broker: {e}")
                if self.state_update:
                    self.state_update('registration_status', 'failed')
                return False

    async def request_agent_status(self):
        if not GRPC_IMPORTS_SUCCESSFUL:
            self.logger.error("gRPC imports failed. Cannot request agent status.")
            return None
        try:
            async with grpc.aio.insecure_channel(f"{self.grpc_host}:{self.grpc_port}") as channel:
                stub = AgentStatusServiceStub(channel)
                request = AgentStatusRequest(broker_id=self.broker_id)
                response = await stub.GetAgentStatus(request)
                agents_data = []
                for agent in response.agents:
                    agent_data = {
                        "agent_id": agent.agent_id,
                        "agent_name": agent.agent_name,
                        "last_seen": agent.last_seen,
                        "metrics": dict(agent.metrics)
                    }
                    agents_data.append(agent_data)
                status_update = {
                    "message_type": MessageType.AGENT_STATUS_UPDATE,
                    "agents": agents_data,
                    "is_full_update": response.is_full_update
                }

                await self.command_callback(status_update)
                return status_update
        except Exception as e:
            self.logger.error(f"Error requesting agent status via gRPC: {e}")
            return None

    def start_agent_status_subscription(self):
        if self._grpc_task is not None and not self._grpc_task.done():
            self.logger.warning("Agent status subscription already running.")
            return self._grpc_task
        self._grpc_task = asyncio.create_task(self._agent_status_stream_loop())
        self.logger.info("Started agent status subscription task.")
        return self._grpc_task

    async def _agent_status_stream_loop(self, reconnect_interval=5):
        if not GRPC_IMPORTS_SUCCESSFUL:
            self.logger.error("gRPC imports failed. Cannot connect to gRPC server.")
            return
        attempt = 0
        max_backoff = 60
        while True:
            try:
                if attempt > 0:
                    backoff = min(reconnect_interval * (2 ** (attempt - 1)), max_backoff)
                    jitter = backoff * 0.2 * (random.random() * 2 - 1)
                    sleep_time = max(1, backoff + jitter)
                    self.logger.info(f"Attempt {attempt}: Waiting {sleep_time:.1f}s before reconnecting to gRPC server")
                    await asyncio.sleep(sleep_time)
                attempt += 1
                channel = grpc.aio.insecure_channel(f"{self.grpc_host}:{self.grpc_port}")
                stub = AgentStatusServiceStub(channel)
                request = AgentStatusRequest(broker_id=self.broker_id)
                self.logger.info(f"Subscribing to agent status updates as broker {self.broker_id}")
                attempt = 0
                async for response in stub.SubscribeToAgentStatus(request):
                    try:

                        agents_data = []
                        for agent in response.agents:
                            self.logger.info(f"Received agent status update: {agent}")
                            agents_data.append({
                                "agent_id": agent.agent_id,
                                "agent_name": agent.agent_name,
                                "last_seen": agent.last_seen,
                                "metrics": agent.metrics
                            })
                        status_update = {
                            "message_type": MessageType.AGENT_STATUS_UPDATE,
                            "agents": agents_data,
                            "is_full_update": response.is_full_update
                        }
                        self.logger.info(f"Processing agent status update: {status_update}")
                        await self.command_callback(status_update)
                    except Exception as process_err:
                        self.logger.error(f"Error processing agent status update: {process_err}")
                        continue
                self.logger.info("gRPC stream closed normally by server. Reconnecting...")
            except grpc.RpcError as e:
                if hasattr(e, 'code'):
                    code = e.code()
                    details = e.details() if hasattr(e, 'details') else "Unknown details"
                    if code == grpc.StatusCode.UNAVAILABLE:
                        self.logger.error(f"gRPC server unavailable: {details}")
                    elif code == grpc.StatusCode.CANCELLED:
                        self.logger.warning(f"gRPC stream cancelled: {details}")
                    elif code == grpc.StatusCode.DEADLINE_EXCEEDED:
                        self.logger.error(f"gRPC deadline exceeded: {details}")
                    elif code == grpc.StatusCode.UNIMPLEMENTED:
                        self.logger.error(f"gRPC method not implemented: {details}")
                    elif code == grpc.StatusCode.INTERNAL:
                        self.logger.error(f"gRPC internal server error: {details}")
                    else:
                        self.logger.error(f"gRPC error with code {code}: {details}")
                else:
                    self.logger.error(f"gRPC error during agent status stream: {e}")
                try:
                    await channel.close()
                except Exception as close_err:
                    self.logger.warning(f"Error closing gRPC channel: {close_err}")
                continue
            except asyncio.CancelledError:
                self.logger.info("gRPC client task cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error connecting to gRPC server: {e}")
        self.logger.info("gRPC client stopped")

    async def stop(self):
        if self._grpc_task and not self._grpc_task.done():
            self._grpc_task.cancel()
            try:
                await self._grpc_task
            except asyncio.CancelledError:
                self.logger.info("gRPC agent status subscription task cancelled.")
            except Exception as e:
                self.logger.error(f"Error during gRPC task cancellation: {e}")
        self._grpc_task = None
