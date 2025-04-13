"""
gRPC client implementation for the broker to receive agent status updates from the server
"""
import grpc
import asyncio
import logging
import time
import inspect
from typing import Callable, Optional
import random
import sys
import os

# Add the parent directory to sys.path so we can import the generated modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import shared modules
from shared_models import setup_logging, MessageType

logger = setup_logging(__name__)
# Import generated gRPC code
# Note: These imports will only work after running generate_grpc.py
try:
    from generated.agent_status_service_pb2 import AgentStatusRequest
    from generated.agent_status_service_pb2_grpc import AgentStatusServiceStub
    GRPC_IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.warning(f"gRPC generated code not found. Please run generate_grpc.py first. Error: {e}")
    GRPC_IMPORTS_SUCCESSFUL = False
    
    # Placeholder implementations when imports fail
    class AgentStatusServiceStub:
        """Placeholder for the gRPC client stub."""
        def __init__(self, channel):
            self.channel = channel
        
        async def SubscribeToAgentStatus(self, request):
            """Placeholder for the streaming RPC method that returns an empty async generator"""
            logger.warning("Using placeholder SubscribeToAgentStatus implementation")
            # Return an empty async generator that immediately stops
            if False:  # This ensures the generator yields nothing
                yield None
            return
        
        async def GetAgentStatus(self, request):
            """Placeholder for the unary RPC method that returns None"""
            logger.warning("Using placeholder GetAgentStatus implementation")
            # Create a minimal response-like object
            class DummyResponse:
                def __init__(self):
                    self.agents = []
                    self.is_full_update = True
            return DummyResponse()

    class AgentStatusRequest:
        """Placeholder for the gRPC request message."""
        def __init__(self, broker_id):
            self.broker_id = broker_id


# Global variable to store the agent status callback
_agent_status_callback = None

def set_agent_status_callback(callback: Callable):
    """
    Set the callback function that will be called when agent status updates are received.
    
    Args:
        callback: A function that will be called with the agent status data.
                 The function should take a dictionary with the agent status data.
    """
    global _agent_status_callback
    _agent_status_callback = callback
    logger.info("Agent status callback set")

