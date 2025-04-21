import logging
from datetime import datetime
import asyncio
from typing import Dict, List, Optional

from shared_models import setup_logging, MessageType

logger = setup_logging(__name__)

class BrokerStateManager:
    """Manages the state of known agents within the Broker service."""

    def __init__(self):
        self._agents: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()  # Use asyncio.Lock instead of threading.Lock

    async def update_agents_from_status(self, message_data: Dict):
        """
        Processes agent status updates received via gRPC or other means.
        Updates the internal state of registered agents. Thread-safe.
        """
        if not isinstance(message_data, dict):
            logger.warning(f"Received non-dictionary data in update_agents_from_status: {type(message_data)}")
            return

        logger.debug(f"Processing agent status update: {message_data}")

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
                is_online = agent.get("is_online", False)
                agent_name = agent.get("agent_name", "Unknown Agent")
                last_seen = agent.get("last_seen", None)

                if agent_id not in self._agents:
                    self._agents[agent_id] = {
                        "name": agent_name,
                        "registration_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "is_online": is_online,
                        "last_seen": last_seen
                    }
                    logger.info(f"Added new agent from status update: {agent_name} ({agent_id}), Online: {is_online}")
                else:
                    if self._agents[agent_id].get("is_online") != is_online:
                        old_status = self._agents[agent_id].get("is_online")
                        self._agents[agent_id]["is_online"] = is_online
                        logger.info(f"Updated agent status: {agent_name} ({agent_id}), Online status changed: {old_status} -> {is_online}")
                    if self._agents[agent_id].get("name") != agent_name:
                        old_name = self._agents[agent_id].get("name")
                        self._agents[agent_id]["name"] = agent_name
                        logger.info(f"Updated agent name: {agent_id} from '{old_name}' to '{agent_name}'")
                    self._agents[agent_id]["last_seen"] = last_seen

            if is_full_update:
                logger.info("Processing full status update - marking missing agents as offline")
                agents_to_mark_offline = set(self._agents.keys()) - updated_ids
                for agent_id_offline in agents_to_mark_offline:
                    if self._agents[agent_id_offline].get("is_online", False):
                        self._agents[agent_id_offline]["is_online"] = False
                        logger.info(f"Marked agent {self._agents[agent_id_offline].get('name', agent_id_offline)} ({agent_id_offline}) as offline (not in full update)")

            await self._log_agent_summary()

    async def get_online_agents(self, exclude_sender_id: Optional[str] = None) -> List[str]:
        """Returns a list of IDs of currently online agents, optionally excluding one."""
        async with self._lock:
            online_agents = [
                agent_id for agent_id, info in self._agents.items()
                if info.get("is_online", False) and agent_id != exclude_sender_id
            ]
            logger.debug(f"Get online agents (excluding {exclude_sender_id}): {online_agents}")
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
        online_agents_count = sum(1 for info in self._agents.values() if info.get("is_online", False))
        logger.info(f"Agent State Summary: Total agents: {len(self._agents)}, Online agents: {online_agents_count}")

