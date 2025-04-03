from typing import Dict, Set, Optional
from fastapi import WebSocket
import pika

# Import shared models only for type hints if necessary, avoid circular dependencies
from shared_models import AgentStatus

# WebSocket Connections
active_connections: Set[WebSocket] = set()
agent_connections: Dict[str, WebSocket] = {}
frontend_connections: Set[WebSocket] = set()
broker_connection: Optional[WebSocket] = None

# Agent Status Tracking
agent_statuses: Dict[str, AgentStatus] = {}
agent_status_history: Dict[str, AgentStatus] = {} # Previous status for change detection

# RabbitMQ Connection
# Note: This will be managed (created/updated) by functions in rabbitmq_utils.py
rabbitmq_connection: Optional[pika.BlockingConnection] = None 