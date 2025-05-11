import json
from datetime import datetime, timezone
import asyncio
from fastapi.websockets import WebSocket

# Import shared models, config, state, and utils
from shared_models import MessageType, setup_logging
from decorators import log_function_call
import state
import config # Added for keepalive settings
from grpc_services import agent_status_service
import logging

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module

@log_function_call
async def prepare_agent_status_data(is_full_update: bool = False, force_full_update: bool = False):
    """Prepare agent status data for broadcasting.
    
    Args:
        is_full_update: Flag indicating this is a full agent status update (vs. delta)
        force_full_update: Force sending a full status update even if no changes detected
        
    Returns:
        Tuple containing (agent_status_list, online_agent_count, status_update, status_update_json)
    """
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
    
    
    status_update = {
        "message_type": MessageType.AGENT_STATUS_UPDATE,
        "agents": agent_status_list,
        "is_full_update": is_full_update or force_full_update
    }
    
    status_update_json = json.dumps(status_update)
    return agent_status_list, online_agent_count, status_update, status_update_json

@log_function_call
async def broadcast_to_websocket(target_websocket: WebSocket, status_update_json: str, online_agent_count: int):
    """Send agent status update to a specific WebSocket.
    
    Args:
        target_websocket: The WebSocket to send the update to
        status_update_json: JSON string containing the status update
        online_agent_count: Number of online agents (for logging)
    """
    frontend_id = getattr(target_websocket, 'client_id', 'unknown')
    try:
        # Check if WebSocket is connected - use a different approach that works with FastAPI
        try:
            await target_websocket.send_text(status_update_json)
        except RuntimeError as conn_error:
            if "WebSocket is not connected" in str(conn_error):
                logger.warning(f"Cannot send targeted agent status to frontend {frontend_id}: WebSocket not connected")
            else:
                raise
    except Exception as e:
        logger.error(f"Error sending targeted agent status to frontend {frontend_id}: {e}")

@log_function_call
async def broadcast_to_websockets(status_update_json: str, online_agent_count: int):
    """Broadcast agent status update to all connected WebSockets.
    
    Args:
        status_update_json: JSON string containing the status update
        online_agent_count: Number of online agents (for logging)
    """
    # Broadcast to all connected frontends
    active_connections = state.frontend_connections
    if not active_connections:
        return
        
    # Now we know we have connections to process
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
    
    logger.info(f"Successful broadcast of agent status to {len(active_connections) - len(disconnected)} frontends")

@log_function_call
async def broadcast_agent_status(force_full_update: bool = False, is_full_update: bool = False, target_websocket: WebSocket = None):
    """Broadcast agent status to all clients or a specific frontend client.
    
    For brokers: Uses gRPC exclusively.
    For frontends: Uses WebSockets for backward compatibility.
    
    Args:
        force_full_update: Force sending a full status update even if no changes detected
        is_full_update: Flag indicating this is a full agent status update (vs. delta)
        target_websocket: Optional specific WebSocket to send the update to instead of broadcasting
    """
    
    try:
        # Prepare the agent status data
        _, online_agent_count, _, status_update_json = await prepare_agent_status_data(
            is_full_update=is_full_update, 
            force_full_update=force_full_update
        )
        
        # Determine whether to send to specific target or broadcast to all
        if target_websocket is not None:
            # Target a specific frontend
            await broadcast_to_websocket(target_websocket, status_update_json, online_agent_count)
        else:
            # Broadcast to all connected frontends
            await broadcast_to_websockets(status_update_json, online_agent_count)

    except Exception as e:
        logger.error(f"Error preparing or sending agent status update to frontends: {e}")

@log_function_call
async def broadcast_agent_status_to_all_subscribers(is_full_update: bool = False, force_full_update: bool = False):
    """Broadcasts agent status updates to all subscribers (frontends via WebSockets and brokers via gRPC).

    Args:
        is_full_update: Flag indicating this is a full agent status update (vs. delta).
        force_full_update: Force sending a full status update even if no changes detected (primarily for WebSockets).
    """
    try:
        # Prepare the agent status data once for both channels
        agent_status_list, online_agent_count, status_update, status_update_json = await prepare_agent_status_data(
            is_full_update=is_full_update, 
            force_full_update=force_full_update
        )
        
        # Schedule broadcast to frontends via WebSockets
        asyncio.create_task(broadcast_to_websockets(status_update_json, online_agent_count))
        
        # Schedule broadcast to brokers via gRPC
        # Note: agent_status_service.broadcast_agent_status_updates handles its own logging for success/failure
        asyncio.create_task(agent_status_service.broadcast_agent_status_updates(is_full_update=is_full_update))
        
    except Exception as e:
        logger.error(f"Error initiating broadcast to all subscribers: {e}")
    

