"""
gRPC server implementation for agent status service
"""
import asyncio
import grpc
from concurrent import futures
import sys
import os
import datetime

# Add the parent directory to sys.path so we can import the generated modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import shared modules
from shared_models import setup_logging
import state

logger = setup_logging(__name__)



# Import generated gRPC code
from generated.agent_status_service_pb2 import AgentStatusResponse, AgentInfo
from generated.agent_status_service_pb2_grpc import AgentStatusServiceServicer, add_AgentStatusServiceServicer_to_server
import broker_registration_service

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
    
    async def SendAgentStatus(self, request, context):
        """
        Handle agent-initiated status updates via SendAgentStatus RPC.
        Uses the AgentInfo format with metrics for all agent state.
        """
        agent = request.agent
        agent_id = agent.agent_id
        agent_name = agent.agent_name
        
        # Extract all metrics from the request
        metrics = dict(agent.metrics)
        logger.info(f"Received status update from agent {agent_id} with {len(metrics)} metrics")
        
        try:
            # Update last_seen if not provided
            if 'last_seen' not in metrics and agent.last_seen:
                metrics['last_seen'] = agent.last_seen
                
            # Update agent metrics in state
            await state.update_agent_metrics(agent_id, agent_name, metrics)
            
            # Broadcast to frontends
            import agent_manager
            asyncio.create_task(agent_manager.broadcast_agent_status(force_full_update=True, is_full_update=True))
        except Exception as e:
            logger.error(f"Failed to process agent status update: {e}")
        
        from generated.agent_status_service_pb2 import AgentStatusUpdateResponse
        return AgentStatusUpdateResponse(success=True, message="Status update received")

    async def _create_status_response(self, is_full_update=False):
        """Create an AgentStatusResponse from the current agent state"""
        response = AgentStatusResponse()
        response.is_full_update = is_full_update
        
        # Convert all agent states to AgentInfo format
        for agent_id, agent_state in state.agent_states.items():
            agent_info = AgentInfo()
            agent_info.agent_id = agent_id
            agent_info.agent_name = agent_state.agent_name
            agent_info.last_seen = agent_state.last_seen
            
            # Add all metrics
            for key, value in agent_state.get_metrics_dict().items():
                agent_info.metrics[key] = value
            
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

# --- Keepalive Settings ---
# Ping clients every 60 seconds if no activity
KEEPALIVE_TIME_MS = 60 * 1000
# Wait 20 seconds for the ping ack before assuming connection is dead
KEEPALIVE_TIMEOUT_MS = 20 * 1000
# Allow pings even if there are no active streams
KEEPALIVE_PERMIT_WITHOUT_CALLS = 1
# Maximum number of bad pings allowed before closing connection
MAX_PINGS_WITHOUT_DATA = 3 # More lenient
# Minimum time between pings - prevents overly frequent pings
MIN_PING_INTERVAL_WITHOUT_DATA_MS = 30 * 1000

grpc_options = [
    ('grpc.keepalive_time_ms', KEEPALIVE_TIME_MS),
    ('grpc.keepalive_timeout_ms', KEEPALIVE_TIMEOUT_MS),
    ('grpc.keepalive_permit_without_calls', KEEPALIVE_PERMIT_WITHOUT_CALLS),
    ('grpc.http2.max_pings_without_data', MAX_PINGS_WITHOUT_DATA),
    ('grpc.http2.min_ping_interval_without_data_ms', MIN_PING_INTERVAL_WITHOUT_DATA_MS),
    # ('grpc.http2.max_ping_strikes', 2) # Optional: How many pings can be missed before connection is closed by server
]
# --- End Keepalive Settings ---


# --- Application-level keepalive settings ---
AGENT_KEEPALIVE_INTERVAL_SECONDS = 60  # How often to check (seconds)
AGENT_KEEPALIVE_GRACE_SECONDS = 60     # Allowed time since last_seen before marking as unknown

async def agent_keepalive_checker():
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        for agent_id, agent_state in state.agent_states.items():
            try:
                last_seen_str = agent_state.last_seen
                last_seen = datetime.datetime.fromisoformat(last_seen_str)
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)
                delta = (now - last_seen).total_seconds()
                if delta > AGENT_KEEPALIVE_GRACE_SECONDS:
                    if agent_state.metrics.get("internal_state") != "unknown_status":
                        logger.warning(f"Agent {agent_id} missed keepalive window ({delta:.1f}s). Marking as unknown_status.")
                        await state.update_agent_metrics(agent_id, agent_state.agent_name, {"internal_state": "unknown_status"})
            except Exception as e:
                logger.error(f"Error in keepalive check for agent {agent_id}: {e}")
        await asyncio.sleep(AGENT_KEEPALIVE_INTERVAL_SECONDS)

def start_grpc_server(port=50051):
    """Start the gRPC server in a separate thread"""
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=grpc_options  # <-- Pass the options here
    )
    add_AgentStatusServiceServicer_to_server(AgentStatusServicer(), server)
    broker_registration_service.add_to_server(server)
    # Bind to both IPv4 and IPv6
    server.add_insecure_port(f'0.0.0.0:{port}')  # IPv4
    server.add_insecure_port(f'[::]:{port}')     # IPv6
    
    logger.info(f"Starting gRPC server on port {port}")

    # Start the agent keepalive checker as a background task
    loop = asyncio.get_event_loop()
    loop.create_task(agent_keepalive_checker())

    return server 

def add_services_to_server(server):
    """Add all gRPC services to the server"""
    add_AgentStatusServiceServicer_to_server(AgentStatusServicer(), server)
    broker_registration_service.add_to_server(server)
    logger.info("All gRPC services added to server")