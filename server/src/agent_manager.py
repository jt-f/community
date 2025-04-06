import logging
import json
from datetime import datetime
import asyncio

# Import shared models, config, state, and utils
from shared_models import AgentStatus, AgentStatusUpdate, MessageType
import config
import state
import rabbitmq_utils

logger = logging.getLogger(__name__)

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

async def broadcast_agent_status(force_full_update: bool = False):
    """Broadcast current agent status to all frontend clients and brokers."""
    agents_to_broadcast = []
    changes_detected = False # Flag if delta changes were detected

    if force_full_update:
        agents_to_broadcast = list(state.agent_statuses.values())
        # Update history for all agents when sending full update
        for agent_status in agents_to_broadcast:
            # Use model_copy to avoid modifying the original state object if it's complex later
            state.agent_status_history[agent_status.agent_id] = agent_status.model_copy()
    else:
        # Check for changed agents for delta update
        for agent_id, current_status in state.agent_statuses.items():
            if has_agent_status_changed(agent_id, current_status):
                agents_to_broadcast.append(current_status)
                # Update history only for the changed agent
                state.agent_status_history[agent_id] = current_status.model_copy()
                changes_detected = True

    # --- Decision to broadcast ---
    # Proceed if forcing a full update OR if delta changes were detected
    if not force_full_update and not changes_detected:
        logger.debug("No agent status changes detected for delta update, skipping broadcast.")
        return

    # If force_full_update is true, agents_to_broadcast might be empty if no agents exist.
    # If it's a delta update, agents_to_broadcast will only be non-empty if changes_detected is true.
    logger.debug(f"Preparing to broadcast status for {len(agents_to_broadcast)} agents (Forced: {force_full_update})")

    status_update = {
        "message_type": MessageType.AGENT_STATUS_UPDATE,
        "agents": [agent.model_dump() for agent in agents_to_broadcast],
        "is_full_update": force_full_update
    }
    status_payload = json.dumps(status_update)

    # Send to all connected brokers
    disconnected_brokers = set()
    for broker_id, websocket in state.broker_connections.items():
        try:
            await websocket.send_text(status_payload)
            logger.debug(f"Sent agent status update ({len(agents_to_broadcast)} agents) to broker {broker_id}.")
        except Exception as e:
            logger.error(f"Error sending status update to broker {broker_id}: {e}. Marking broker disconnected.")
            disconnected_brokers.add(broker_id)

    # Remove disconnected brokers
    for broker_id in disconnected_brokers:
        if broker_id in state.broker_connections:
            del state.broker_connections[broker_id]
            logger.info(f"Removed disconnected broker {broker_id}")

    # Then broadcast to all connected frontend clients
    if state.frontend_connections:
        disconnected_clients = set()
        for ws in state.frontend_connections:
            try:
                await ws.send_text(status_payload)
                logger.debug(f"Sent agent status update ({len(agents_to_broadcast)} agents) to frontend client.")
            except Exception as e:
                logger.error(f"Error sending status update to frontend client: {e}. Marking client disconnected.")
                disconnected_clients.add(ws)
        
        # Remove disconnected clients
        state.frontend_connections -= disconnected_clients
        if disconnected_clients:
            logger.info(f"Removed {len(disconnected_clients)} disconnected frontend clients.")
    else:
        logger.debug("No frontend clients connected for status broadcast.")

async def send_agent_status_to_broker():
    """Sends the current agent status list to the broker."""
    try:
        # Get list of active agents
        active_agents = [
            {
                "agent_id": agent_id,
                "agent_name": status.agent_name,
                "is_online": status.is_online,
                "last_seen": status.last_seen
            }
            for agent_id, status in state.agent_statuses.items()
        ]
        
        # Prepare the status update message
        status_message = {
            "message_type": MessageType.AGENT_STATUS_UPDATE,
            "agents": active_agents,
            "is_full_update": True
        }
        
        # Send to all connected brokers
        disconnected_brokers = set()
        for broker_id, websocket in state.broker_connections.items():
            try:
                await websocket.send_text(json.dumps(status_message))
                logger.debug(f"Sent agent status update to broker {broker_id}")
            except Exception as e:
                logger.error(f"Error sending status update to broker {broker_id}: {e}")
                disconnected_brokers.add(broker_id)
        
        # Remove disconnected brokers
        for broker_id in disconnected_brokers:
            if broker_id in state.broker_connections:
                del state.broker_connections[broker_id]
                logger.info(f"Removed disconnected broker {broker_id}")
                
    except Exception as e:
        logger.error(f"Error preparing or sending requested active agent status to broker via WebSocket: {e}")

