"""
gRPC server implementation for agent status service
"""
import asyncio
import grpc
from concurrent import futures
import sys
import os

# Add the parent directory to sys.path so we can import the generated modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import generated gRPC code
from generated.agent_status_service_pb2 import AgentStatusResponse, AgentInfo
from generated.agent_status_service_pb2_grpc import AgentStatusServiceServicer, add_AgentStatusServiceServicer_to_server
import broker_registration_service

# Import shared modules
from shared_models import setup_logging
import state

logger = setup_logging(__name__)

# Global variables
# Use a dict to map subscriber_id to subscriber context
subscriber_contexts = {}
subscription_lock = asyncio.Lock()

class AgentStatusServicer(AgentStatusServiceServicer):
    """Implementation of the AgentStatusService"""
    
    async def SubscribeToAgentStatus(self, request, context):
        """
        Stream agent status updates to the broker.
        This is a server-streaming RPC that sends updates whenever agent status changes.
        """
        broker_id = request.broker_id
        logger.info(f"Broker {broker_id} subscribed to agent status updates")
        
        # Add this subscriber to active subscribers with its context
        subscriber_id = id(context)
        
        # Create a queue for status updates
        queue = asyncio.Queue()
        
        async with subscription_lock:
            subscriber_contexts[subscriber_id] = {
                "broker_id": broker_id,
                "queue": queue,
                "active": True
            }
        
        # Set up cancellation detection
        context.add_done_callback(lambda _: self._handle_context_done(subscriber_id))
        
        try:
            # Send initial full status update
            yield await self._create_status_response(is_full_update=True)
            
            # Process updates from the queue while context is active
            while subscriber_contexts.get(subscriber_id, {}).get("active", False):
                try:
                    # Wait for an update with a timeout
                    response = await asyncio.wait_for(queue.get(), timeout=5.0)
                    # Check if the context is still valid before yielding
                    if not context.cancelled():
                        yield response
                    else:
                        logger.debug(f"Context cancelled for broker {broker_id}, stopping stream")
                        break
                    queue.task_done()
                except asyncio.TimeoutError:
                    # No updates received within timeout, check if context is still valid
                    if context.cancelled():
                        logger.debug(f"Context cancelled for broker {broker_id} during timeout")
                        break
                    continue
                
        except Exception as e:
            logger.error(f"Error in agent status stream for broker {broker_id}: {e}")
        finally:
            # Remove this subscriber when done
            await self._cleanup_subscriber(subscriber_id)
            logger.info(f"Broker {broker_id} unsubscribed from agent status updates")
    
    async def GetAgentStatus(self, request, context):
        """
        Get a one-time full agent status update.
        This is a unary RPC that returns the current agent status.
        """
        broker_id = request.broker_id
        logger.info(f"Broker {broker_id} requested a one-time agent status update")
        
        # Simply return the current status
        return await self._create_status_response(is_full_update=True)
    
    async def _create_status_response(self, is_full_update=False):
        """Create an AgentStatusResponse from the current agent status state"""
        response = AgentStatusResponse()
        response.is_full_update = is_full_update
        
        # Convert agent_statuses to proto format
        for agent_id, status in state.agent_statuses.items():
            agent_info = AgentInfo()
            agent_info.agent_id = agent_id
            agent_info.agent_name = status.agent_name
            agent_info.is_online = status.is_online
            agent_info.last_seen = status.last_seen
            agent_info.status = status.status  # Include status field
            response.agents.append(agent_info)
        
        return response

    def _handle_context_done(self, subscriber_id):
        """Handle context completion by marking the subscriber as inactive"""
        subscriber_info = subscriber_contexts.get(subscriber_id)
        if subscriber_info:
            subscriber_info["active"] = False
            broker_id = subscriber_info.get("broker_id", "unknown")
            logger.debug(f"Marked subscriber for broker {broker_id} as inactive due to context completion")

    async def _cleanup_subscriber(self, subscriber_id):
        """Remove a subscriber from the active subscribers list"""
        async with subscription_lock:
            if subscriber_id in subscriber_contexts:
                broker_id = subscriber_contexts[subscriber_id].get("broker_id", "unknown")
                logger.info(f"Cleaning up subscriber for broker {broker_id}")
                del subscriber_contexts[subscriber_id]

async def broadcast_agent_status_updates(is_full_update=False):
    """
    Broadcast agent status updates to all active subscribers.
    This function should be called whenever agent status changes.
    """
    subscriber_count = len(subscriber_contexts)
    if subscriber_count == 0:
        return
    
    logger.info(f"Broadcasting agent status updates to {subscriber_count} subscribers (is_full_update={is_full_update})")
    
    # Create a status response just once for all subscribers
    response = await AgentStatusServicer()._create_status_response(is_full_update=is_full_update)
    
    async with subscription_lock:
        # Track subscribers to remove if their context is no longer valid
        to_remove = []
        
        for subscriber_id, subscriber_info in subscriber_contexts.items():
            try:
                # Check if subscriber is marked as active
                if not subscriber_info.get("active", False):
                    to_remove.append(subscriber_id)
                    continue
                
                # Add the response to the subscriber's queue
                broker_id = subscriber_info.get("broker_id", "unknown")
                queue = subscriber_info.get("queue")
                if queue:
                    try:
                        # Use put_nowait to avoid blocking
                        if queue.qsize() < 10:  # Limit queue size to prevent memory issues
                            queue.put_nowait(response)
                            logger.debug(f"Added status update to broker {broker_id}'s queue")
                        else:
                            logger.warning(f"Queue full for broker {broker_id}, skipping update")
                    except asyncio.QueueFull:
                        logger.warning(f"Queue full for broker {broker_id}, skipping update")
                else:
                    logger.warning(f"No queue found for broker {broker_id}, marking for removal")
                    to_remove.append(subscriber_id)
                
            except Exception as e:
                logger.error(f"Error broadcasting to subscriber {subscriber_id}: {e}")
                to_remove.append(subscriber_id)
        
        # Remove any invalid subscribers
        for subscriber_id in to_remove:
            if subscriber_id in subscriber_contexts:
                broker_id = subscriber_contexts.get(subscriber_id, {}).get("broker_id", "unknown")
                logger.info(f"Removing invalid subscriber for broker {broker_id}")
                subscriber_contexts.pop(subscriber_id, None)

def start_grpc_server(port=50051):
    """Start the gRPC server in a separate thread"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    add_AgentStatusServiceServicer_to_server(AgentStatusServicer(), server)
    broker_registration_service.add_to_server(server)
    server.add_insecure_port(f'[::]:{port}')
    
    logger.info(f"Starting gRPC server on port {port}")
    return server 

def add_services_to_server(server):
    """Add all gRPC services to the server"""
    add_AgentStatusServiceServicer_to_server(AgentStatusServicer(), server)
    broker_registration_service.add_to_server(server)
    logger.info("All gRPC services added to server")