@log_function_call
async def broadcast_agent_deregister(agent_id: str):
    """Broadcast a DEREGISTER_AGENT message to all frontend clients to remove the agent from the UI."""
    message = {
        "message_type": MessageType.DEREGISTER_AGENT,
        "agent_id": agent_id,
        "send_timestamp": datetime.now().isoformat(),
    }
    try:
        payload = json.dumps(message)
        active_connections = state.frontend_connections
        if not active_connections:
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
    except Exception as e:
        logger.error(f"Error broadcasting DEREGISTER_AGENT for {agent_id}: {e}")

@log_function_call
async def update_agent_status(agent_id: str, agent_name: str, metrics: dict) -> bool:
    """Updates an agent's status in the state.
    
    Args:
        agent_id: ID of the agent to update
        agent_name: Name of the agent
        metrics: A dictionary containing all metrics reported by the agent.
    
    Returns True if the agent's status changed, False otherwise.
    """
    logger.info(f"Updating agent status for {agent_id} ('{agent_name}') with metrics: {metrics}")
    
    # Ensure agent ID exists
    if not agent_id:
        logger.warning("Cannot update agent status: empty agent ID")
        return False
        
    current_time = datetime.now().isoformat()
    status_changed = False
    
    # Ensure essential metrics are present and add server-side timestamp
    if not metrics:
        metrics = {}
        
    # Derive internal_state
    internal_state = metrics.get("internal_state", "initializing")
    
    # Check if agent exists
    if agent_id in state.agent_states:
        agent_state = state.agent_states[agent_id]
        
        # Always check internal_state change separately to ensure we detect busy/idle transitions
        previous_internal_state = agent_state.metrics.get("internal_state", "initializing")
        state_changed = previous_internal_state != internal_state
        name_changed = agent_state.agent_name != agent_name
        
        # If internal_state or name changed, always update
        if state_changed or name_changed:
            logger.info(f"Agent {agent_id} state changed: internal_state {previous_internal_state} -> {internal_state}")
            # Update the agent state
            agent_state.agent_name = agent_name
            agent_state.last_seen = current_time
            agent_state.update_metrics(metrics)
            status_changed = True
        else:
            # For other metrics, compare more thoroughly
            # Skip update if no significant changes
            metrics_changed = any(agent_state.metrics.get(k) != str(v) for k, v in metrics.items())
            if not metrics_changed:
                # Even if no change, update last_seen to keep the agent 'alive'
                agent_state.last_seen = current_time
                # Update legacy status as well to reflect last_seen update
                if agent_id in state.agent_statuses:
                    state.agent_statuses[agent_id].last_seen = current_time
                return False
            
            # We have detected changes in metrics other than internal_state
            agent_state.agent_name = agent_name
            agent_state.last_seen = current_time
            agent_state.update_metrics(metrics)
            status_changed = True
            
        # Update legacy status for compatibility
        state.agent_statuses[agent_id] = agent_state.to_agent_status()
    else:
        # Create new agent state
        agent_state = state.AgentState(agent_id, agent_name)
        agent_state.last_seen = current_time
        agent_state.update_metrics(metrics)
        state.agent_states[agent_id] = agent_state
        
        # Also create legacy status for backward compatibility
        state.agent_statuses[agent_id] = agent_state.to_agent_status()
        
        status_changed = True
    
    # If status changed, broadcast the update
    if status_changed:
        asyncio.create_task(broadcast_agent_status_to_all_subscribers(is_full_update=True))
        
    return status_changed

@log_function_call
async def mark_agent_offline(agent_id: str) -> bool:
    """Marks an agent as offline. Returns True if the status changed."""
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


