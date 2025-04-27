import asyncio
from datetime import datetime
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
from decorators import log_exceptions
logger = setup_logging(__name__)
logger.propagate = False # Prevent messages reaching the root logger

# --- gRPC Debug Logging ---
if os.getenv("GRPC_DEBUG") == "1":
    os.environ["GRPC_VERBOSITY"] = "DEBUG"
    os.environ["GRPC_TRACE"] = "keepalive,http2_stream_state,http2_ping,http2_flowctl"
    logger.info("gRPC debug logging enabled: GRPC_VERBOSITY=DEBUG, GRPC_TRACE=keepalive,http2_stream_state,http2_ping,http2_flowctl")
# --- End gRPC Debug Logging ---

# --- Keepalive Settings ---
# Ping server every 45 seconds if no activity (must be less than server's KEEPALIVE_TIME_MS)
KEEPALIVE_TIME_MS = 45 * 1000
# Wait 15 seconds for the ping ack (must be less than server's KEEPALIVE_TIMEOUT_MS)
KEEPALIVE_TIMEOUT_MS = 15 * 1000
# Send pings even without active calls
KEEPALIVE_PERMIT_WITHOUT_CALLS = 1
# --- End Keepalive Settings ---

grpc_options = [
    ('grpc.keepalive_time_ms', KEEPALIVE_TIME_MS),
    ('grpc.keepalive_timeout_ms', KEEPALIVE_TIMEOUT_MS),
    ('grpc.keepalive_permit_without_calls', KEEPALIVE_PERMIT_WITHOUT_CALLS),
    # ('grpc.enable_retries', 1), # Optional: enable built-in gRPC retries
    # ('grpc.service_config', '{"retryPolicy": ...}') # Optional: configure retry policy
]

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
        self._grpc_connection_state = "disconnected" # Add internal state tracking
        self._killed = False  # Prevent resurrection after kill/unregister

    def _update_grpc_state(self, new_state: str):
        """Helper to update internal and external gRPC state."""
        if self._grpc_connection_state != new_state:
            logger.info(f"gRPC connection state changing from '{self._grpc_connection_state}' to '{new_state}'")
            self._grpc_connection_state = new_state
            if self._state_update:
                # Update the broader agent state via callback
                self._state_update('grpc_status', new_state)
                # Also update internal_state if connection is lost/restored
                if new_state == "unavailable":
                     self._state_update('internal_state', 'unavailable')
                elif new_state == "connected":
                     # If we just reconnected, go back to idle (or let registration handle it)
                     # Avoid overriding 'working' or other states if connection just flickered
                     # Check current internal state before overriding
                     # This part might need refinement based on desired agent behavior on reconnect
                     pass # Let other state updates handle internal_state after connection is back

    def _ensure_connection(self):
        """Creates the gRPC channel and stub if they don't exist."""
        if self.channel is None: # Only create if it doesn't exist at all
            try:
                self.channel = grpc.aio.insecure_channel(
                    f"{self.server_host}:{self.server_port}",
                    options=grpc_options # Pass keepalive options here
                )
                self.stub = AgentRegistrationServiceStub(self.channel)
                logger.info(f"gRPC channel created for {self.server_host}:{self.server_port} with keepalive options.")
                self._update_grpc_state("connecting") # Initial state after creation
                # NOTE: grpc.aio.Channel does NOT support .subscribe. This is only available on the synchronous gRPC API.
                # If you want to track channel state changes in async, you must poll get_state() and use wait_for_state_change().
                return True
            except Exception as e:
                logger.error(f"Failed to create gRPC channel: {e}")
                self.channel = None
                self.stub = None
                self._update_grpc_state("failed")
                return False
        # If channel exists, assume it's trying to connect or is connected based on state changes
        return True

    def _on_channel_state_change(self, state):
        """Callback for gRPC channel state changes."""
        logger.info(f"gRPC channel state changed: {state}")
        if state == grpc.ChannelConnectivity.READY:
            self._update_grpc_state("connected")
        elif state == grpc.ChannelConnectivity.CONNECTING:
             self._update_grpc_state("connecting")
        elif state == grpc.ChannelConnectivity.TRANSIENT_FAILURE:
             self._update_grpc_state("unavailable") # Transient failure means connection lost
        elif state == grpc.ChannelConnectivity.IDLE:
             self._update_grpc_state("idle") # May happen initially or after disconnect
        elif state == grpc.ChannelConnectivity.SHUTDOWN:
             self._update_grpc_state("shutdown")
             self.channel = None # Ensure channel is recreated next time
             self.stub = None

    async def check_grpc_readiness(self, timeout: float = 15.0) -> bool:
        """Checks if the gRPC channel is currently READY."""
        if not self.channel:
             self._ensure_connection() # Attempt to create if missing
             if not self.channel:
                 return False # Failed to create

        connectivity_state = self.channel.get_state(try_to_connect=False) # Don't trigger connection here
        logger.debug(f"Checking gRPC readiness, current state: {connectivity_state}")

        if connectivity_state == grpc.ChannelConnectivity.READY:
            self._update_grpc_state("connected") # Ensure state is accurate
            return True
        elif connectivity_state == grpc.ChannelConnectivity.IDLE:
             # Try to connect if idle
             logger.info("gRPC channel is IDLE, attempting to connect...")
             connectivity_state = self.channel.get_state(try_to_connect=True)
             # Give it a moment to change state
             await asyncio.sleep(0.1)
             connectivity_state = self.channel.get_state(try_to_connect=False)
             if connectivity_state == grpc.ChannelConnectivity.READY:
                 self._update_grpc_state("connected")
                 return True

        # If not ready or idle->ready, wait for connection up to timeout
        try:
            await asyncio.wait_for(self.channel.wait_for_state_change(connectivity_state), timeout=timeout)
            new_state = self.channel.get_state(try_to_connect=False)
            logger.info(f"gRPC state changed to {new_state} after waiting.")
            if new_state == grpc.ChannelConnectivity.READY:
                self._update_grpc_state("connected")
                return True
            else:
                 # Update state based on the new state after waiting
                 self._on_channel_state_change(new_state) # Manually call handler
                 return False
        except asyncio.TimeoutError:
            logger.warning(f"gRPC channel did not become ready within {timeout}s timeout. Current state: {self.channel.get_state(try_to_connect=False)}")
            self._update_grpc_state("unavailable") # Assume unavailable on timeout
            return False
        except Exception as e:
             logger.error(f"Error waiting for gRPC channel readiness: {e}")
             self._update_grpc_state("failed")
             return False

    @log_exceptions
    async def register(self, agent_id, agent_name):
        """Register the agent with the server and optionally start the command stream."""
        if self._killed:
            logger.warning("Agent is killed/shutdown. Registration will not start.")
            return False
        if not self._ensure_connection():
            self._update_grpc_state("failed") # Ensure state reflects failure
            return False
        if not await self.check_grpc_readiness():
            logger.error("gRPC channel not ready, cannot register agent.")
            # State already updated by check_grpc_readiness
            return False
        # If ready, state should be 'connected'
        self._update_grpc_state("connected")

        request = AgentRegistrationRequest(
            agent_id=agent_id,
            agent_name=agent_name,
        )
        try:
            logger.info(f"Attempting to register agent {agent_name} ({agent_id})...")
            response = await self.stub.RegisterAgent(request, timeout=15.0) # Add timeout
            if response.success:
                self._is_registered = True
                # Update agent state via callback
                if self._state_update:
                    self._state_update('registration_status', 'registered')
                    self._state_update('internal_state', 'idle') # Set to idle after successful registration

                logger.info(f"Agent registered successfully with ID: {agent_id}")
                self._command_callback = self._command_callback

                # Start command stream only if registration is successful
                self.start_command_stream(agent_id, self._command_callback)

                return True
            else:
                logger.error(f"Agent registration failed: {response.message}")
                if self._state_update: self._state_update('registration_status', 'failed')
                return False
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error during registration: {e.details()} (Code: {e.code()})")
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                 self._update_grpc_state("unavailable")
            else:
                 self._update_grpc_state("failed") # Other gRPC error
            if self._state_update: self._state_update('registration_status', 'failed')
            return False
        except Exception as e: # Includes asyncio.TimeoutError from request timeout
            logger.error(f"Unexpected error during registration: {e}")
            self._update_grpc_state("failed")
            if self._state_update: self._state_update('registration_status', 'failed')
            return False

    @log_exceptions
    async def unregister(self, agent_id):
        """Unregister the agent from the server."""
        if self._killed:
            logger.warning("Agent is killed/shutdown. Unregistration will not proceed.")
            return False
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

    @log_exceptions
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

    @log_exceptions
    async def send_command_result(self, agent_id, command_id: str, result):
        """Send the result of an executed command back to the server. Accepts dict or CommandResult."""
        if not self._is_registered or not self.stub or not agent_id:
            logger.warning("Cannot send command result: Agent not registered.")
            return False

        # Accept either dict or CommandResult for flexibility
        if isinstance(result, dict):
            request = CommandResult(
                command_id=command_id,
                agent_id=agent_id,
                success=result.get("success", False),
                output=result.get("output", ""),
                error_message=result.get("error_message", ""),
                exit_code=result.get("exit_code", 0),
            )
        elif isinstance(result, CommandResult):
            request = result
        else:
            logger.error(f"send_command_result: result must be dict or CommandResult, got {type(result)}")
            return False
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

    @log_exceptions
    async def send_agent_status_update(self, agent_id, agent_name, last_seen, metrics: dict):
        """Send a full agent status update to the server using the new SendAgentStatus RPC."""
        if not self._ensure_connection():
             # State updated in _ensure_connection
             return False
        # Don't proceed if the channel isn't even connected/ready
        if self._grpc_connection_state not in ["connected", "idle"]: # Allow idle as it might connect on call
             logger.warning(f"Cannot send status update, gRPC state is '{self._grpc_connection_state}'")
             # Attempt to check readiness to trigger potential state change/reconnect
             await self.check_grpc_readiness(timeout=1.0)
             # Re-check state after attempt
             if self._grpc_connection_state not in ["connected"]:
                 return False

        try:
            # Ensure last_seen is included in metrics if not already present
            if 'last_seen' not in metrics:
                metrics['last_seen'] = datetime.now().isoformat() # Use current time if missing

            # --- PATCH: Ensure metrics is a dict of str:str ---
            metrics_str = {str(k): str(v) for k, v in metrics.items()}

            # Defensive: ensure we never pass a dict to a protobuf method
            if not isinstance(metrics_str, dict):
                logger.error("Metrics is not a dict, cannot send agent status update.")
                return False

            agent_info = AgentInfo(
                agent_id=agent_id,
                agent_name=agent_name,
                last_seen=metrics_str['last_seen'], # Use the one from metrics
                metrics=metrics_str
            )
            request = AgentStatusUpdateRequest(agent=agent_info)

            # Create stub for the status service specifically
            status_stub = AgentStatusServiceStub(self.channel)
            logger.debug(f"Sending agent status update via SendAgentStatus: {request}")
            response = await status_stub.SendAgentStatus(request, timeout=15.0) # Add timeout

            # If call succeeded, ensure state is marked connected
            self._update_grpc_state("connected")
            logger.debug(f"Sent agent status update via SendAgentStatus: {response.message}") # Use debug level
            return response.success
        except grpc.aio.AioRpcError as e:
            logger.warning(f"Failed to send agent status update: {e.details()} (Code: {e.code()})")
            if e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.CANCELLED]:
                 self._update_grpc_state("unavailable") # Mark as unavailable on these errors
            else:
                 self._update_grpc_state("failed") # Other errors
            return False
        except Exception as e: # Includes asyncio.TimeoutError
            logger.warning(f"Unexpected error sending agent status update: {e}")
            self._update_grpc_state("failed")
            return False

    @log_exceptions
    async def _command_stream_loop(self, agent_id):
        """Background task to listen for commands from the server."""
        if self._killed:
            logger.error("Command stream cannot start: Agent is killed/shutdown.")
            return
        if not self._is_registered: # Check registration flag first
            logger.error("Command stream cannot start: Agent not registered.")
            return

        logger.info("Starting command stream listener...")

        while self._is_registered and not self._killed: # Loop while agent should be registered and not killed
            if not self._ensure_connection():
                logger.warning("Command stream: gRPC connection failed to initialize. Retrying in 15s...")
                await asyncio.sleep(15)
                continue

            # Wait for connection to be ready before starting stream
            if not await self.check_grpc_readiness(timeout=10.0):
                 logger.warning("Command stream: gRPC connection not ready. Retrying in 15s...")
                 # State is updated by check_grpc_readiness
                 await asyncio.sleep(15)
                 continue

            # If we reach here, connection is ready
            self._update_grpc_state("connected")
            logger.info("Command stream connection ready, attempting to connect stream...")
            request = ReceiveCommandsRequest(agent_id=agent_id)
            stream = None # Initialize stream variable

            try:
                stream = self.stub.ReceiveCommands(request) # Use the main registration stub
                logger.info("Command stream connected.")
                async for command in stream:
                    # --- Process command (existing logic) ---
                    logger.info(f"Received command {command}")
                    if self._command_callback:
                        try:
                            command_dict = {
                                "command_id": command.command_id,
                                "type": command.type,
                                "content": command.content,
                                "parameters": dict(command.parameters),
                                "is_cancellation": command.is_cancellation,
                            }
                            logger.info(f"Received command: {command_dict}")
                            if asyncio.iscoroutinefunction(self._command_callback):
                                result = await self._command_callback(command_dict)
                            else:
                                result = self._command_callback(command_dict)

                            if result and isinstance(result, dict):
                                 await self.send_command_result(agent_id, command.command_id, result)

                        except Exception as e:
                            logger.error(f"Error executing command callback for {command.command_id}: {e}", exc_info=True)
                            await self.send_command_result(agent_id, command.command_id, {
                                "success": False, "output": "", "error_message": f"Agent failed to execute command: {e}", "exit_code": 1
                            })
                    else:
                        logger.warning("Received command but no callback is registered.")
                        await self.send_command_result(agent_id, command.command_id, {
                            "success": False, "output": "", "error_message": "Agent has no command handler registered.", "exit_code": 1
                        })
                    # --- End process command ---

            except grpc.aio.AioRpcError as e:
                if e.code() == grpc.StatusCode.CANCELLED:
                    logger.info("Command stream cancelled (likely server shutdown or agent unregistration).")
                    self._update_grpc_state("cancelled") # Or maybe 'idle'?
                    break # Exit the loop if cancelled by server/unregistration
                elif e.code() in [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED]:
                    logger.warning(f"Command stream disconnected: {e.details()} (Code: {e.code()}). Retrying connection...")
                    self._update_grpc_state("unavailable")
                    # Fall through to retry delay
                else:
                    logger.error(f"Unhandled gRPC error in command stream: {e.details()} (Code: {e.code()}). Retrying connection...")
                    self._update_grpc_state("failed")
                    # Fall through to retry delay
            except Exception as e:
                 logger.error(f"Unexpected error in command stream loop: {e}. Retrying connection...")
                 self._update_grpc_state("failed")
                 # Fall through to retry delay
            finally:
                 # Clean up the stream context if it exists and errored
                 if stream and isinstance(stream, grpc.aio.UnaryStreamCall) and stream.is_active():
                     stream.cancel()
                     logger.info("Cancelled active command stream context due to error or loop exit.")


            # Wait before retrying the connection loop if still registered and not killed
            if self._is_registered and not self._killed:
                 logger.info("Waiting 10 seconds before attempting to reconnect command stream...")
                 await asyncio.sleep(10)

        logger.info("Command stream listener loop finished.")
        self._command_stream_task = None # Clear task reference when loop exits

    def start_command_stream(self, agent_id, callback):
        """Starts the background command stream listener task."""
        if self._killed:
            logger.error("Cannot start command stream: Agent is killed/shutdown.")
            return
        if not self._is_registered:
             logger.error("Cannot start command stream: Agent not registered.")
             return

        if self._command_stream_task and not self._command_stream_task.done():
            logger.warning("Command stream task already running.")
            return

        self._command_callback = callback
        self._command_stream_task = asyncio.create_task(self._command_stream_loop(agent_id))
        logger.info("Command stream task created.")

    @log_exceptions
    async def cleanup(self, agent_id):
        """Clean up gRPC resources and mark agent as killed/shutdown."""
        logger.info("Cleaning up ServerManager gRPC resources...")
        self._killed = True  # Prevent resurrection after cleanup

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