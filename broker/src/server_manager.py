import os
import asyncio
import random
import logging # Import logging directly
from typing import Callable, Optional, Dict

# Third-party imports
import grpc

# Local application imports
from shared_models import setup_logging, MessageType
from decorators import log_exceptions
import broker_config # Import broker configuration

logger = setup_logging(__name__)

# Import generated gRPC code with error handling
GRPC_IMPORTS_SUCCESSFUL = False
try:
    from generated.agent_status_service_pb2 import AgentStatusRequest
    from generated.agent_status_service_pb2_grpc import AgentStatusServiceStub
    from generated.broker_registration_service_pb2 import BrokerRegistrationRequest, BrokerRegistrationResponse
    from generated.broker_registration_service_pb2_grpc import BrokerRegistrationServiceStub
    GRPC_IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.error(f"Failed to import gRPC generated code. Please run generate_grpc.py. Error: {e}")


class ServerManager:
    """
    Manages gRPC communication for the Broker, including registration and agent status updates.
    """
    def __init__(self, broker_id: str, state_update: Optional[Callable] = None, command_callback: Optional[Callable] = None):
        """Initializes the ServerManager.

        Args:
            broker_id: The unique ID for this broker instance.
            state_update: Optional callback function to report state changes (e.g., registration status).
            command_callback: Optional callback function to process received agent status updates.
        """
        self.broker_id = broker_id
        self.state_update = state_update
        self.command_callback = command_callback
        # Use the already configured logger
        self.grpc_host = broker_config.GRPC_HOST # Use config value
        self.grpc_port = broker_config.GRPC_PORT # Use config value
        self._grpc_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event() # Event to signal stopping

    @log_exceptions
    async def register(self) -> bool:
        """Registers the broker with the gRPC server with retries and backoff."""
        if not GRPC_IMPORTS_SUCCESSFUL:
            logger.error("gRPC imports failed. Cannot register broker.")
            if self.state_update:
                self.state_update('registration_status', 'failed')
            return False

        max_retries = 5
        retry_delay = 5.0 # Use float for delays
        for attempt in range(max_retries):
            try:
                async with grpc.aio.insecure_channel(f"{self.grpc_host}:{self.grpc_port}") as channel:
                    stub = BrokerRegistrationServiceStub(channel)
                    request = BrokerRegistrationRequest(
                        broker_id=self.broker_id,
                        broker_name=f"BrokerService_{self.broker_id[:4]}" # More descriptive name
                    )
                    logger.info(f"Attempting to register broker {self.broker_id} (Attempt {attempt + 1}/{max_retries})")
                    response: BrokerRegistrationResponse = await stub.RegisterBroker(request, timeout=10) # Add timeout

                    if response.success:
                        logger.info(f"Broker {self.broker_id} registered successfully.")
                        # Start subscription only after successful registration
                        self.start_agent_status_subscription()
                        if self.state_update:
                            self.state_update('registration_status', 'registered')
                        return True
                    else:
                        logger.error(f"Broker registration failed: {response.message}")
                        # No retry on explicit failure response from server
                        if self.state_update:
                            self.state_update('registration_status', 'failed')
                        return False

            except grpc.aio.AioRpcError as e:
                status_code = e.code()
                details = e.details()
                logger.warning(f"gRPC error during registration (Attempt {attempt + 1}/{max_retries}): {status_code} - {details}")
                if status_code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED) and attempt < max_retries - 1:
                    logger.info(f"Retrying registration in {retry_delay:.1f} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60) # Exponential backoff capped at 60s
                else:
                    logger.error(f"Failed to register broker after {max_retries} attempts due to gRPC error: {status_code}")
                    if self.state_update:
                        self.state_update('registration_status', 'failed')
                    return False
            except Exception as e:
                logger.error(f"Unexpected error during broker registration: {e}", exc_info=True)
                if self.state_update:
                    self.state_update('registration_status', 'failed')
                # Stop retrying on unexpected errors
                return False
        # Should not be reached if loop completes, but added for safety
        return False

    @log_exceptions
    async def request_agent_status(self) -> Optional[Dict]:
        """Requests a one-time snapshot of agent statuses from the server."""
        if not GRPC_IMPORTS_SUCCESSFUL:
            logger.error("gRPC imports failed. Cannot request agent status.")
            return None
        if not self.command_callback:
            logger.warning("No command_callback set, cannot process agent status response.")
            return None

        try:
            async with grpc.aio.insecure_channel(f"{self.grpc_host}:{self.grpc_port}") as channel:
                stub = AgentStatusServiceStub(channel)
                request = AgentStatusRequest(broker_id=self.broker_id)
                logger.info(f"Requesting agent status snapshot for broker {self.broker_id}")
                response = await stub.GetAgentStatus(request, timeout=10) # Add timeout

                status_update = self._process_agent_status_response(response)

                logger.info(f"Received agent status snapshot. Processing {len(status_update['agents'])} agents.")
                await self.command_callback(status_update)
                return status_update
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC error requesting agent status: {e.code()} - {e.details()}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error requesting agent status: {e}", exc_info=True)
            return None

    def _process_agent_status_response(self, response) -> Dict:
        """Processes the gRPC agent status response into a dictionary for the callback."""
        agents_data = []
        for agent in response.agents:
            agents_data.append({
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "last_seen": agent.last_seen,
                "metrics": dict(agent.metrics) # Convert map to dict
            })

        return {
            "message_type": MessageType.AGENT_STATUS_UPDATE,
            "agents": agents_data,
            "is_full_update": response.is_full_update
        }

    def start_agent_status_subscription(self) -> Optional[asyncio.Task]:
        """Starts the background task for subscribing to agent status updates."""
        if not GRPC_IMPORTS_SUCCESSFUL:
             logger.error("gRPC imports failed. Cannot start agent status subscription.")
             return None
        if self._grpc_task is not None and not self._grpc_task.done():
            logger.warning("Agent status subscription task is already running.")
            return self._grpc_task

        self._stop_event.clear() # Ensure stop event is clear before starting
        self._grpc_task = asyncio.create_task(self._agent_status_stream_loop())
        logger.info("Started agent status subscription background task.")
        return self._grpc_task

    @log_exceptions
    async def _agent_status_stream_loop(self, initial_reconnect_delay=5.0):
        """Background loop to maintain the gRPC stream for agent status updates."""
        if not GRPC_IMPORTS_SUCCESSFUL or not self.command_callback:
            logger.error("Cannot start agent status stream: gRPC imports failed or no command_callback set.")
            return

        reconnect_delay = initial_reconnect_delay
        max_backoff = 60.0

        while not self._stop_event.is_set():
            channel = None # Define channel outside try block for finally clause
            try:
                channel = grpc.aio.insecure_channel(f"{self.grpc_host}:{self.grpc_port}")
                stub = AgentStatusServiceStub(channel)
                request = AgentStatusRequest(broker_id=self.broker_id)
                logger.info(f"Subscribing to agent status updates for broker {self.broker_id}...")

                async for response in stub.SubscribeToAgentStatus(request):
                    if self._stop_event.is_set(): # Check stop event during iteration
                        logger.info("Stop event set, breaking from agent status stream.")
                        break

                    status_update = self._process_agent_status_response(response)
                    logger.info(f"Processing streamed agent status update ({len(status_update['agents'])} agents, full={response.is_full_update}).")
                    await self.command_callback(status_update)

                # If loop finishes without break, server closed stream gracefully
                if not self._stop_event.is_set():
                    logger.info("gRPC stream closed by server. Attempting to reconnect...")
                    reconnect_delay = initial_reconnect_delay # Reset delay on graceful close

            except grpc.aio.AioRpcError as e:
                status_code = e.code()
                details = e.details()
                logger.error(f"gRPC error in agent status stream: {status_code} - {details}")
                if status_code == grpc.StatusCode.CANCELLED and self._stop_event.is_set():
                    logger.info("Stream cancelled as part of shutdown.")
                    break # Exit loop if cancelled due to stop event
                # Apply backoff for other retryable errors
                if status_code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.INTERNAL, grpc.StatusCode.DEADLINE_EXCEEDED):
                     logger.info(f"Stream error, will attempt reconnect after {reconnect_delay:.1f} seconds.")
                     reconnect_delay = min(reconnect_delay * 2, max_backoff)
                else:
                     # Non-retryable gRPC error, log and potentially stop trying
                     logger.error(f"Non-retryable gRPC error {status_code}. Stopping stream attempts.")
                     break # Exit loop for non-retryable errors

            except asyncio.CancelledError:
                logger.info("Agent status stream task cancelled externally.")
                break # Exit loop if task is cancelled
            except Exception as e:
                logger.error(f"Unexpected error in agent status stream loop: {e}", exc_info=True)
                # Apply backoff for unexpected errors before retrying
                logger.info(f"Unexpected error, will attempt reconnect after {reconnect_delay:.1f} seconds.")
                reconnect_delay = min(reconnect_delay * 2, max_backoff)
            finally:
                if channel:
                    await channel.close()
                    logger.debug("gRPC channel closed in stream loop finally block.")

            # Wait before retrying, unless stopping
            if not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=reconnect_delay)
                    # If wait completes, stop event was set during sleep
                    logger.info("Stop event set during reconnect delay. Exiting stream loop.")
                    break
                except asyncio.TimeoutError:
                    # Timeout occurred, continue to next retry attempt
                    pass

        logger.info("Agent status subscription loop finished.")

    @log_exceptions
    async def stop(self):
        """Stops the gRPC agent status subscription task gracefully."""
        logger.info("Stopping ServerManager and gRPC subscription...")
        self._stop_event.set() # Signal the loop to stop

        if self._grpc_task and not self._grpc_task.done():
            logger.info("Waiting for gRPC agent status subscription task to finish...")
            try:
                # Wait for the task to finish, with a timeout
                await asyncio.wait_for(self._grpc_task, timeout=10.0)
                logger.info("gRPC agent status subscription task finished gracefully.")
            except asyncio.TimeoutError:
                logger.warning("gRPC task did not finish within timeout during stop. Attempting cancellation.")
                self._grpc_task.cancel()
                try:
                    await self._grpc_task # Await cancellation
                except asyncio.CancelledError:
                    logger.info("gRPC task successfully cancelled after timeout.")
                except Exception as e:
                     logger.error(f"Error during gRPC task cancellation: {e}", exc_info=True)
            except asyncio.CancelledError:
                 # This might happen if stop() itself is cancelled
                 logger.warning("ServerManager stop() was cancelled while waiting for gRPC task.")
            except Exception as e:
                logger.error(f"Error waiting for gRPC task during stop: {e}", exc_info=True)
        elif self._grpc_task and self._grpc_task.done():
             logger.info("gRPC agent status subscription task was already done.")
        else:
             logger.info("No active gRPC agent status subscription task to stop.")

        self._grpc_task = None # Clear the task reference
        logger.info("ServerManager stop sequence complete.")
