import json
from datetime import datetime
import asyncio
from fastapi.websockets import WebSocket

# Import shared models, config, state, and utils
from shared_models import MessageType, setup_logging
import state
import agent_status_service
import logging

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module

async def broadcast_agent_status(force_full_update: bool = False, is_full_update: bool = False, target_websocket: WebSocket = None):
    """Broadcast agent status to all clients or a specific frontend client.
    
    For brokers: Uses gRPC exclusively.
    For frontends: Uses WebSockets for backward compatibility.
    
    Args:
        force_full_update: Force sending a full status update even if no changes detected
        is_full_update: Flag indicating this is a full agent status update (vs. delta)
        target_websocket: Optional specific WebSocket to send the update to instead of broadcasting
    """
    logger.info(f"Broadcasting agent status")
    
    # Get current agent status
    agent_status_list = []
    online_agent_count = 0
    
    # Convert agent_states to a list for transmission
    for agent_id, agent_state in state.agent_states.items():
        # Just include agent_id and metrics for the agent
        agent_status = {
            "agent_id": agent_id,
            "metrics": agent_state.get_metrics_dict()  # Include all metrics with agent_name and last_seen
        }
        agent_status_list.append(agent_status)
        
        # Count online agents based on internal_state
        internal_state = agent_state.metrics.get("internal_state", "initializing")
        if internal_state != "offline":
            online_agent_count += 1
    
    # Get online agents based on internal_state
    online_agents = [
        s['agent_id'] for s in agent_status_list 
        if state.agent_states[s['agent_id']].metrics.get("internal_state", "initializing") != "offline"
    ]
    if len(online_agents) > 0:
        logger.info(f"Online agents: {online_agents}")
    else:
        logger.info("No agents online")
    
    status_update = {
        "message_type": MessageType.AGENT_STATUS_UPDATE,
        "agents": agent_status_list,
        "is_full_update": is_full_update or force_full_update
    }

    try:
        status_update_json = json.dumps(status_update)
        # Determine whether to send to specific target or broadcast to all
        if target_websocket is not None:
            # Target a specific frontend
            frontend_id = getattr(target_websocket, 'client_id', 'unknown')
            try:
                # Check if WebSocket is connected - use a different approach that works with FastAPI
                try:
                    logger.info(f"Sending targeted agent status ({online_agent_count} online) to frontend {frontend_id}")
                    await target_websocket.send_text(status_update_json)
                except RuntimeError as conn_error:
                    if "WebSocket is not connected" in str(conn_error):
                        logger.warning(f"Cannot send targeted agent status to frontend {frontend_id}: WebSocket not connected")
                    else:
                        raise
            except Exception as e:
                logger.error(f"Error sending targeted agent status to frontend {frontend_id}: {e}")
        else:
            # Broadcast to all connected frontends
            active_connections = state.frontend_connections
            if not active_connections:
                logger.info("No frontend WebSockets connected, status update not broadcasted")
                return
                
            # Now we know we have connections to process
            logger.info(f"Broadcasting agent status ({online_agent_count} online) to {len(active_connections)} frontends")
            disconnected = []
            
            # Send to all connected frontends
            for ws in active_connections:
                # Guard against invalid objects in the set
                if not ws:
                    continue
                    
                frontend_id = getattr(ws, 'client_id', 'unknown')
                try:
                    # Check if WebSocket is connected - use a different approach that works with FastAPI
                    try:
                        await ws.send_text(status_update_json)
                    except RuntimeError as conn_error:
                        if "WebSocket is not connected" in str(conn_error):
                            logger.warning(f"Frontend {frontend_id} WebSocket not connected, marking for cleanup")
                            disconnected.append(ws)
                        else:
                            raise
                except Exception as e:
                    logger.error(f"Error sending to frontend {frontend_id}: {e}")
                    disconnected.append(ws)
            
            # Clean up any disconnected WebSockets
            for ws in disconnected:
                if ws in state.frontend_connections:
                    state.frontend_connections.remove(ws)
                    frontend_id = getattr(ws, 'client_id', 'unknown')
                    logger.info(f"Removed disconnected frontend: {frontend_id}")
            
            logger.info(f"Successfully broadcasted agent status to {len(active_connections) - len(disconnected)} frontends")

    except Exception as e:
        logger.error(f"Error preparing or sending agent status update to frontends: {e}")
    

