import json
from datetime import datetime
import asyncio
from fastapi.websockets import WebSocketState

# Import shared models, config, state, and utils
from shared_models import AgentStatus, MessageType, setup_logging
import state
import grpc_services

# Configure logging
logger = setup_logging(__name__)

def has_agent_status_changed(agent_id: str, new_status: AgentStatus) -> bool:
    """Check if an agent's status has changed from its previous state."""
    if agent_id not in state.agent_status_history:
        return True  # First time seeing this agent
    
    old_status = state.agent_status_history[agent_id]
    # Compare relevant fields for change detection
    return (old_status.is_online != new_status.is_online or 
            old_status.last_seen != new_status.last_seen or
            old_status.agent_name != new_status.agent_name # Check name changes too
           )

async def broadcast_agent_status(force_full_update: bool = False, is_full_update: bool = False):
    """Broadcast agent status to all clients.
    
    For brokers: Uses gRPC exclusively.
    For frontends: Uses WebSockets for backward compatibility.
    
    Args:
        force_full_update: Force sending a full status update even if no changes detected
        is_full_update: Flag indicating this is a full agent status update (vs. delta)
    """
    logger.info(f"broadcast_agent_status called - force_full_update={force_full_update}, is_full_update={is_full_update}")
    
    # Get current agent status
    agent_status_list = []
    online_agent_count = 0
    
    # Convert agent_statuses to a list for transmission
    for agent_id, status in state.agent_statuses.items():
        agent_status_list.append({
            "agent_id": agent_id,
            "agent_name": status.agent_name,
            "is_online": status.is_online,
            "last_seen": status.last_seen
        })
        if status.is_online:
            online_agent_count += 1
    
    logger.info(f"Online agents: {[s['agent_id'] for s in agent_status_list if s['is_online']]}")
    
    # Check if anything changed or full update is forced
    if not force_full_update and not is_full_update:
        # Check for delta changes
        changes_detected = False
        for agent_id, current_status in state.agent_statuses.items():
            if agent_id in state.agent_status_history:
                history = state.agent_status_history[agent_id]
                if (history.is_online != current_status.is_online or
                    history.agent_name != current_status.agent_name):
                    changes_detected = True
                    logger.info(f"Change detected for agent {agent_id}: "
                               f"online: {history.is_online} -> {current_status.is_online}, "
                               f"name: {history.agent_name} -> {current_status.agent_name}")
                    break
        
        if not changes_detected:
            logger.debug("No agent status changes detected and not forced, skipping broadcast")
            return
    
    # STEP 1: Send update to all brokers via gRPC (primary method)
    logger.info(f"Broadcasting agent status via gRPC to all subscribers")
    await grpc_services.broadcast_agent_status_updates(is_full_update=is_full_update or force_full_update)
    
    # STEP 2: Send update to all frontends via WebSockets (for backward compatibility)
    # Only frontends use WebSockets for agent status updates
    if state.frontend_connections:
        logger.info(f"Broadcasting agent status via WebSockets to {len(state.frontend_connections)} frontends")
        
        # Prepare status update message for frontends
        status_update = {
            "message_type": MessageType.AGENT_STATUS_UPDATE,
            "agents": agent_status_list,
            "is_full_update": is_full_update or force_full_update
        }
        
        try:
            status_update_json = json.dumps(status_update)
            
            # Send agent status to all connected frontends via WebSockets
            frontend_send_count = 0
            for websocket in state.frontend_connections:
                try:
                    frontend_id = getattr(websocket, 'client_id', 'unknown')
                    if not websocket.client_state == WebSocketState.CONNECTED:
                        logger.warning(f"Cannot send agent status to frontend {frontend_id}: WebSocket not connected")
                        continue
                        
                    logger.info(f"Sending agent status ({online_agent_count} online) to frontend {frontend_id}")
                    await websocket.send_text(status_update_json)
                    frontend_send_count += 1
                    logger.info(f"Successfully sent agent status to frontend {frontend_id}")
                except Exception as e:
                    frontend_id = getattr(websocket, 'client_id', 'unknown')
                    logger.error(f"Error sending agent status to frontend {frontend_id}: {e}")
                    
            logger.info(f"Sent agent status to {frontend_send_count}/{len(state.frontend_connections)} frontends")
        except Exception as e:
            logger.error(f"Error preparing or sending agent status update to frontends: {e}")
    
    # Update history with current state regardless of broadcast success
    for agent_id, status in state.agent_statuses.items():
        if agent_id in state.agent_status_history:
            state.agent_status_history[agent_id] = status.model_copy()

def update_agent_status(agent_id: str, agent_name: str, is_online: bool) -> bool:
    """Updates an agent's status in the state.
    
    Returns True if the agent's status changed, False otherwise.
    """
    logger.info(f"Updating agent status: {agent_id}, name={agent_name}, online={is_online}")
    
    # Ensure agent ID exists
    if not agent_id:
        logger.warning("Cannot update agent status: empty agent ID")
        return False
        
    current_time = datetime.now().isoformat()
    status_changed = False
    
    # Check if this agent already exists
    if agent_id in state.agent_statuses:
        old_status = state.agent_statuses[agent_id]
        # Create a copy for change detection
        if agent_id not in state.agent_status_history:
            state.agent_status_history[agent_id] = old_status.model_copy()
        
        # If nothing's changing, don't update the last_seen time
        if (old_status.is_online == is_online and 
            old_status.agent_name == agent_name):
            logger.debug(f"No change in agent {agent_id} status, skipping update.")
            return False
            
        # Update fields that changed
        old_status.is_online = is_online
        if old_status.agent_name != agent_name:
            old_status.agent_name = agent_name
        old_status.last_seen = current_time
        
        logger.info(f"Updated existing agent: {agent_id}, name={agent_name}, online={is_online}")
        status_changed = True
    else:
        # Create a new agent status entry
        new_status = AgentStatus(
            agent_id=agent_id,
            agent_name=agent_name,
            is_online=is_online,
            last_seen=current_time
        )
        state.agent_statuses[agent_id] = new_status
        logger.info(f"Created new agent status entry: {agent_id}, name={agent_name}, online={is_online}")
        status_changed = True
    
    # If status changed, broadcast via gRPC immediately
    if status_changed:
        # Schedule full update via gRPC first for immediate response
        asyncio.create_task(grpc_services.broadcast_agent_status_updates(is_full_update=True))
        
        # Also schedule the full broadcast which handles frontends via WebSockets
        asyncio.create_task(broadcast_agent_status(is_full_update=True))
        
    return status_changed

def mark_agent_offline(agent_id: str) -> bool:
    """Marks an agent as offline. Returns True if the status changed."""
    logger.info(f"Marking agent offline: {agent_id}")
    if agent_id in state.agent_statuses:
        if state.agent_statuses[agent_id].is_online:
            state.agent_statuses[agent_id].is_online = False
            state.agent_statuses[agent_id].last_seen = datetime.now().isoformat()
            logger.info(f"Agent {agent_id} marked as offline.")
            
            # Broadcast via gRPC immediately for quick response
            asyncio.create_task(grpc_services.broadcast_agent_status_updates(is_full_update=True))
            
            # Also schedule full broadcast for frontends
            asyncio.create_task(broadcast_agent_status(is_full_update=True))
            
            return True
        else:
            logger.debug(f"Agent {agent_id} already marked as offline.")
    else:
        logger.warning(f"Cannot mark unknown agent {agent_id} as offline.")
    return False 