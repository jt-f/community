import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any

from shared_models import setup_logging, MessageType

setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__)
logger.propagate = False  # Prevent messages reaching the root logger


class BrokerState:
    """Manages the state of known agents and the broker's internal status."""

    def __init__(self):
        """Initializes the BrokerState with an empty agent dictionary and lock."""
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        # Store broker's own operational state
        self._broker_state: Dict[str, Any] = {
            'internal_state': 'initializing',
            'registration_status': 'unregistered',
            'message_queue_status': 'disconnected',
        }

    async def update_agents_from_status(self, message_data: Dict):
        """
        Processes agent status updates (typically from gRPC) and updates the internal agent state.

        Handles both full state snapshots and partial updates.
        This method is asynchronous and uses a lock for safe concurrent access.

        Args:
            message_data: A dictionary containing agent status information,
                          expected to have 'message_type', 'agents' list, and 'is_full_update' boolean.
        """
        if not isinstance(message_data, dict):
            logger.warning(f"Received non-dictionary data in update_agents_from_status: {type(message_data)}")
            return

        if message_data.get("message_type") != MessageType.AGENT_STATUS_UPDATE:
            logger.warning(f"Received non-status update message type: {message_data.get('message_type')}")
            return

        agents_data = message_data.get("agents", [])
        is_full_update = message_data.get("is_full_update", False)

        async with self._lock:
            logger.info(f"Processing agent status update ({len(agents_data)} agents, full_update={is_full_update})")

            if is_full_update:
                await self._handle_full_update(agents_data)
            else:
                await self._handle_partial_update(agents_data)

            # Log summary after updates
            await self._log_agent_summary()

    def _process_agent_data(self, agent_data: Dict, existing_agent: Optional[Dict] = None) -> Optional[Dict]:
        """Processes raw agent data, determines online status, and returns a structured agent state dict."""
        agent_id = agent_data.get("agent_id")
        if not agent_id:
            logger.warning(f"Skipping agent data with missing agent_id: {agent_data}")
            return None

        metrics = agent_data.get("metrics", {})
        is_online = self._determine_online_status(metrics)
        agent_name = agent_data.get("agent_name", f"Agent_{agent_id[:4]}")
        last_seen = agent_data.get("last_seen", datetime.now().isoformat())

        # Preserve registration time if agent existed before, otherwise set current time
        registration_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if existing_agent:
            registration_time = existing_agent.get("registration_time", registration_time)

        return {
            "agent_id": agent_id,
            "name": agent_name,
            "is_online": is_online,
            "last_seen": last_seen,
            "metrics": metrics,
            "registration_time": registration_time
        }

    async def _handle_full_update(self, agents_data: List[Dict]):
        """Rebuilds the entire agent state from a full update list. Assumes lock is held."""
        new_agents_state: Dict[str, Dict[str, Any]] = {}
        for agent_data in agents_data:
            processed_data = self._process_agent_data(agent_data, self._agents.get(agent_data.get("agent_id")))
            if processed_data:
                agent_id = processed_data["agent_id"]
                new_agents_state[agent_id] = processed_data
                logger.debug(f"Full update: Processed agent {agent_id}")

        old_ids = set(self._agents.keys())
        new_ids = set(new_agents_state.keys())
        if old_ids != new_ids:
            logger.info(f"Full update changes: Added {new_ids - old_ids}, Removed {old_ids - new_ids}")

        self._agents = new_agents_state
        logger.info(f"Completed full agent state rebuild. Total agents: {len(self._agents)}")

    async def _handle_partial_update(self, agents_data: List[Dict]):
        """Merges partial agent updates into the existing state. Assumes lock is held."""
        updated_count = 0
        new_count = 0
        for agent_data in agents_data:
            agent_id = agent_data.get("agent_id")
            existing_agent = self._agents.get(agent_id)
            processed_data = self._process_agent_data(agent_data, existing_agent)

            if not processed_data:
                continue # Skip if agent_id was missing

            agent_id = processed_data["agent_id"] # Re-get agent_id after processing
            is_new = existing_agent is None
            is_online_now = processed_data["is_online"]
            agent_name = processed_data["name"]

            if is_new:
                new_count += 1
                self._agents[agent_id] = processed_data
                logger.info(f"Partial Update: Registered new agent: {agent_id} (Name: {agent_name}, Online: {is_online_now})")
            else:
                updated_count += 1
                # Log significant changes before updating
                was_online = existing_agent.get("is_online", False)
                if was_online != is_online_now:
                    logger.info(f"Partial Update: Agent {agent_id} online status change: {was_online} -> {is_online_now}")

                old_name = existing_agent.get("name")
                if old_name != agent_name:
                    logger.info(f"Partial Update: Agent {agent_id} name change: '{old_name}' -> '{agent_name}'")

                # Update existing agent info using the fully processed data
                existing_agent.update(processed_data)
                logger.debug(f"Partial Update: Updated existing agent: {agent_id}")
        logger.info(f"Partial update processed: {new_count} new, {updated_count} updated agents.")

    def _determine_online_status(self, metrics: Dict) -> bool:
        """Determines if an agent is considered online based on its metrics."""
        # Define states considered 'offline'
        offline_states = {"offline", "shutting_down", "error", "unknown_status", "unavailable"}
        internal_state = metrics.get("internal_state", "unknown_status") # Default to unknown if not present
        return internal_state not in offline_states

    async def get_online_agents(self, exclude_sender_id: Optional[str] = None) -> List[str]:
        """Returns a list of IDs of currently online agents, optionally excluding one."""
        async with self._lock:
            online_agents = [
                agent_id for agent_id, info in self._agents.items()
                if self._determine_online_status(info.get("metrics", {}))
                and agent_id != exclude_sender_id
            ]
            return online_agents

    async def get_all_agents(self) -> Dict[str, Dict[str, Any]]:
        """Returns a copy of the internal agent dictionary. Thread-safe."""
        async with self._lock:
            return self._agents.copy()

    async def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Returns information about a specific agent. Thread-safe."""
        async with self._lock:
            # Return a copy to prevent external modification
            agent_info = self._agents.get(agent_id)
            return agent_info.copy() if agent_info else None

    async def _log_agent_summary(self):
        """Logs a summary of the current agent state. Assumes lock is already held."""
        online_count = sum(1 for info in self._agents.values() if self._determine_online_status(info.get("metrics", {})))
        total_count = len(self._agents)
        offline_count = total_count - online_count
        logger.info(f"Agent State Summary: Total={total_count}, Online={online_count}, Offline={offline_count}")
        # logger.debug(f"Full agent state: {self._agents}") # Optional: Log full state at debug level

    async def set_state(self, key: str, value: Any):
        """Updates a specific key in the broker's internal operational state. Thread-safe."""
        async with self._lock:
            if key in self._broker_state:
                if self._broker_state[key] != value:
                    logger.info(f"Broker state change: '{key}' = '{value}' (was '{self._broker_state[key]}')")
                    self._broker_state[key] = value
                else:
                    logger.debug(f"Broker state unchanged: '{key}' is already '{value}'")
            else:
                logger.warning(f"Attempted to set unknown broker state key: '{key}'")

    async def get_broker_state(self, key: Optional[str] = None) -> Any:
        """Gets the broker's internal operational state (or a specific key). Thread-safe."""
        async with self._lock:
            if key is None:
                return self._broker_state.copy() # Return a copy of the full state
            elif key in self._broker_state:
                return self._broker_state[key]
            else:
                logger.warning(f"Attempted to get unknown broker state key: '{key}'")
                return None # Or raise KeyError depending on desired behavior

    def __repr__(self) -> str:
        """Provides a string representation of the broker's state."""
        # Note: This is synchronous and doesn't use the lock, might show slightly stale data
        state_lines = ["Broker State:"]
        for key, value in self._broker_state.items():
            state_lines.append(f"  {key}: {value}")
        state_lines.append(f"  Known Agents: {len(self._agents)}")
        return "\n".join(state_lines)