async def connect_to_grpc_server(host: str, port: int, broker_id: str, reconnect_interval=5) -> None:
    """
    Connect to the gRPC server and subscribe to agent status updates.
    
    Args:
        host: The gRPC server hostname or IP.
        port: The gRPC server port.
        broker_id: The broker ID to use when connecting.
        reconnect_interval: Time in seconds between reconnection attempts.
    """
    global _agent_status_callback
    
    if not GRPC_IMPORTS_SUCCESSFUL:
        logger.error("gRPC imports failed. Cannot connect to gRPC server.")
        return
    
    attempt = 0
    max_backoff = 60  # Maximum backoff in seconds
    
    while True:
        try:
            # Implement exponential backoff with jitter
            if attempt > 0:
                backoff = min(reconnect_interval * (2 ** (attempt - 1)), max_backoff)
                # Add some randomness to prevent all clients reconnecting at the same time
                jitter = backoff * 0.2 * (random.random() * 2 - 1)
                sleep_time = max(1, backoff + jitter)
                logger.info(f"Attempt {attempt}: Waiting {sleep_time:.1f}s before reconnecting to gRPC server")
                await asyncio.sleep(sleep_time)
            
            attempt += 1
            
            # Create a channel to the server
            logger.info(f"Connecting to gRPC server at {host}:{port}")
            channel = grpc.aio.insecure_channel(f"{host}:{port}")
            
            # Create the stub
            stub = AgentStatusServiceStub(channel)
            
            # Create the request
            request = AgentStatusRequest(broker_id=broker_id)
            
            # Subscribe to agent status updates
            logger.info(f"Subscribing to agent status updates as broker {broker_id}")
            
            try:
                # Reset attempt counter on successful connection
                attempt = 0
                
                # Call the streaming RPC method
                async for response in stub.SubscribeToAgentStatus(request):
                    try:
                        # Process the response
                        if _agent_status_callback:
                            # Convert the response to a dictionary format that matches the current
                            # WebSocket format for backward compatibility
                            agents_data = []
                            for agent in response.agents:
                                agents_data.append({
                                    "agent_id": agent.agent_id,
                                    "agent_name": agent.agent_name,
                                    "is_online": agent.is_online,
                                    "last_seen": agent.last_seen
                                })
                            
                            # Create status update message
                            status_update = {
                                "message_type": MessageType.AGENT_STATUS_UPDATE,
                                "agents": agents_data,
                                "is_full_update": response.is_full_update
                            }
                            
                            # Call the callback with the status update
                            try:
                                if _agent_status_callback:
                                    if inspect.iscoroutinefunction(_agent_status_callback):
                                        await _agent_status_callback(status_update)
                                    else:
                                        # Call non-async function directly
                                        _agent_status_callback(status_update)
                            except Exception as callback_err:
                                logger.error(f"Error in agent status callback: {callback_err}")
                        else:
                            logger.warning("Received agent status update but no callback is registered")
                    except Exception as process_err:
                        logger.error(f"Error processing agent status update: {process_err}")
                        # Continue trying to process other updates even if one fails
                        continue
                
                # If we get here, the stream has ended normally (server closed it)
                logger.info("gRPC stream closed normally by server. Reconnecting...")
                        
            except grpc.RpcError as e:
                # RPC-specific errors
                if hasattr(e, 'code'):
                    code = e.code()
                    details = e.details() if hasattr(e, 'details') else "Unknown details"
                    
                    # Handle specific gRPC status codes
                    if code == grpc.StatusCode.UNAVAILABLE:
                        logger.error(f"gRPC server unavailable: {details}")
                    elif code == grpc.StatusCode.CANCELLED:
                        logger.warning(f"gRPC stream cancelled: {details}")
                    elif code == grpc.StatusCode.DEADLINE_EXCEEDED:
                        logger.error(f"gRPC deadline exceeded: {details}")
                    elif code == grpc.StatusCode.UNIMPLEMENTED:
                        logger.error(f"gRPC method not implemented: {details}")
                    elif code == grpc.StatusCode.INTERNAL:
                        logger.error(f"gRPC internal server error: {details}")
                    else:
                        logger.error(f"gRPC error with code {code}: {details}")
                else:
                    logger.error(f"gRPC error during agent status stream: {e}")
                    
                # Close the channel and retry
                try:
                    await channel.close()
                except Exception as close_err:
                    logger.warning(f"Error closing gRPC channel: {close_err}")
                
                continue
                
        except ConnectionRefusedError:
            logger.error(f"Connection refused: gRPC server at {host}:{port} is not accepting connections")
        except asyncio.CancelledError:
            logger.info("gRPC client task cancelled")
            break  # Exit the loop if the task is cancelled
        except Exception as e:
            logger.error(f"Error connecting to gRPC server: {e}")

    logger.info("gRPC client stopped")

async def request_agent_status(host: str, port: int, broker_id: str) -> Optional[dict]:
    """
    Request a one-time agent status update from the server.
    
    Args:
        host: The gRPC server hostname or IP.
        port: The gRPC server port.
        broker_id: The broker ID to use when connecting.
        
    Returns:
        A dictionary with the agent status data, or None if the request failed.
    """
    global _agent_status_callback
    
    if not GRPC_IMPORTS_SUCCESSFUL:
        logger.error("gRPC imports failed. Cannot request agent status.")
        return None
    
    try:
        # Create a channel to the server
        logger.info(f"Connecting to gRPC server at {host}:{port} for one-time agent status request")
        channel = grpc.aio.insecure_channel(f"{host}:{port}")
        
        # Create the stub
        stub = AgentStatusServiceStub(channel)
        
        # Create the request
        request = AgentStatusRequest(broker_id=broker_id)
        
        # Call the unary RPC method
        logger.info(f"Requesting agent status as broker {broker_id}")
        response = await stub.GetAgentStatus(request)
        
        # Convert the response to a dictionary
        agents_data = []
        for agent in response.agents:
            agents_data.append({
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "is_online": agent.is_online,
                "last_seen": agent.last_seen
            })
        
        # Create status update message
        status_update = {
            "message_type": MessageType.AGENT_STATUS_UPDATE,
            "agents": agents_data,
            "is_full_update": response.is_full_update
        }
        
        # Close the channel
        await channel.close()
        
        # Process the status update with the callback if registered
        if _agent_status_callback:
            try:
                if inspect.iscoroutinefunction(_agent_status_callback):
                    await _agent_status_callback(status_update)
                else:
                    _agent_status_callback(status_update)
                logger.debug("Processed agent status update with callback")
            except Exception as e:
                logger.error(f"Error in agent status callback during one-time request: {e}")
        
        return status_update
    except Exception as e:
        logger.error(f"Error requesting agent status via gRPC: {e}")
        return None