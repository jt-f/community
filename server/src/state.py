from typing import Dict, Set, Optional
from fastapi import WebSocket
import pika
import asyncio

# Import shared models
from shared_models import AgentStatus, setup_logging

# Configure logging
logger = setup_logging(__name__)

# WebSocket Connections
active_connections: Set[WebSocket] = set()
agent_connections: Dict[str, WebSocket] = {}
frontend_connections: Set[WebSocket] = set()
broker_connections: Dict[str, WebSocket] = {}  # broker_id -> WebSocket

# Agent Status Tracking
agent_statuses: Dict[str, AgentStatus] = {}
agent_status_history: Dict[str, AgentStatus] = {} # Previous status for change detection

# RabbitMQ Connection
# Note: This will be managed (created/updated) by functions in rabbitmq_utils.py
rabbitmq_connection: Optional[pika.BlockingConnection] = None

# Broker status tracking
broker_statuses: Dict[str, Dict] = {}  # broker_id -> status dict
broker_status_lock = asyncio.Lock()

# Broker status tracking
broker_status = {
    "is_online": False,
    "last_seen": None
} 