@log_function_call
async def agent_keepalive_checker():
    """Periodically checks agent last_seen times and marks inactive agents."""
    while True:
        # Check interval first before performing checks
        await asyncio.sleep(config.AGENT_KEEPALIVE_INTERVAL_SECONDS)
        now = datetime.now(timezone.utc)
        agents_to_mark_unknown = []
        agents_to_mark_offline = []

        try:
            # Use items() for safe iteration if state might change elsewhere (though updates should be async safe)
            current_agent_states = state.agent_states.copy() # Copy for iteration safety
            
            # Get list of agents with active gRPC connections from agent_registration_service
            from grpc_services.agent_registration_service import agent_command_streams
            active_connections = set(agent_command_streams.keys())

            for agent_id, agent_state in current_agent_states.items():
                current_internal_state = agent_state.metrics.get("internal_state", "initializing")
                
                # Check if agent has an active gRPC connection
                has_active_connection = agent_id in active_connections

                # --- Handle agent recovery ---
                # If agent is in unknown_status or offline but has an active connection and was seen recently, recover it
                if current_internal_state in ["unknown_status", "offline"] and has_active_connection:
                    await state.update_agent_metrics(agent_id, agent_state.agent_name, {"internal_state": "idle"})
                    continue

                # --- Skip agents already marked offline ---
                if current_internal_state == "offline" and not has_active_connection:
                    logger.debug(f"Agent {agent_id} is already offline and has no active connection, skipping keepalive check.")
                    continue

                try:
                    last_seen_str = agent_state.last_seen
                    if not last_seen_str:
                        logger.warning(f"Agent {agent_id} has no last_seen timestamp, cannot perform keepalive check.")
                        continue # Cannot check if no last_seen

                    last_seen = datetime.fromisoformat(last_seen_str)
                    # Ensure timezone awareness for comparison
                    if last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=timezone.utc)

                    delta = (now - last_seen).total_seconds()
                    logger.debug(f"Agent {agent_id} last seen: {last_seen_str}, delta: {delta:.1f}s, active connection: {has_active_connection}")

                    # --- Handle transition from active to unknown_status ---
                    # Only mark as unknown if both last_seen is old AND no active connection
                    if delta > config.AGENT_KEEPALIVE_GRACE_SECONDS and not has_active_connection and current_internal_state not in ["unknown_status", "offline"]:
                        logger.warning(f"Agent {agent_id} ({agent_state.agent_name}) missed keepalive window ({delta:.1f}s > {config.AGENT_KEEPALIVE_GRACE_SECONDS}s) and has no active connection. Marking as unknown_status.")
                        agents_to_mark_unknown.append((agent_id, agent_state.agent_name))

                    # --- Handle transition from unknown_status to offline ---
                    # Only mark as offline if it's in unknown_status, has exceeded grace period, AND has no active connection
                    elif current_internal_state == "unknown_status" and delta > config.AGENT_UNKNOWN_OFFLINE_GRACE_SECONDS and not has_active_connection:
                        logger.warning(f"Agent {agent_id} ({agent_state.agent_name}) in unknown_status missed the unknown-to-offline window ({delta:.1f}s > {config.AGENT_UNKNOWN_OFFLINE_GRACE_SECONDS}s) and has no active connection. Marking as offline.")
                        agents_to_mark_offline.append(agent_id)

                    else:
                        # Agent is active or in unknown_status but within grace period or has active connection
                        logger.debug(f"Agent {agent_id} is within its keepalive window or has active connection (delta: {delta:.1f}s)")

                except ValueError as ve:
                    logger.error(f"Error parsing last_seen for agent {agent_id} ('{last_seen_str}'): {ve}")
                except Exception as e:
                    logger.error(f"Unexpected error in keepalive check loop for agent {agent_id}: {e}", exc_info=True)

            # Perform state updates outside the iteration loop
            # Mark agents as unknown_status
            if agents_to_mark_unknown:
                tasks = [
                    state.update_agent_metrics(agent_id, agent_name, {"internal_state": "unknown_status"})
                    for agent_id, agent_name in agents_to_mark_unknown
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result, (agent_id, _) in zip(results, agents_to_mark_unknown):
                    if isinstance(result, Exception):
                        logger.error(f"Failed to update status for agent {agent_id} to unknown_status: {result}")

            # Mark agents as offline
            if agents_to_mark_offline:
                # Use the existing mark_agent_offline function which handles broadcasting
                tasks = [
                    mark_agent_offline(agent_id)
                    for agent_id in agents_to_mark_offline
                ]
                # Await the tasks, but we don't necessarily need the results unless debugging failures
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"Error during agent keepalive check cycle: {e}", exc_info=True)

