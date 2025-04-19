from typing import Dict, Set, Optional
from fastapi import WebSocket
import pika
import asyncio

# Import shared models
from shared_models import AgentStatus, setup_logging
import agent_manager

# Configure logging
logger = setup_logging(__name__)

# WebSocket Connections
frontend_connections: Set[WebSocket] = set()

# Agent Status Tracking
agent_statuses: Dict[str, AgentStatus] = {}
agent_status_history: Dict[str, AgentStatus] = {} # Previous status for change detection

# Agent metadata
agent_metadata: Dict[str, Dict] = {}  # Additional agent information beyond status

# RabbitMQ Connection
rabbitmq_connection: Optional[pika.BlockingConnection] = None

# Broker status tracking
broker_statuses: Dict[str, Dict] = {}  # broker_id -> status dict
broker_status_lock = asyncio.Lock()

async def update_agent_status(agent_id: str, status: AgentStatus) -> None:
    """Update an agent's status, record history, and broadcast updates to all clients."""
    # Save previous status for change detection
    if agent_id in agent_statuses:
        agent_status_history[agent_id] = agent_statuses[agent_id]
    
    # Update with new status
    agent_statuses[agent_id] = status
    logger.debug(f"Updated status for agent {agent_id}: online={status.is_online}")
    
    # Broadcast updates to all clients
    try:
        # Broadcast to frontends via WebSockets
        asyncio.create_task(agent_manager.broadcast_agent_status(is_full_update=True, target_websocket=None))
        
        # Broadcast to brokers via gRPC
        asyncio.create_task(broadcast_agent_status_update(is_full_update=True))
    except Exception as e:
        logger.error(f"Error broadcasting agent status updates: {e}")

async def broadcast_agent_status_update(is_full_update: bool = False) -> None:
    """Broadcast agent status updates to all subscribers via gRPC."""
    # Import here to avoid circular imports
    from grpc_services import broadcast_agent_status_updates
    
    try:
        # Call the broadcast function from the gRPC service
        await broadcast_agent_status_updates(is_full_update=is_full_update)
        logger.debug(f"Broadcast agent status update (full_update={is_full_update})")
    except Exception as e:
        logger.error(f"Error broadcasting agent status update: {e}") 