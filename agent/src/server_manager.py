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

logger = setup_logging(__name__)
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
            logger.info(f"gRPC connection state changing from '{self._grpc_connection_state}' to '{new_state}'")
            self._grpc_connection_state = new_state
            if self._state_updater:
                changed = self._state_updater.set_grpc_status(new_state)

    def _ensure_connection(self):
        if self.channel is None:
            try:
                self.channel = grpc.aio.insecure_channel(
                    f"{self.server_host}:{self.server_port}",
                    options=grpc_options
                )
                self.stub = AgentRegistrationServiceStub(self.channel)
                self.agent_status_stub = AgentStatusServiceStub(self.channel)
                logger.info(f"gRPC channel created for {self.server_host}:{self.server_port} with keepalive options.")
                self._update_grpc_state("connecting")
                return True
            except Exception as e:
                logger.error(f"Failed to create gRPC channel: {e}")
                self.channel = None
                self.stub = None
                self.agent_status_stub = None
                self._update_grpc_state("failed")
                return False
        return True

    def _on_channel_state_change(self, state):
        logger.info(f"gRPC channel state changed: {state}")
        if state == grpc.ChannelConnectivity.READY:
            self._update_grpc_state("connected")
        elif state == grpc.ChannelConnectivity.CONNECTING:
             self._update_grpc_state("connecting")
        elif state == grpc.ChannelConnectivity.TRANSIENT_FAILURE:
             self._update_grpc_state("unavailable")
        elif state == grpc.ChannelConnectivity.IDLE:
             self._update_grpc_state("idle")
        elif state == grpc.ChannelConnectivity.SHUTDOWN:
             self._update_grpc_state("shutdown")
             self.channel = None
             self.stub = None

    async def check_grpc_readiness(self, timeout: float = agent_config.GRPC_READINESS_CHECK_TIMEOUT, retries: int = agent_config.GRPC_READINESS_CHECK_RETRIES, retry_delay: float = agent_config.GRPC_READINESS_CHECK_RETRY_DELAY) -> bool:
        if not self._ensure_connection():
            return False

        for attempt in range(retries + 1):
            current_state = self.channel.get_state(try_to_connect=True)
            logger.debug(f"Checking gRPC readiness (Attempt {attempt + 1}/{retries + 1}), current state: {current_state}")

            if current_state == grpc.ChannelConnectivity.READY:
                self._update_grpc_state("connected")
                logger.info("gRPC channel is READY.")
                return True

            if current_state == grpc.ChannelConnectivity.SHUTDOWN:
                logger.warning("gRPC channel is SHUTDOWN. Cannot check readiness.")
                self._update_grpc_state("shutdown")
                return False

            try:
                await asyncio.wait_for(self.channel.wait_for_state_change(current_state), timeout=timeout)
                new_state = self.channel.get_state(try_to_connect=False)
                logger.info(f"gRPC state changed from {current_state} to {new_state} (Attempt {attempt + 1})")
                self._on_channel_state_change(new_state)

                if new_state == grpc.ChannelConnectivity.READY:
                    return True
                elif new_state == grpc.ChannelConnectivity.SHUTDOWN:
                    logger.warning("gRPC channel transitioned to SHUTDOWN during readiness check.")
                    return False

            except asyncio.TimeoutError:
                final_state = self.channel.get_state(try_to_connect=False)
                logger.warning(f"gRPC channel state did not change from {current_state} within {timeout}s timeout (Attempt {attempt + 1}). Final state: {final_state}")
                self._on_channel_state_change(final_state)

            except Exception as e:
                 logger.error(f"Error waiting for gRPC channel readiness (Attempt {attempt + 1}): {e}")
                 self._update_grpc_state("failed")
                 return False

            if attempt < retries and self.channel.get_state(try_to_connect=False) != grpc.ChannelConnectivity.READY:
                logger.info(f"Waiting {retry_delay}s before next gRPC readiness check...")
                await asyncio.sleep(retry_delay)

        final_state_after_retries = self.channel.get_state(try_to_connect=False)
        logger.error(f"gRPC channel failed to become ready after {retries + 1} attempts. Final state: {final_state_after_retries}")
        if final_state_after_retries != grpc.ChannelConnectivity.READY:
             self._on_channel_state_change(final_state_after_retries)
        return False

    def _on_channel_state_change(self, state: grpc.ChannelConnectivity):
        logger.info(f"gRPC channel state changed: {state}")
        if state == grpc.ChannelConnectivity.READY:
            self._update_grpc_state("connected")
        elif state == grpc.ChannelConnectivity.CONNECTING:
            self._update_grpc_state("connecting")
        elif state == grpc.ChannelConnectivity.TRANSIENT_FAILURE:
            self._update_grpc_state("unavailable")
        elif state == grpc.ChannelConnectivity.IDLE:
            self._update_grpc_state("disconnected")
        elif state == grpc.ChannelConnectivity.SHUTDOWN:
            self._update_grpc_state("shutdown")
        else:
            logger.warning(f"Unhandled gRPC channel state: {state}")
            self._update_grpc_state("error")

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
        """Sends an unsolicited agent status update to the server using SendAgentStatus RPC."""
        if not self.agent_status_stub:
            logger.error("Cannot send status update: AgentStatusServiceStub not initialized.")
            return False

        if not await self.check_grpc_readiness(timeout=2.0): # Quick check
            logger.error("Cannot send status update: gRPC channel not ready.")
            return False
            
        # Convert metrics to string map if necessary (proto expects map<string, string>)
        metrics_dict = {}
        if metrics:
            for k, v in metrics.items():
                metrics_dict[str(k)] = str(v)
                
        # Use current time if last_seen not provided
        if not last_seen:
            last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        # Construct the AgentInfo message
        agent_info = AgentInfo(
            agent_id=agent_id,
            agent_name=agent_name,
            last_seen=last_seen,
            metrics=metrics_dict
        )

        # Create the request with the agent_info
        request = AgentStatusUpdateRequest(agent=agent_info)
        
        # Use a default timeout if GRPC_CALL_TIMEOUT is not defined
        timeout = getattr(agent_config, 'GRPC_CALL_TIMEOUT', 10.0)  # Default 10 seconds
        
        try:
            logger.debug(f"Sending agent status update for {agent_id}...")
            response = await self.agent_status_stub.SendAgentStatus(request, timeout=timeout)
            if response.success:
                logger.debug(f"Agent status update for {agent_id} successful.")
                return True
            else:
                logger.warning(f"Agent status update for {agent_id} failed on server: {response.message}")
                return False
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error sending agent status update: {e.code()} - {e.details()}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending agent status update: {e}", exc_info=True)
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
            # Unsubscribe callback first to avoid race conditions during shutdown
            self.channel.unsubscribe(self._on_channel_state_change)
            await self.channel.close(grace=grace_period / 2)
            logger.info("gRPC channel closed.")
            self.channel = None # Clear the channel reference
            self._update_grpc_state("shutdown")
        else:
            logger.info("No active gRPC channel to close.")
            self._update_grpc_state("shutdown") # Ensure state reflects shutdown

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

