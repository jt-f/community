"""
Shared instances used across the application.
"""
from .agent_manager import AgentManager
from .server import agent_server

# Create agent manager instance that will be used throughout the application
agent_manager = AgentManager()

# Set the server reference after creation
agent_manager.server = agent_server 