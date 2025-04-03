import logging
import json
from datetime import datetime

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
    """Broadcast current agent status to all frontend clients and the broker."""
    agents_to_broadcast = []
    is_update = False # Flag if there's anything to broadcast

    if force_full_update:
        agents_to_broadcast = list(state.agent_statuses.values())
        is_update = True # Always send if forcing full update
        # Update history for all agents when sending full update
        for agent_status in agents_to_broadcast:
            state.agent_status_history[agent_status.agent_id] = agent_status.model_copy()
    else:
        # Check for changed agents
        for agent_id, current_status in state.agent_statuses.items():
            if has_agent_status_changed(agent_id, current_status):
                agents_to_broadcast.append(current_status)
                # Update history for the changed agent
                state.agent_status_history[agent_id] = current_status.model_copy()
                is_update = True

    if not is_update:
        logger.debug("No agent status changes detected, skipping broadcast.")
        return

    if not agents_to_broadcast:
         logger.debug("No agents to include in status broadcast.")
         # Optionally send an empty update if force_full_update was true?
         # If force_full_update and agent_statuses is empty, maybe send empty list.
         if not force_full_update:
             return

    status_update = AgentStatusUpdate(agents=agents_to_broadcast)
    status_payload = status_update.model_dump_json() # Use model_dump_json for efficiency

    # Send to broker first if connected
    if state.broker_connection:
        try:
            await state.broker_connection.send_text(status_payload)
            logger.debug(f"Sent agent status update ({len(agents_to_broadcast)} agents) directly to broker.")
        except Exception as e:
            logger.error(f"Error sending status update directly to broker: {e}. Marking broker disconnected.")
            state.broker_connection = None # Assume disconnect on error
    else:
        logger.debug("Broker not connected via WebSocket, status not sent directly.")

    # Then broadcast to all connected frontend clients
    if state.frontend_connections:
        disconnected_clients = set()
        for ws in state.frontend_connections:
            try:
                await ws.send_text(status_payload)
            except Exception as e:
                # Handle potential errors (e.g., client disconnected between check and send)
                logger.error(f"Error sending status update to frontend client {getattr(ws, 'client_id', '?')}: {e}")
                disconnected_clients.add(ws)
        
        # Remove clients that failed to send
        state.frontend_connections -= disconnected_clients
        if disconnected_clients:
            logger.info(f"Removed {len(disconnected_clients)} disconnected frontend clients during status broadcast.")
            
        logger.info(f"Broadcast agent status update ({len(agents_to_broadcast)} agents) to {len(state.frontend_connections)} frontend clients.")
    else:
        logger.debug("No frontend clients connected for status broadcast.")

async def send_agent_status_to_broker():
    """Send current ACTIVE agent status list to the broker via RabbitMQ."""
    try:
        active_agent_list = []
        for agent_id, status in state.agent_statuses.items():
            # Only include agents that are currently connected via WebSocket
            if agent_id in state.agent_connections:
                active_agent_list.append(status.model_dump()) # Use model_dump for dict
        
        status_data = {
            "message_type": MessageType.AGENT_STATUS_UPDATE,
            "agents": active_agent_list,
            "is_full_update": True  # Indicate this is a full, active list
        }
        
        if rabbitmq_utils.publish_to_broker_control_queue(status_data):
             logger.info(f"Sent full active agent status update ({len(active_agent_list)} agents) to broker via RabbitMQ.")
        else:
            logger.error("Failed to send active agent status update to broker via RabbitMQ.")

    except Exception as e:
        logger.error(f"Error preparing or sending active agent status to broker: {e}")

def update_agent_status(agent_id: str, agent_name: str, is_online: bool):
    """Updates the status of a specific agent."""
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if agent_id in state.agent_statuses:
        # Update existing agent
        state.agent_statuses[agent_id].is_online = is_online
        state.agent_statuses[agent_id].last_seen = current_time_str
        state.agent_statuses[agent_id].agent_name = agent_name # Update name if changed
        logger.debug(f"Updated status for agent {agent_name} ({agent_id}): online={is_online}")
    else:
        # Add new agent
        state.agent_statuses[agent_id] = AgentStatus(
            agent_id=agent_id,
            agent_name=agent_name,
            is_online=is_online,
            last_seen=current_time_str
        )
        logger.info(f"Added new agent status for {agent_name} ({agent_id}): online={is_online}")
    
    # No broadcast here, broadcast is handled by services or handlers

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

def handle_pong(agent_id: str):
    """Handles a PONG message received from an agent."""
    if agent_id in state.agent_statuses:
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state.agent_statuses[agent_id].last_seen = current_time_str
        
        was_offline = not state.agent_statuses[agent_id].is_online
        state.agent_statuses[agent_id].is_online = True
        
        logger.debug(f"Received PONG from agent {agent_id}. Updated last_seen.")
        
        # If agent was marked offline, trigger an immediate status broadcast
        if was_offline:
            logger.info(f"Agent {agent_id} is back online after PONG. Triggering status update.")
            # Using create_task to avoid blocking the caller
            import asyncio
            asyncio.create_task(broadcast_agent_status())
    else:
        logger.warning(f"Received PONG for unknown or unregistered agent ID: {agent_id}") 