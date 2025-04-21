import asyncio
import grpc
import os
import time
from generated.agent_registration_service_pb2 import (
    AgentRegistrationRequest,
    AgentUnregistrationRequest,
    CommandResult,
    HeartbeatRequest,
    ReceiveCommandsRequest
)
from generated.agent_registration_service_pb2_grpc import AgentRegistrationServiceStub
from generated.agent_status_service_pb2 import AgentInfo, AgentStatusUpdateRequest
from generated.agent_status_service_pb2_grpc import AgentStatusServiceStub
from shared_models import setup_logging
logger = setup_logging(__name__)
logger.propagate = False # Prevent messages reaching the root logger

class ServerManager:
    """
    Handles all gRPC communication with the central server, including registration,
    status updates, command streaming, and command results.
    Now stateless regarding agent_id: all methods require agent_id as an argument.
    """
    def __init__(self,  state_update=None, command_callback=None):
        self.server_host = os.getenv("GRPC_HOST", "localhost")
        self.server_port = int(os.getenv("GRPC_PORT", "50051"))
        self.channel = None
        self.stub = None
        self._command_stream_task = None
        self._command_callback = command_callback
        self._state_update = state_update
        self._is_registered = False

    def _ensure_connection(self):
        """Creates the gRPC channel and stub if they don't exist."""
        if self.channel is None or self.stub is None:
            try:
                self.channel = grpc.aio.insecure_channel(f"{self.server_host}:{self.server_port}")
                self.stub = AgentRegistrationServiceStub(self.channel)
                logger.info(f"gRPC channel created for {self.server_host}:{self.server_port}. Connection will be verified on first RPC call.")
                # Removed synchronous grpc.channel_ready_future test which is incompatible with grpc.aio.Channel
                # Connection status will be updated upon successful registration or other RPC calls.
            except Exception as e:
                logger.error(f"Failed to create gRPC channel: {e}")
                self.channel = None
                self.stub = None
                # Update state only if creation fails, not during the check
                if self._state_update:
                    self._state_update('grpc_status', 'failed') 
                return False
        return True

    async def check_grpc_readiness(self, timeout: float = 5.0) -> bool:
        """
        Await the gRPC channel's readiness. Returns True if ready, False if timeout or error.
        """
        if not self.channel:
            return False
        try:
            await asyncio.wait_for(self.channel.channel_ready(), timeout=timeout)
            logger.info("gRPC channel is ready.")
            return True
        except (asyncio.TimeoutError, grpc.aio.AioRpcError) as e:
            logger.error(f"gRPC channel not ready: {e}")
            return False

    async def register(self, agent_id, agent_name, command_callback=None):
        """Register the agent with the server and optionally start the command stream."""
        if not self._ensure_connection():
            return False
        if not await self.check_grpc_readiness():
            logger.error("gRPC channel not ready, cannot register agent.")
            return False
        self._state_update('grpc_status', 'connected')
        request = AgentRegistrationRequest(
            agent_id=agent_id,
            agent_name=agent_name,
        )
        try:
            logger.info(f"Attempting to register agent {agent_name} ({agent_id})...")
            response = await self.stub.RegisterAgent(request)
            if response.success:
                self._is_registered = True
                self._state_update('registration_status', 'registered')

                logger.info(f"Agent registered successfully with ID: {agent_id}")
                self._command_callback = command_callback or self._command_callback

                self.start_command_stream(agent_id, self._command_callback)
                self._state_update('internal_state', 'idle')

                return True
            else:
                logger.error(f"Agent registration failed: {response.message}")
                return False
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error during registration: {e.details()} (Code: {e.code()})")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during registration: {e}")
            return False

    async def unregister(self, agent_id):
        """Unregister the agent from the server."""
        if not self._is_registered or not self.stub or not agent_id:
            logger.warning("Cannot unregister: Agent not registered or connection issue.")
            return False

        request = AgentUnregistrationRequest(agent_id=agent_id)
        try:
            logger.info(f"Attempting to unregister agent {agent_id}...")
            response = await self.stub.UnregisterAgent(request)
            if response.success:
                logger.info("Agent unregistered successfully.")
                self._is_registered = False
                return True
            else:
                logger.error(f"Agent unregistration failed: {response.message}")
                return False
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error during unregistration: {e.details()} (Code: {e.code()})")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during unregistration: {e}")
            return False

    async def send_status_update(self, agent_id, status: str, metrics: dict = None):
        """Send a status update (heartbeat) to the server."""
        if not self._is_registered or not self.stub or not agent_id:
            return False

        request = HeartbeatRequest(
            agent_id=agent_id,
            status=status,
            metrics=metrics or {}
        )
        try:
            logger.info(f"Sending heartbeat/status update '{status}', metrics: {metrics}...")
            response = await self.stub.SendHeartbeat(request, timeout=5.0)
            if response.success:
                logger.debug(f"Heartbeat/Status update '{status}' sent successfully.")
                return True
            else:
                logger.warning(f"Heartbeat/Status update failed on server side.")
                return False
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                 logger.warning(f"gRPC server unavailable for heartbeat.")
            elif e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                 logger.warning(f"gRPC heartbeat timed out.")
            else:
                 logger.error(f"gRPC error during heartbeat: {e.details()} (Code: {e.code()})")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending heartbeat: {e}")
            return False

    async def send_command_result(self, agent_id, command_id: str, result: dict):
        """Send the result of an executed command back to the server."""
        if not self._is_registered or not self.stub or not agent_id:
            logger.warning("Cannot send command result: Agent not registered.")
            return False

        request = CommandResult(
            command_id=command_id,
            agent_id=agent_id,
            success=result.get("success", False),
            output=result.get("output", ""),
            error_message=result.get("error_message", ""),
            exit_code=result.get("exit_code", 0),
        )
        try:
            logger.info(f"Sending result for command {command_id}...")
            response = await self.stub.SendCommandResult(request, timeout=10.0)
            if response.received:
                logger.info(f"Command result for {command_id} successfully received by server.")
                return True
            else:
                logger.warning(f"Server indicated command result for {command_id} was not received properly.")
                return False
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error sending command result: {e.details()} (Code: {e.code()})")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending command result: {e}")
            return False

    async def send_agent_status_update(self, agent_id, agent_name, last_seen, metrics: dict):
        """Send a full agent status update to the server using the new SendAgentStatus RPC."""
        try:
            agent_info = AgentInfo(
                agent_id=agent_id,
                agent_name=agent_name,
                last_seen=last_seen,
                metrics=metrics
            )
            request = AgentStatusUpdateRequest(agent=agent_info)
            if self.channel is None:
                self._ensure_connection()
            stub = AgentStatusServiceStub(self.channel)
            response = await stub.SendAgentStatus(request)
            logger.info(f"Sent agent status update via SendAgentStatus: {response.message}")
            return response.success
        except Exception as e:
            logger.warning(f"Failed to send agent status update: {e}")
            return False

    async def _command_stream_loop(self, agent_id):
        """Background task to listen for commands from the server."""
        if not self._is_registered or not self.stub or not agent_id:
            logger.error("Command stream cannot start: Agent not registered.")
            return

        logger.info("Starting command stream listener...")
        request = ReceiveCommandsRequest(agent_id=agent_id)

        while self._is_registered:
            try:
                stream = self.stub.ReceiveCommands(request)
                logger.info("Command stream connected.")
                async for command in stream:
                    logger.info(f"Received command: {command}")
                    if self._command_callback:
                        try:
                            command_dict = {
                                "command_id": command.command_id,
                                "type": command.type,
                                "content": command.content,
                                "parameters": dict(command.parameters),
                                "is_cancellation": command.is_cancellation,
                            }
                            if asyncio.iscoroutinefunction(self._command_callback):
                                result = await self._command_callback(command_dict)
                            else:
                                result = self._command_callback(command_dict)

                            if result and isinstance(result, dict):
                                 await self.send_command_result(agent_id, command.command_id, result)

                        except Exception as e:
                            logger.error(f"Error executing command callback for {command.command_id}: {e}", exc_info=True)
                            await self.send_command_result(agent_id, command.command_id, {
                                "success": False,
                                "output": "",
                                "error_message": f"Agent failed to execute command: {e}",
                                "exit_code": 1
                            })
                    else:
                        logger.warning("Received command but no callback is registered.")
                        await self.send_command_result(agent_id, command.command_id, {
                            "success": False,
                            "output": "",
                            "error_message": "Agent has no command handler registered.",
                            "exit_code": 1
                        })

            except grpc.aio.AioRpcError as e:
                if e.code() == grpc.StatusCode.CANCELLED:
                    logger.info("Command stream cancelled (likely server shutdown or agent unregistration).")
                    break
                elif e.code() == grpc.StatusCode.UNAVAILABLE:
                    logger.warning("Command stream disconnected: Server unavailable. Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    logger.error(f"gRPC error in command stream: {e.details()} (Code: {e.code()}). Retrying in 5 seconds...")
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error in command stream loop: {e}. Retrying in 10 seconds...", exc_info=True)
                await asyncio.sleep(10)
            finally:
                 if self._is_registered:
                      logger.info("Command stream listener attempt finished, will retry if still registered.")
                 else:
                      logger.info("Command stream listener stopped because agent is no longer registered.")

    def start_command_stream(self, agent_id, callback):
        """Starts the background command stream listener task."""
        if not self._is_registered:
             logger.error("Cannot start command stream: Agent not registered.")
             return

        if self._command_stream_task and not self._command_stream_task.done():
            logger.warning("Command stream task already running.")
            return

        self._command_callback = callback
        self._command_stream_task = asyncio.create_task(self._command_stream_loop(agent_id))
        logger.info("Command stream task created.")

    async def cleanup(self, agent_id):
        """Clean up gRPC resources."""
        logger.info("Cleaning up ServerManager gRPC resources...")


        if self._command_stream_task and not self._command_stream_task.done():
            logger.info("Cancelling command stream task...")
            self._command_stream_task.cancel()
            try:
                await self._command_stream_task
            except asyncio.CancelledError:
                logger.info("Command stream task successfully cancelled.")

            except Exception as e:
                 logger.error(f"Error during command stream task cancellation: {e}")

        await self.unregister(agent_id)
        self._is_registered = False
        self._state_update('registration_status', 'not_registered')

        if self.channel:
            logger.info("Closing gRPC channel.")
            await self.channel.close()
            self._state_update('grpc_status', 'disconnected')
            self.channel = None
            self.stub = None

        logger.info("ServerManager cleanup complete.")