async def broadcast_agent_deregister(agent_id: str):
    """Broadcast a DEREGISTER_AGENT message to all frontend clients to remove the agent from the UI."""
    logger.info(f"Broadcasting DEREGISTER_AGENT for agent {agent_id} to all frontends.")
    message = {
        "message_type": MessageType.DEREGISTER_AGENT,
        "agent_id": agent_id,
        "send_timestamp": datetime.now().isoformat(),
    }
    try:
        payload = json.dumps(message)
        active_connections = state.frontend_connections
        if not active_connections:
            logger.info("No frontend WebSockets connected, DEREGISTER_AGENT not broadcasted")
            return
        disconnected = []
        for ws in active_connections:
            if not ws:
                continue
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.error(f"Error sending DEREGISTER_AGENT to frontend: {e}")
                disconnected.append(ws)
        for ws in disconnected:
            if ws in state.frontend_connections:
                state.frontend_connections.remove(ws)
        logger.info(f"Successfully broadcasted DEREGISTER_AGENT for {agent_id} to {len(active_connections) - len(disconnected)} frontends")
    except Exception as e:
        logger.error(f"Error broadcasting DEREGISTER_AGENT for {agent_id}: {e}")

def update_agent_status(agent_id: str, agent_name: str, internal_state: str = "offline") -> bool:
    """Updates an agent's status in the state.
    
    Args:
        agent_id: ID of the agent to update
        agent_name: Name of the agent
        internal_state: Internal state of the agent (e.g. "idle", "working", "paused", "offline")
    
    Returns True if the agent's status changed, False otherwise.
    """
    logger.info(f"Updating agent status: {agent_id}, name={agent_name}, state={internal_state}")
    
    # Ensure agent ID exists
    if not agent_id:
        logger.warning("Cannot update agent status: empty agent ID")
        return False
        
    current_time = datetime.now().isoformat()
    status_changed = False
    
    # Create metrics for the update
    metrics = {
        "last_seen": current_time,
        "internal_state": internal_state
    }
    
    # Check if agent exists
    if agent_id in state.agent_states:
        agent_state = state.agent_states[agent_id]
        
        # Skip update if nothing changed
        current_state = agent_state.metrics.get("internal_state", "initializing")
        new_state = metrics["internal_state"]
        
        if current_state == new_state and agent_state.agent_name == agent_name:
            logger.debug(f"No change in agent {agent_id} status, skipping update.")
            return False
            
        # Update the agent state
        agent_state.agent_name = agent_name
        agent_state.last_seen = current_time
        
        # Update metrics
        agent_state.update_metrics(metrics)
        
        # Update legacy status for compatibility
        state.agent_statuses[agent_id] = agent_state.to_agent_status()
        
        logger.info(f"Updated existing agent: {agent_id}, name={agent_name}, internal_state={new_state}")
        status_changed = True
    else:
        # Create a new agent state
        agent_state = state.AgentState(agent_id, agent_name)
        agent_state.last_seen = current_time
        
        # Set metrics
        agent_state.update_metrics(metrics)
        
        # Add to state
        state.agent_states[agent_id] = agent_state
        
        # Also create legacy status
        state.agent_statuses[agent_id] = agent_state.to_agent_status()
        
        logger.info(f"Created new agent state: {agent_id}, name={agent_name}, internal_state={internal_state}")
        status_changed = True
    
    # If status changed, broadcast the update
    if status_changed:
        # Schedule full update via gRPC first for immediate response
        asyncio.create_task(agent_status_service.broadcast_agent_status_updates(is_full_update=True))
        
        # Also schedule the full broadcast which handles frontends via WebSockets
        asyncio.create_task(broadcast_agent_status(is_full_update=True, target_websocket=None))
        
    return status_changed

def mark_agent_offline(agent_id: str) -> bool:
    """Marks an agent as offline. Returns True if the status changed."""
    logger.info(f"Marking agent offline: {agent_id}")
    if agent_id in state.agent_states:
        agent_state = state.agent_states[agent_id]
        # Set all metrics/state attributes to offline template
        offline_metrics = {
            "internal_state": "offline",
            "grpc_status": "disconnected",
            "registration_status": "not_registered",
            "message_queue_status": "not_connected",
            "llm_client_status": "not_configured",
            "last_seen": datetime.now().isoformat()
        }
        agent_state.metrics.update(offline_metrics)
        agent_state.last_seen = offline_metrics["last_seen"]
        # Update legacy status
        state.agent_statuses[agent_id] = agent_state.to_agent_status()
        logger.info(f"Agent {agent_id} marked as offline with all metrics reset.")
        # Broadcast via gRPC and WebSocket
        asyncio.create_task(agent_status_service.broadcast_agent_status_updates(is_full_update=True))
        asyncio.create_task(broadcast_agent_status(is_full_update=True, target_websocket=None))
        return True
    else:
        logger.warning(f"Cannot mark unknown agent {agent_id} as offline.")
    return False