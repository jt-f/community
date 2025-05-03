"""Manages gRPC communication with the central server for agent registration, status updates, and command handling."""
import asyncio
from datetime import datetime
import grpc
import os

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
from typing import Callable, Dict, Any, Optional
from shared_models import setup_logging
from state import AgentState 
from decorators import log_exceptions
import agent_config 
import logging

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module
logger.propagate = False

if agent_config.GRPC_DEBUG:
    os.environ["GRPC_VERBOSITY"] = "DEBUG"
    os.environ["GRPC_TRACE"] = "keepalive,http2_stream_state,http2_ping,http2_flowctl"
    logger.info("gRPC debug logging enabled: GRPC_VERBOSITY=DEBUG, GRPC_TRACE=keepalive,http2_stream_state,http2_ping,http2_flowctl")

grpc_options = [
    ('grpc.keepalive_time_ms', agent_config.GRPC_KEEPALIVE_TIME_MS),
    ('grpc.keepalive_timeout_ms', agent_config.GRPC_KEEPALIVE_TIMEOUT_MS),
    ('grpc.keepalive_permit_without_calls', agent_config.GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS),
]

class ServerManager:
    """
    Handles all gRPC communication with the central server, including registration,
    status updates, command streaming, and command results.
    Uses the AgentState object for state updates.
    """
    def __init__(self, state_updater: Optional[AgentState] = None, command_callback: Optional[Callable] = None):
        self.server_host = agent_config.GRPC_HOST
        self.server_port = agent_config.GRPC_PORT
        self.channel = None
        self.stub = None
        self.agent_status_stub = None
        self._command_stream_task = None
        self._command_callback = command_callback
        self._state_updater = state_updater
        self._is_registered = False
        self._grpc_connection_state = "disconnected"
        self._killed = False
        self.status_update_task = None

    def _update_grpc_state(self, new_state: str):
        if self._grpc_connection_state != new_state:
            logger.info("gRPC connection state changed to %s", new_state)
            self._grpc_connection_state = new_state
            if self._state_updater:
                self._state_updater.set_grpc_status(new_state)

    def _ensure_connection(self):
        if self.channel is None:
            try:
                self.channel = grpc.aio.insecure_channel(
                    f"{self.server_host}:{self.server_port}",
                    options=grpc_options
                )
                self.stub = AgentRegistrationServiceStub(self.channel)
                self.agent_status_stub = AgentStatusServiceStub(self.channel)
                logger.info("Created gRPC channel to %s:%s", self.server_host, self.server_port)
                self._update_grpc_state("connecting")
                return True
            except Exception as e:
                logger.error("Failed to create gRPC channel: %s", e)
                self._cleanup_connection()
                return False
        return True

    def _cleanup_connection(self):
        self.channel = None
        self.stub = None
        self.agent_status_stub = None
        self._update_grpc_state("failed")

    async def check_grpc_readiness(self, *, 
                                 timeout: float = agent_config.GRPC_READINESS_CHECK_TIMEOUT,
                                 retries: int = agent_config.GRPC_READINESS_CHECK_RETRIES,
                                 retry_delay: float = agent_config.GRPC_READINESS_CHECK_RETRY_DELAY) -> bool:
        if not self._ensure_connection():
            return False

        for attempt in range(retries + 1):
            current_state = self.channel.get_state(try_to_connect=True)
            logger.debug("gRPC readiness check attempt %d/%d", attempt + 1, retries + 1)

            if current_state == grpc.ChannelConnectivity.READY:
                self._update_grpc_state("connected")
                return True

            if current_state == grpc.ChannelConnectivity.SHUTDOWN:
                logger.warning("gRPC channel in shutdown state")
                return False

            try:
                await asyncio.wait_for(
                    self.channel.wait_for_state_change(current_state),
                    timeout=timeout
                )
                new_state = self.channel.get_state(try_to_connect=False)
                self._on_channel_state_change(new_state)

                if new_state == grpc.ChannelConnectivity.READY:
                    return True

            except asyncio.TimeoutError:
                final_state = self.channel.get_state(try_to_connect=False)
                logger.warning("gRPC state check timeout after %.1fs", timeout)
                self._on_channel_state_change(final_state)

            if attempt < retries:
                await asyncio.sleep(retry_delay)

        logger.error("gRPC readiness check failed after %d attempts", retries + 1)
        return False

    def _on_channel_state_change(self, state: grpc.ChannelConnectivity):
        state_map = {
            grpc.ChannelConnectivity.READY: "connected",
            grpc.ChannelConnectivity.CONNECTING: "connecting",
            grpc.ChannelConnectivity.TRANSIENT_FAILURE: "unavailable",
            grpc.ChannelConnectivity.IDLE: "idle",
            grpc.ChannelConnectivity.SHUTDOWN: "shutdown"
        }
        new_state = state_map.get(state, "error")
        self._update_grpc_state(new_state)
        if state == grpc.ChannelConnectivity.SHUTDOWN:
            self._cleanup_connection()

    async def register(self, agent_id: str, agent_name: str) -> bool:
        """Register agent with central server.

        Args:
            agent_id: Unique agent identifier
            agent_name: Human-readable agent name

        Returns:
            True if registration succeeded
        """
        if not self._ensure_connection():
            logger.error("gRPC connection unavailable for registration")
            return False

        try:
            request = AgentRegistrationRequest(
                agent_id=agent_id,
                agent_name=agent_name,
                version=agent_config.AGENT_VERSION
            )
            response = await self.stub.RegisterAgent(request, timeout=10)

            if response.success:
                self._is_registered = True
                if self._state_updater:
                    self._state_updater.set_registration_status("registered")
                return True

            logger.error("Registration failed: %s", response.message)
            return False

        except Exception as e:
            logger.error("Registration error: %s", e)
            return False

    def _update_grpc_state(self, status: str):
        if self._state_updater:
            changed = self._state_updater.set_grpc_status(status)
            if changed:
                logger.info(f"Agent gRPC status updated to: {status}")
        else:
            logger.warning("State updater not available, cannot update gRPC status.")

    # --- Registration Logic ---

    async def register(self, agent_id: str, agent_name: str) -> bool:
        """
        Registers the agent with the central server via gRPC.
        Args:
            agent_id: The unique identifier for the agent.
            agent_name: The human-readable name for the agent.
        Returns:
            True if registration is successful, False otherwise.
        """
        if not self._ensure_connection():
            logger.error("Cannot register agent: Failed to establish gRPC connection.")
            if self._state_updater:
                self._state_updater.set_registration_status("error")
                self._state_updater.set_last_error("gRPC connection failed during registration attempt.")
            return False

        try:
            # Wait for channel to be ready
            ready = await self.check_grpc_readiness()
            if not ready:
                logger.error("gRPC channel not ready for agent registration.")
                if self._state_updater:
                    self._state_updater.set_registration_status("error")
                return False

            # Use the directly imported message class
            request = AgentRegistrationRequest(
                agent_id=agent_id,
                agent_name=agent_name,
                # Add other fields from AgentRegistrationRequest as needed
                # version=agent_config.AGENT_VERSION, # Example
                # capabilities={}, # Example
                # hostname=os.uname().nodename, # Example
                # platform=f"{os.uname().sysname} {os.uname().release}" # Example
            )
            logger.info(f"Attempting to register agent '{agent_name}' ({agent_id}) with server...")
            response = await self.stub.RegisterAgent(request, timeout=10)
            if response.success:
                logger.info(f"Agent '{agent_name}' ({agent_id}) registered successfully.")
                self._is_registered = True
                if self._state_updater:
                    self._state_updater.set_registration_status("registered")
                    self._state_updater.set_last_error(None)
                return True
            else:
                logger.error(f"Agent registration failed: {response.message}")
                if self._state_updater:
                    self._state_updater.set_registration_status("failed")
                    self._state_updater.set_last_error(response.message)
                return False
        except Exception as e:
            logger.error(f"Exception during agent registration: {e}", exc_info=True)
            if self._state_updater:
                self._state_updater.set_registration_status("error")
                self._state_updater.set_last_error(str(e))
            return False

    # --- Agent Status Push Logic ---

    @log_exceptions
    async def send_agent_status_update(self, agent_id: str, agent_name: str, last_seen: str = None, metrics: Dict[str, Any] = None) -> bool:
        """Push agent status to server.

        Args:
            agent_id: Unique agent identifier
            agent_name: Human-readable agent name
            last_seen: ISO8601 timestamp of last activity
            metrics: Dictionary of agent metrics

        Returns:
            True if update succeeded
        """
        if not self.agent_status_stub:
            logger.error("Status service unavailable")
            return False

        if not await self.check_grpc_readiness(timeout=2.0):
            logger.error("gRPC channel not ready for status update")
            return False

        metrics_dict = {str(k): str(v) for k, v in (metrics or {}).items()}
        last_seen = last_seen or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            request = AgentStatusUpdateRequest(
                agent=AgentInfo(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    last_seen=last_seen,
                    metrics=metrics_dict
                )
            )
            
            response = await self.agent_status_stub.SendAgentStatus(
                request,
                timeout=getattr(agent_config, 'GRPC_CALL_TIMEOUT', 10.0)
            )

            if response.success:
                logger.debug("Status update for %s succeeded", agent_id)
                return True

            logger.warning("Server rejected status update: %s", response.message)
            return False

        except grpc.aio.AioRpcError as e:
            logger.error("gRPC error: %s - %s", e.code().name, e.details())
            return False
        except Exception as e:
            logger.error("Status update failed: %s", e)
            return False

    # --- Periodic Status Update Logic (Renamed from Heartbeat) ---

    async def start_status_updater(self):
        """Starts the status update loop if not already running."""
        if self.status_update_task and not self.status_update_task.done():
            logger.warning("Status update task already running.")
            return
            
        if not await self.check_grpc_readiness(timeout=5.0): # Ensure connection before starting
            logger.error("Cannot start status updater: gRPC channel not ready.")
            return

        # We have _state_updater instead of state_manager
        if not self._state_updater:
            logger.error("Cannot start status updater: Missing state updater.")
            return
             
        logger.info("Starting status update task...")
        self.status_update_task = asyncio.create_task(self._send_status_update_loop())
        # Optional: Add done callback for logging/cleanup if task finishes unexpectedly
        self.status_update_task.add_done_callback(self._status_update_done_callback)

    def _status_update_done_callback(self, task: asyncio.Task):
        """Callback executed when the status update task finishes."""
        try:
            task.result() # Raises exception if task failed
            logger.info("Status update task finished normally.")
        except asyncio.CancelledError:
            logger.info("Status update task was cancelled.")
        except Exception as e:
            logger.error(f"Status update task exited with error: {e}", exc_info=True)
        finally:
            # Ensure task reference is cleared if it finishes somehow
            if self.status_update_task is task:
                 self.status_update_task = None

    async def _send_status_update_loop(self):
        """Periodically sends status updates using SendAgentStatus RPC."""
        if not self._state_updater:
            logger.error("_send_status_update_loop cannot run: Missing state updater.")
            return
            
        # Use the interval defined in agent_config
        status_update_interval = agent_config.AGENT_STATUS_UPDATE_INTERVAL 
        
        logger.info(f"Starting status update loop with interval {status_update_interval}s.")

        while True:
            try:
                # Gather necessary info from state updater
                agent_id = self._state_updater.get_agent_id()
                agent_name = self._state_updater.get_agent_name()
                full_status = self._state_updater.get_full_status_for_update()
                last_seen = full_status.get('last_updated') # Might be None initially
                metrics = full_status # Pass the full dictionary as metrics

                logger.debug(f"Sending periodic status update for {agent_id}...")
                # Call the existing method that uses SendAgentStatus RPC
                success = await self.send_agent_status_update(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    last_seen=last_seen,
                    metrics=metrics
                )

                if not success:
                    logger.warning("Periodic status update failed.")
                    # Consider adding more robust error handling or backoff here

            except Exception as e:
                logger.error(f"Error in status update loop: {e}", exc_info=True)
                # Avoid spamming logs in case of persistent errors
                await asyncio.sleep(status_update_interval) 

            # Wait for the next interval
            await asyncio.sleep(status_update_interval)

        logger.info("Status update loop stopped.") # Should ideally not be reached unless task cancelled

    # --- Shutdown Logic ---

    async def shutdown(self, grace_period: float = 5.0):
        """Gracefully shuts down the gRPC connection and stops related tasks."""
        logger.info("Shutting down gRPC Server Manager...")

        # 1. Stop status update task (Renamed)
        if self.status_update_task and not self.status_update_task.done():
            logger.info("Cancelling status update task...")
            self.status_update_task.cancel()
            try:
                await asyncio.wait_for(self.status_update_task, timeout=grace_period / 2)
                logger.info("Status update task cancelled.")
            except asyncio.CancelledError:
                logger.info("Status update task successfully cancelled.")
            except asyncio.TimeoutError:
                logger.warning("Status update task did not cancel within grace period.")
            except Exception as e:
                logger.error(f"Error waiting for status update task cancellation: {e}")
        self.status_update_task = None

        # 2. Close gRPC channel
        if self.channel:
            logger.info("Closing gRPC channel...")
            # Close the channel directly
            await self.channel.close(grace=grace_period / 2)
            logger.info("gRPC channel closed.")
            self.channel = None  # Clear the channel reference
            self._update_grpc_state("shutdown")
        else:
            logger.info("No active gRPC channel to close.")
            self._update_grpc_state("shutdown")  # Ensure state reflects shutdown

        logger.info("gRPC Server Manager shut down complete.")

    # --- Cleanup Logic ---
    
    @log_exceptions
    async def cleanup(self, agent_id: str, grace_period: float = 5.0):
        """Unregisters the agent and then shuts down the gRPC connection."""
        logger.info(f"Starting cleanup for agent {agent_id}...")
        
        # 1. Attempt Unregistration
        if self._is_registered and self.stub:
            if await self.check_grpc_readiness(timeout=2.0):
                try:
                    logger.info(f"Attempting to unregister agent {agent_id}...")
                    request = AgentUnregistrationRequest(agent_id=agent_id)
                    # Use a default timeout if GRPC_CALL_TIMEOUT is not defined
                    timeout = getattr(agent_config, 'GRPC_CALL_TIMEOUT', 10.0)  # Default 10 seconds
                    response = await self.stub.UnregisterAgent(request, timeout=timeout)
                    if response.success:
                        logger.info(f"Agent {agent_id} unregistered successfully.")
                    else:
                        logger.warning(f"Agent {agent_id} unregistration failed on server: {response.message}")
                except grpc.aio.AioRpcError as e:
                    logger.error(f"gRPC error during unregistration: {e.code()} - {e.details()}")
                except Exception as e:
                    logger.error(f"Unexpected error during unregistration: {e}", exc_info=True)
            else:
                logger.warning("gRPC channel not ready, skipping unregistration.")
        elif not self._is_registered:
            logger.info("Agent was not registered, skipping unregistration call.")
        else:
            logger.warning("Registration stub not available, cannot unregister.")
            
        self._is_registered = False # Ensure state reflects unregistered

        # 2. Shutdown Connection and Tasks
        await self.shutdown(grace_period)
        
        logger.info(f"Cleanup for agent {agent_id} finished.")

    async def start_command_stream(self):
        """Starts listening for commands from the server."""
        if not self._command_callback:
            logger.error("Cannot start command stream: No command callback provided.")
            return

        if not await self.check_grpc_readiness(timeout=5.0):
            logger.error("Cannot start command stream: gRPC channel not ready.")
            return

        if self._command_stream_task and not self._command_stream_task.done():
            logger.warning("Command stream task already running.")
            return

        logger.info("Starting command stream task...")
        self._command_stream_task = asyncio.create_task(self._command_stream_loop())

    async def _command_stream_loop(self):
        """Continuously listens for commands from the server."""
        while True:
            try:
                if not self.stub or not self._is_registered:
                    logger.warning("Command stream loop stopping: Not registered or stub not available.")
                    break

                request = ReceiveCommandsRequest(agent_id=self._state_updater.get_agent_id())
                async for command in self.stub.ReceiveCommands(request):
                    if not command:
                        continue

                    try:
                        # Convert command to dictionary format
                        command_dict = {
                            "type": command.type,
                            "command_id": command.command_id,
                            "payload": command.payload
                        }
                        # Process command through callback
                        await self._command_callback(command_dict)
                    except Exception as e:
                        logger.error(f"Error processing command: {e}", exc_info=True)

            except grpc.aio.AioRpcError as e:
                if e.code() == grpc.StatusCode.CANCELLED:
                    logger.info("Command stream cancelled.")
                    break
                logger.error(f"gRPC error in command stream: {e.code()} - {e.details()}")
                await asyncio.sleep(5)  # Wait before retrying
            except Exception as e:
                logger.error(f"Unexpected error in command stream: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

        logger.info("Command stream loop stopped.")

