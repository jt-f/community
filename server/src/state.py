from typing import Dict, Set, Optional, Any
from fastapi import WebSocket
import pika
import asyncio
from datetime import datetime

# Import shared models
from shared_models import AgentStatus, setup_logging
from decorators import log_function_call # Added import

from grpc_services.agent_status_service import broadcast_agent_status_updates
import agent_manager
import logging

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module

class AgentState:
    """
    Agent state tracking using the AgentInfo format.
    All state is stored in metrics dictionary for flexibility and scalability.
    Only agent_id, agent_name and last_seen are kept as direct properties.
    """
    def __init__(self, agent_id: str, agent_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.last_seen = datetime.now().isoformat()
        self.metrics = {
            "internal_state": "initializing"  # Default state
        }

    def update_metric(self, key: str, value: Any) -> None:
        """Update a single metric"""
        str_value = str(value)
        if key not in self.metrics or self.metrics[key] != str_value:
            self.metrics[key] = str_value
            logger.debug(f"Agent {self.agent_id} metric updated: {key} = {str_value}")
    
    def update_metrics(self, metrics: Dict[str, Any]) -> None:
        """Update multiple metrics at once"""
        changed = False
        for key, value in metrics.items():
            str_value = str(value)
            if key not in self.metrics or self.metrics[key] != str_value:
                self.metrics[key] = str_value
                changed = True
                logger.debug(f"Agent {self.agent_id} metric '{key}' set to '{str_value}'") # Log individual change
        
        if changed:
            logger.debug(f"Agent {self.agent_id} metrics updated with {len(metrics)} values")
    
    def to_agent_status(self) -> AgentStatus:
        """Convert to AgentStatus for API/serialization."""
        # No legacy is_online/status fields; just use metrics and core fields
        return AgentStatus(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            last_seen=self.last_seen,
            metrics=self.get_metrics_dict()
        )
    
    def get_metrics_dict(self) -> Dict[str, str]:
        """Get all metrics as a dictionary"""
        # Create a copy of the metrics
        metrics_copy = self.metrics.copy()
        # Ensure core properties are included
        metrics_copy["agent_name"] = self.agent_name
        metrics_copy["last_seen"] = self.last_seen
        return metrics_copy
    
    def __repr__(self):
        internal_state = self.metrics.get("internal_state", "initializing")
        metrics_str = ", ".join([f"{k}={v}" for k, v in self.metrics.items() if k != "internal_state"])
        return (
            f"Agent {self.agent_id} State:\n"
            f"  Name:          {self.agent_name}\n"
            f"  Last Seen:     {self.last_seen}\n"
            f"  Internal State: {internal_state}\n"
            f"  Metrics:       {metrics_str}"
        )

# WebSocket Connections
frontend_connections: Set[WebSocket] = set()

# Agent Status Tracking - unified with AgentState
agent_states: Dict[str, AgentState] = {}  # Primary storage using AgentInfo-compatible format
agent_statuses: Dict[str, AgentStatus] = {}  # Legacy compatibility
agent_status_history: Dict[str, AgentStatus] = {}  # Previous status for change detection

# Agent metadata
agent_metadata: Dict[str, Dict] = {}  # Additional agent information beyond status

# RabbitMQ Connection
rabbitmq_connection: Optional[pika.BlockingConnection] = None

# Broker status tracking
broker_statuses: Dict[str, Dict] = {}  # broker_id -> status dict
broker_status_lock = asyncio.Lock()

@log_function_call # Added decorator
async def update_agent_status(agent_id: str, status: AgentStatus) -> None:
    """Update an agent's status, record history, and broadcast updates to all clients."""
    # Save previous status for change detection
    if agent_id in agent_statuses:
        agent_status_history[agent_id] = agent_statuses[agent_id]
    
    # Update legacy status
    agent_statuses[agent_id] = status
    
    # Update or create the unified agent state
    if agent_id not in agent_states:
        agent_states[agent_id] = AgentState(agent_id, status.agent_name)
    
    # Update the agent state
    agent_state = agent_states[agent_id]
    agent_state.agent_name = status.agent_name
    agent_state.last_seen = status.last_seen
    
    # Update metrics if provided
    if status.metrics:
        agent_state.update_metrics(status.metrics)
    
    logger.debug(f"Updated status for agent {agent_id}")
    
    # Broadcast updates to all clients
    try:
        # Use the unified broadcast function to send to all subscribers
        asyncio.create_task(agent_manager.broadcast_agent_status_to_all_subscribers(is_full_update=True))
    except Exception as e:
        logger.error(f"Error broadcasting agent status updates: {e}")

@log_function_call # Added decorator
async def update_agent_metrics(agent_id: str, agent_name: str, metrics: Dict[str, Any]) -> None:
    """Update an agent's metrics and broadcast the updates."""
    # Create agent state if it doesn't exist
    if agent_id not in agent_states:
        agent_states[agent_id] = AgentState(agent_id, agent_name)
        
    # Update the metrics
    agent_state = agent_states[agent_id]
    agent_state.agent_name = agent_name  # Ensure name is updated
    agent_state.last_seen = datetime.now().isoformat()
    agent_state.update_metrics(metrics)
    
    # Also update legacy status
    agent_statuses[agent_id] = agent_state.to_agent_status()
    
    # Broadcast the updates
    try:
        # Use the unified broadcast function to send to all subscribers
        asyncio.create_task(agent_manager.broadcast_agent_status_to_all_subscribers(is_full_update=True))
    except Exception as e:
        logger.error(f"Error broadcasting agent metrics updates: {e}")

@log_function_call # Added decorator
async def broadcast_agent_status_update(is_full_update: bool = False) -> None:
    """Broadcast agent status updates to all subscribers.
    
    This is a legacy function maintained for backward compatibility.
    It now uses the unified broadcast function from agent_manager.
    """
    try:
        # Use the unified broadcast function from agent_manager
        await agent_manager.broadcast_agent_status_to_all_subscribers(is_full_update=is_full_update)
        logger.debug(f"Broadcast agent status update (full_update={is_full_update})")
    except Exception as e:
        logger.error(f"Error broadcasting agent status update: {e}")