def update_agent_status(agent_id: str, agent_name: str, is_online: bool):
    """Update the status of an agent in the state."""
    current_time = datetime.now().isoformat()
    agent_status = AgentStatus(
        agent_id=agent_id,
        agent_name=agent_name,
        is_online=is_online,
        last_seen=current_time
    )
    state.agent_statuses[agent_id] = agent_status
    logger.info(f"Updated agent status: {agent_id} ({agent_name}) - Online: {is_online}")

def mark_agent_offline(agent_id: str):
    """Marks an agent as offline if they exist."""
    if agent_id in state.agent_statuses:
        if state.agent_statuses[agent_id].is_online:
             state.agent_statuses[agent_id].is_online = False
             # Update last_seen as well? Depends on desired behavior.
             # state.agent_statuses[agent_id].last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
             logger.info(f"Marked agent {state.agent_statuses[agent_id].agent_name} ({agent_id}) as offline.")
             # Trigger broadcast or let ping service handle it?
             # For immediate feedback, could trigger a broadcast here:
             # asyncio.create_task(broadcast_agent_status())
        else:
             logger.debug(f"Agent {agent_id} is already marked offline.")
    else:
        logger.warning(f"Attempted to mark unknown agent {agent_id} as offline.")

async def handle_agent_disconnection(agent_id: str) -> bool:
    """Handles the disconnection of an agent.

    Removes the agent's WebSocket connection from the active state
    and marks the agent as offline in the status registry.

    Args:
        agent_id: The ID of the agent that disconnected.

    Returns:
        True if the agent was found and marked offline, False otherwise.
    """
    disconnected = False
    agent_name = state.agent_statuses.get(agent_id, AgentStatus(agent_id=agent_id, agent_name="unknown")).agent_name # Get name for logging

    # Remove from active connections if present
    if agent_id in state.agent_connections:
        logger.warning(f"Removing connection for agent {agent_name} ({agent_id}) due to detected disconnection.")
        # Attempt to close websocket gracefully first? Might already be closed.
        ws = state.agent_connections.pop(agent_id, None) # Use pop with None default
        if ws:
             try:
                 # Use a short timeout as the connection is likely already broken
                 await asyncio.wait_for(ws.close(code=1011, reason="Server detected disconnection"), timeout=0.5)
             except asyncio.TimeoutError:
                 logger.debug(f"Timeout closing websocket for disconnected agent {agent_id}, likely already closed.")
             except Exception as e:
                 logger.debug(f"Error during explicit close for disconnected agent {agent_id}: {e}") # Log other potential errors during close
        disconnected = True # Indicate connection was present and removed

    # Mark as offline in the registry (safe to call even if already offline)
    mark_agent_offline(agent_id) # This function handles logging if status changes

    # If we removed the connection, it implies a change even if mark_agent_offline didn't log it
    # But mark_agent_offline should handle the core status change logging.
    # The return value primarily signifies that we processed a disconnect event for this agent ID.
    # We rely on the caller to decide if a broadcast is needed based on *any* disconnections.
    return disconnected # Return true if connection was removed or agent was marked offline

def handle_pong(agent_id: str):
    """Handles a PONG message received from an agent or broker."""
    if agent_id.startswith("broker_"):
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with state.broker_status_lock:
            if agent_id not in state.broker_statuses:
                state.broker_statuses[agent_id] = {
                    "is_online": False,
                    "last_seen": None
                }
            was_offline = not state.broker_statuses[agent_id]["is_online"]
            state.broker_statuses[agent_id]["is_online"] = True
            state.broker_statuses[agent_id]["last_seen"] = current_time_str
            
        logger.info(f"Received PONG from broker {agent_id}. Updated last_seen.")
        if was_offline:
            logger.info(f"Broker {agent_id} is back online after PONG.")
            # Using create_task to avoid blocking the caller
            asyncio.create_task(broadcast_agent_status())
        return
        
    if agent_id in state.agent_statuses:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state.agent_statuses[agent_id].last_seen = current_time_str
        
        was_offline = not state.agent_statuses[agent_id].is_online
        state.agent_statuses[agent_id].is_online = True
        
        logger.info(f"Received PONG from agent {agent_id}. Updated last_seen.")
        
        # If agent was marked offline, trigger an immediate status broadcast
        if was_offline:
            logger.info(f"Agent {agent_id} is back online after PONG. Triggering status update.")
            # Using create_task to avoid blocking the caller (asyncio imported at top)
            asyncio.create_task(broadcast_agent_status())
    else:
        logger.warning(f"Received PONG for unknown or unregistered agent ID: {agent_id}") 