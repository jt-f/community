import logging
from datetime import datetime
import asyncio
from typing import Dict, List, Optional

from shared_models import setup_logging, MessageType

logger = setup_logging(__name__)

class BrokerState:
    """Manages the state of known agents within the Broker service."""

    def __init__(self):
        self._agents: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self._state = {
            'internal_state': 'initializing',
        }

    async def update_agents_from_status(self, message_data: Dict):
        """
        Processes agent status updates received via gRPC or other means.
        Updates the internal state of registered agents. Thread-safe.
        """
        if not isinstance(message_data, dict):
            logger.warning(f"Received non-dictionary data in update_agents_from_status: {type(message_data)}")
            return

        logger.info(f"Processing agent status update: {message_data}")

        if message_data.get("message_type") != MessageType.AGENT_STATUS_UPDATE:
            logger.warning(f"Received non-status update message in status handler: {message_data.get('message_type')}")
            return

        agents_data = message_data.get("agents", [])
        is_full_update = message_data.get("is_full_update", False)

        async with self._lock:
            # --- Handle empty agent list explicitly ---
            if not agents_data and is_full_update:
                logger.warning("Received empty full agent status update. Clearing registered agents list.")
                self._agents.clear()
                logger.info(f"Cleared registered agents list due to empty full update.")
                await self._log_agent_summary()
                return

            logger.info(f"Processing status update for {len(agents_data)} agents (is_full_update={is_full_update})")

            updated_ids = set()
            # Update our internal state with the current agent statuses
            for agent in agents_data:
                agent_id = agent.get("agent_id")
                if not agent_id:
                    logger.warning("Received agent status entry with no ID")
                    continue

                updated_ids.add(agent_id)
                agent_name = agent.get("agent_name", "Unknown Agent")
                last_seen = agent.get("last_seen", None)
                metrics = agent.get("metrics", {})

                if agent_id not in self._agents:
                    self._agents[agent_id] = {
                        "name": agent_name,
                        "registration_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "last_seen": last_seen,
                        "metrics": metrics
                    }
                    logged_state = metrics.get("internal_state", "unknown") 
                    logger.info(f"Added new agent from status update: {agent_name} ({agent_id}), State: {logged_state}")
                else:
                    old_state = self._agents[agent_id].get("metrics", {}).get("internal_state", "unknown")
                    new_state = metrics.get("internal_state", "unknown")
                    if old_state != new_state:
                        logger.info(f"Updated agent status: {agent_name} ({agent_id}), State changed: {old_state} -> {new_state}")
                    if self._agents[agent_id].get("name") != agent_name:
                        old_name = self._agents[agent_id].get("name")
                        self._agents[agent_id]["name"] = agent_name
                        logger.info(f"Updated agent name: {agent_id} from '{old_name}' to '{agent_name}'")
                    self._agents[agent_id]["last_seen"] = last_seen
                    self._agents[agent_id]["metrics"] = metrics

            if is_full_update:
                logger.info("Processing full status update - marking missing agents as offline")
                agents_to_mark_offline = set(self._agents.keys()) - updated_ids
                for agent_id_offline in agents_to_mark_offline:
                    current_metrics = self._agents[agent_id_offline].get("metrics", {})
                    if current_metrics.get("internal_state") != "offline":
                        current_metrics["internal_state"] = "offline"
                        self._agents[agent_id_offline]["metrics"] = current_metrics 
                        self._agents[agent_id_offline]["last_seen"] = datetime.now().isoformat() 
                        logger.info(f"Marked agent {self._agents[agent_id_offline].get('name', agent_id_offline)} ({agent_id_offline}) as offline (not in full update)")

            await self._log_agent_summary()

    async def get_online_agents(self, exclude_sender_id: Optional[str] = None) -> List[str]:
        """Returns a list of IDs of currently online agents, optionally excluding one."""
        async with self._lock:
            online_agents = [
                agent_id for agent_id, info in self._agents.items()
                if info.get("metrics", {}).get("internal_state", "offline") not in ["offline", "shutting_down", "error"] 
                and agent_id != exclude_sender_id
            ]
            logger.info(f"Online agents (active): {online_agents}")
            return online_agents

    async def get_all_agents(self) -> Dict[str, Dict]:
        """Returns a copy of the internal agent dictionary."""
        async with self._lock:
            return self._agents.copy()

    async def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """Returns information about a specific agent."""
        async with self._lock:
            return self._agents.get(agent_id)

    async def _log_agent_summary(self):
        """Logs a summary of the current agent state. Assumes lock is already held."""
        logger.info(f"Agent State Summary: {self._agents.values()}")
        online_agents_count = sum(1 for info in self._agents.values() if info.get("metrics", {}).get("internal_state", "offline") not in ["offline", "shutting_down", "error"])
        offline_agents_count = sum(1 for info in self._agents.values() if info.get("metrics", {}).get("internal_state", "offline") == "offline")
        logger.info(f"Agent State Summary: Total agents: {len(self._agents)}, Active agents: {online_agents_count}, Offline agents: {offline_agents_count}")

    def set_state(self, key, value):
        self._state[key] = value

    def get_state(self, key=None):
        if key is None:
            return self._state.copy()
        if key not in self._state:
            raise KeyError(f"Invalid state key: {key}")
        return self._state[key]

    def __repr__(self):
        state_lines = ["State:"]
        for key, value in self._state.items():
            state_lines.append(f"  {key}: {value}")
        return "\n".join(state_lines)
