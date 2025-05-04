"""
gRPC server implementation for agent status service
"""
import asyncio
import logging
import os
import sys
from datetime import datetime

import grpc

# Import generated gRPC code
from generated.agent_status_service_pb2 import AgentInfo, AgentStatusResponse, AgentStatusUpdateResponse
from generated.agent_status_service_pb2_grpc import (AgentStatusServiceServicer,
                                                   add_AgentStatusServiceServicer_to_server)

# Import shared modules
from shared_models import setup_logging
import state
import agent_manager # Import moved here for clarity

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Global variables for status subscriptions
subscriber_contexts = {}  # Maps subscriber_id to subscriber context
subscription_lock = asyncio.Lock()


class AgentStatusServicer(AgentStatusServiceServicer):
    """Implementation of the AgentStatusService."""

    async def SubscribeToAgentStatus(self, request, context):
        """
        Stream agent status updates to a subscriber (e.g., a broker).

        This is a server-streaming RPC that sends updates whenever agent status changes.
        It sends an initial full update and then subsequent partial or full updates.
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

        This is a unary RPC that returns the current status of all known agents.
        """
        broker_id = request.broker_id
        logger.info(f"Broker {broker_id} requested a one-time agent status update")
        
        # Simply return the current status
        return await self._create_status_response(is_full_update=True)
    
    async def SendAgentStatus(self, request, context):
        """
        Receive an agent-initiated status update.

        This unary RPC allows an agent to push its current status and metrics
        to the server.
        """
        agent = request.agent
        agent_id = agent.agent_id
        agent_name = agent.agent_name
        logger.info(f"""
        Received status update from agent {agent_id} ('{agent_name}')
        {request.agent}
        """)

        try:
            # Ensure 'last_seen' is present in the agent info
            if not agent.last_seen:
                logger.warning(f"Agent {agent_id} sent status update without 'last_seen' timestamp.")
                # Use current time as fallback
                agent.last_seen = datetime.now().isoformat()


            await state.update_agent_status(agent_id, agent)

            # Broadcast the update to connected frontends/subscribers
            # Use force_full_update=True to ensure consistency after direct update
            asyncio.create_task(agent_manager.broadcast_agent_status(force_full_update=True, is_full_update=True))
        except Exception as e:
            logger.error(f"Failed to process agent status update from {agent_id}: {e}", exc_info=True)
            return AgentStatusUpdateResponse(success=False, message=f"Error processing update: {e}")

        return AgentStatusUpdateResponse(success=True, message="Status update received")

    async def _create_status_response(self, is_full_update=False):
        """Create an AgentStatusResponse message from the current agent state."""
        response = AgentStatusResponse()
        response.is_full_update = is_full_update
        
        # Convert all agent states to AgentInfo format
        current_agent_states = state.agent_states.copy() # Copy for thread safety during iteration
        for agent_id, agent_state in current_agent_states.items():
            try:
                agent_info = AgentInfo()
                agent_info.agent_id = agent_id
                agent_info.agent_name = agent_state.agent_name
                agent_info.last_seen = agent_state.last_seen
                
                # Add all metrics
                for key, value in agent_state.get_metrics_dict().items():
                    agent_info.metrics[key] = str(value) # Ensure value is string for proto
                
                response.agents.append(agent_info)
            except Exception as e:
                 logger.error(f"Error converting state for agent {agent_id} to AgentInfo: {e}", exc_info=True)
        
        return response

    def _handle_context_done(self, subscriber_id):
        """Callback function invoked when a subscriber's gRPC context is done (cancelled/closed)."""
        subscriber_info = subscriber_contexts.get(subscriber_id)
        if subscriber_info:
            subscriber_info["active"] = False
            broker_id = subscriber_info.get("broker_id", "unknown")
            logger.debug(f"Marked subscriber for broker {broker_id} as inactive due to context completion")

    async def _cleanup_subscriber(self, subscriber_id):
        """Remove a subscriber's context and queue from the active subscribers list."""
        async with subscription_lock:
            if subscriber_id in subscriber_contexts:
                broker_id = subscriber_contexts[subscriber_id].get("broker_id", "unknown")
                logger.info(f"Cleaning up subscriber for broker {broker_id}")
                del subscriber_contexts[subscriber_id]


async def broadcast_agent_status_updates(is_full_update=False):
    """
    Broadcast the current agent status to all active subscribers.

    This function is called when agent status changes need to be pushed
    to subscribed clients (like brokers).
    """
    subscriber_count = len(subscriber_contexts)
    if subscriber_count == 0:
        return
    
    logger.info(f"Broadcasting agent status updates to {subscriber_count} subscribers (is_full_update={is_full_update})")
    
    # Create a status response just once for all subscribers
    try:
        # Need an instance to call the method
        servicer_instance = AgentStatusServicer()
        response = await servicer_instance._create_status_response(is_full_update=is_full_update)
    except Exception as e:
         logger.error(f"Failed to create status response for broadcast: {e}", exc_info=True)
         return
    
    async with subscription_lock:
        # Track subscribers to remove if their context is no longer valid
        to_remove = []
        
        for subscriber_id, subscriber_info in list(subscriber_contexts.items()): # Iterate over a copy
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


def start_agent_status_service(server):
    """Add the AgentStatusServiceServicer to the given gRPC server."""
    logger.info("Adding agent status service to gRPC server")
    servicer = AgentStatusServicer()
    add_AgentStatusServiceServicer_to_server(servicer, server)

