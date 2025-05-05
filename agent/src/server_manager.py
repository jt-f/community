"""Manages gRPC communication with the central server for agent registration, status updates, and command handling."""
import asyncio
from datetime import datetime
import grpc
import os

from generated.agent_registration_service_pb2 import (
    AgentRegistrationRequest,
    AgentUnregistrationRequest,
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

    def __init__(self, state_manager: AgentState, command_callback: Callable):
        """Initialize ServerManager.
        Args:
            state_manager: The AgentState instance to monitor and report.
            command_callback: Async function to call when a command is received.
        """
        self.server_host = agent_config.GRPC_HOST
        self.server_port = agent_config.GRPC_PORT
        self.channel = None
        self.stub = None
        self.agent_status_stub = None
        self._command_stream_task = None
        self._command_callback = command_callback
        self._state_manager = state_manager
        self._is_registered = False
        self._grpc_connection_state = "disconnected"
        self._killed = False
        # self.status_update_task = None # Removed: No longer needed

        # Register the handler for state updates
        asyncio.create_task(self._state_manager.register_listener(self._handle_state_update))

    # --- State Update Handler ---
    @log_exceptions
    async def _handle_state_update(self, updated_state: Dict[str, Any]):
        """Callback triggered by AgentState when the state changes."""

        # Check if the agent is registered and connection is ready before sending
        if not self._is_registered or not self.agent_status_stub:
            logger.debug("Skipping status update: Agent not registered or status stub unavailable.")
            return

        if not await self.check_grpc_readiness(timeout=1.0, retries=0): # Quick check
            logger.warning("Skipping status update: gRPC channel not ready.")
            return

        # Extract necessary info from the state updater
        # Use get_full_status_for_update to ensure all relevant data is included
        try:
            agent_id = await self._state_manager.get_agent_id()
            agent_name = await self._state_manager.get_agent_name()
            full_status = await self._state_manager.get_full_status_for_update()
            last_seen = full_status.get('last_updated') # Use the timestamp from the state
            metrics = full_status # Pass the full dictionary as metrics

            if not agent_id or not agent_name:
                logger.warning("Skipping status update: Agent ID or Name not available in state.")
                return

            # Schedule the update to avoid blocking the listener callback
            asyncio.create_task(self.send_agent_status_update(
                agent_id=agent_id,
                agent_name=agent_name,
                last_seen=last_seen,
                metrics=metrics
            ))
        except Exception as e:
            logger.error(f"Error preparing data for state-triggered status update: {e}", exc_info=True)

    # --- gRPC Connection Management ---

    async def _update_grpc_state(self, new_state: str):
        if self._grpc_connection_state != new_state:
            self._grpc_connection_state = new_state
            await self._state_manager.set_grpc_status(new_state)

    async def _ensure_connection(self):
        if self.channel is None:
            try:
                logger.info(f"Creating gRPC channel to {self.server_host}:{self.server_port}")
                self.channel = grpc.aio.insecure_channel(
                    f"{self.server_host}:{self.server_port}",
                    options=grpc_options
                )
                self.stub = AgentRegistrationServiceStub(self.channel)
                self.agent_status_stub = AgentStatusServiceStub(self.channel)
                await self._update_grpc_state("connected")
                return True
            except Exception as e:
                logger.error("Failed to create gRPC channel: %s", e)
                await self._cleanup_connection()
                return False
        return True

    async def _cleanup_connection(self):
        self.channel = None
        self.stub = None
        self.agent_status_stub = None
        await self._update_grpc_state("failed")

    async def check_grpc_readiness(self, *,
                                 timeout: float = agent_config.GRPC_READINESS_CHECK_TIMEOUT,
                                 retries: int = agent_config.GRPC_READINESS_CHECK_RETRIES,
                                 retry_delay: float = agent_config.GRPC_READINESS_CHECK_RETRY_DELAY) -> bool:
        if not await self._ensure_connection():
            logger.warning("gRPC readiness check failed: Could not ensure connection.")
            return False

        logger.debug("Starting gRPC readiness check...")
        for attempt in range(retries + 1):
            current_state = self.channel.get_state(try_to_connect=True)
            logger.debug("gRPC readiness check attempt %d/%d. Current state: %s", attempt + 1, retries + 1, current_state)

            if current_state == grpc.ChannelConnectivity.READY:
                await self._update_grpc_state("connected")

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
                await self._on_channel_state_change(new_state)

                if new_state == grpc.ChannelConnectivity.READY:
                    return True

            except asyncio.TimeoutError:
                final_state = self.channel.get_state(try_to_connect=False)
                logger.warning("gRPC state check timeout after %.1fs", timeout)
                await self._on_channel_state_change(final_state)

            if attempt < retries:
                await asyncio.sleep(retry_delay)

        logger.error("gRPC readiness check failed after %d attempts", retries + 1)
        await self._update_grpc_state("failed") # Ensure state reflects failure
        return False

    async def _on_channel_state_change(self, state: grpc.ChannelConnectivity):
        state_map = {
            grpc.ChannelConnectivity.READY: "connected",
            grpc.ChannelConnectivity.CONNECTING: "connecting",
            grpc.ChannelConnectivity.TRANSIENT_FAILURE: "unavailable",
            grpc.ChannelConnectivity.IDLE: "idle",
            grpc.ChannelConnectivity.SHUTDOWN: "shutdown"
        }
        new_state = state_map.get(state, "error")
        await self._update_grpc_state(new_state)
        if state == grpc.ChannelConnectivity.SHUTDOWN:
            await self._cleanup_connection()

    async def register(self, agent_id: str, agent_name: str) -> bool:
        """
        Registers the agent with the central server via gRPC.
        Args:
            agent_id: The unique identifier for the agent.
            agent_name: The human-readable name for the agent.
        Returns:
            True if registration is successful, False otherwise.
        """
        logger.info(f"Attempting registration for agent {agent_id} ('{agent_name}')...")
        if not await self._ensure_connection(): # Added await
            logger.error("Cannot register agent: Failed to establish gRPC connection.")
            if self._state_manager:
                await self._state_manager.set_registration_status("error") # Added await
                await self._state_manager.set_last_error("gRPC connection failed during registration attempt.") # Added await
            return False

        try:
            # Wait for channel to be ready
            ready = await self.check_grpc_readiness()
            if not ready:
                logger.error("gRPC channel not ready for agent registration.")
                if self._state_manager:
                    await self._state_manager.set_registration_status("error") # Added await
                return False
            else:
                logger.info("gRPC channel is ready for agent registration.")

            # Use the directly imported message class
            request = AgentRegistrationRequest(
                agent_id=agent_id,
                agent_name=agent_name,
                # Add other fields from AgentRegistrationRequest as needed
                version=agent_config.AGENT_VERSION, # Example
                # capabilities={}, # Example
                # hostname=os.uname().nodename, # Example
                # platform=f"{os.uname().sysname} {os.uname().release}" # Example
            )
            logger.info(f"Attempting to register agent '{agent_name}' ({agent_id}) with server...")
            response = await self.stub.RegisterAgent(request, timeout=10)
            if response.success:
                logger.info(f"Agent '{agent_name}' ({agent_id}) registered successfully.")
                self._is_registered = True
                if self._state_manager:
                    await self._state_manager.set_registration_status("registered") # Added await
                    await self._state_manager.set_last_error(None) # Added await
                return True
            else:
                logger.error(f"Agent registration failed: {response.message}")
                if self._state_manager:
                    await self._state_manager.set_registration_status("failed") # Added await
                    await self._state_manager.set_last_error(response.message) # Added await
                return False
        except Exception as e:
            logger.error(f"Exception during agent registration: {e}", exc_info=True)
            if self._state_manager:
                await self._state_manager.set_registration_status("error") # Added await
                await self._state_manager.set_last_error(str(e)) # Added await
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
        logger.debug(f"Attempting to send status update for agent {agent_id}...")
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
                logger.debug(f"Status update for {agent_id} succeeded")
                return True

            logger.warning("Server rejected status update: %s", response.message)
            return False

        except grpc.aio.AioRpcError as e:
            logger.error("gRPC error: %s - %s", e.code().name, e.details())
            return False
        except Exception as e:
            logger.error("Status update failed: %s", e)
            return False

    # --- Periodic Status Update Logic (REMOVED) ---
    # Methods start_status_updater, _status_update_done_callback, _send_status_update_loop removed

    # --- Shutdown Logic ---

    async def shutdown(self, grace_period: float = 5.0):
        """Gracefully shuts down the gRPC connection and stops related tasks."""
        logger.info("Shutting down gRPC Server Manager...")

        # 1. Stop command stream task (if running)
        if self._command_stream_task and not self._command_stream_task.done():
            logger.info("Cancelling command stream task...")
            self._command_stream_task.cancel()
            try:
                await asyncio.wait_for(self._command_stream_task, timeout=grace_period / 2)
                logger.info("Command stream task cancelled.")
            except asyncio.CancelledError:
                logger.info("Command stream task successfully cancelled.")
            except asyncio.TimeoutError:
                logger.warning("Command stream task did not cancel within grace period.")
            except Exception as e:
                logger.error(f"Error waiting for command stream task cancellation: {e}")
        self._command_stream_task = None

        # 2. Stop status update task (REMOVED)
        # No longer needed as status updates are event-driven

        # 3. Close gRPC channel
        if self.channel:
            logger.info("Closing gRPC channel...")
            # Close the channel directly
            await self.channel.close(grace=grace_period / 2)
            logger.info("gRPC channel closed.")
            self.channel = None  # Clear the channel reference
            await self._update_grpc_state("shutdown") # Added await
        else:
            logger.info("No active gRPC channel to close.")
            await self._update_grpc_state("shutdown")  # Ensure state reflects shutdown, Added await

        logger.info("gRPC Server Manager shut down complete.")

    # --- Cleanup Logic ---
    
    @log_exceptions
    async def cleanup(self, agent_id: str, grace_period: float = 5.0):
        """Unregisters the agent and then shuts down the gRPC connection."""

        # 1. Stop command stream task (if running)
        if self._command_stream_task and not self._command_stream_task.done():
            logger.info(f"Starting cleanup for agent {agent_id}...")

        # 1. Attempt Unregistration
        if self._is_registered and self.stub:
            logger.info(f"Checking gRPC readiness for unregistration of agent {agent_id}")
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

        self._command_stream_task = asyncio.create_task(self._command_stream_loop())

    async def _command_stream_loop(self):
        """Continuously listens for commands from the server."""
        logger.info("Starting command stream loop")
        while True:
            logger.debug("Command stream loop waiting for command...")
            try:
                if not self.stub or not self._is_registered:
                    logger.warning("Command stream loop stopping: Not registered or stub not available.")
                    break

                # Await the asynchronous call to get the agent ID
                agent_id = await self._state_manager.get_agent_id()
                if not agent_id:
                    logger.error("Failed to get agent ID, cannot receive commands.")
                    await asyncio.sleep(5) # Wait before retrying or breaking
                    continue # Or break, depending on desired behavior

                request = ReceiveCommandsRequest(agent_id=agent_id)
                async for command in self.stub.ReceiveCommands(request):
                    if not command:
                        continue

                    try:
                        logger.info(f"Received command {command.command_id} of type {command.type} for agent {self._state_manager.get_agent_id()}")
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
                logger.info("Waiting 5 seconds before retrying command stream...")
                await asyncio.sleep(5)  # Wait before retrying
            except Exception as e:
                logger.error(f"Unexpected error in command stream: {e}", exc_info=True)
                logger.info("Waiting 5 seconds before retrying command stream after unexpected error...")
                await asyncio.sleep(5)  # Wait before retrying

        logger.info("Command stream loop stopped.")

