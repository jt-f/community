import asyncio
import time
from typing import List, Optional, Dict, Any
from app.core.models import Message, WebSocketMessage
from app.core.agents.base import BaseAgent
from ..utils.logger import get_logger

logger = get_logger(__name__)

class AgentManager:
    def __init__(self):
        """Initialize the agent manager."""
        self.available_agents = []
        self.thinking_agents = []  # Renamed from busy_agents
        self.running = False
        self.agent_server = None  # Will be set after initialization
        self.max_concurrent_tasks = 100
        
    def set_server(self, server):
        """Set the agent server reference."""
        self.agent_server = server
        
    def register_agent(self, agent: BaseAgent):
        """Register a new agent with the manager."""
        # Set the agent_server reference in the agent
        agent.agent_server = self.agent_server
        self.available_agents.append(agent)
        
    def unregister_agent(self, agent: BaseAgent):
        """Unregister an agent from the manager."""
        state_changed = False
        
        if agent in self.available_agents:
            self.available_agents.remove(agent)
            
        if agent in self.thinking_agents:  # Updated from busy_agents
            self.thinking_agents.remove(agent)  # Updated from busy_agents
            state_changed = True
            
        # Broadcast state update if thinking agents list changed
        if state_changed and self.agent_server:
            asyncio.create_task(self.agent_server.broadcast_state())
            logger.debug(f"Agent {agent.agent_id} removed from thinking list - broadcasting state update")
            
    async def run(self):
        """Run the agent manager loop."""
        self.running = True
        logger.debug("Agent manager started")
        
        while self.running:
            # Process available agents
            if self.available_agents and len(self.thinking_agents) < self.max_concurrent_tasks:  # Updated from busy_agents
                # Get the next available agent
                agent = self.available_agents.pop(0)
                self.thinking_agents.append(agent)  # Updated from busy_agents

                # Process the agent in the background
                asyncio.create_task(self._process_agent(agent))
            
            # Sleep to avoid busy waiting
            await asyncio.sleep(0.1)
    
    async def _process_agent(self, agent: BaseAgent):
        """Process a single agent."""
        try:
            # Check if the agent has messages to process
            if agent.has_messages():
                
                # Process the agent's messages
                logger.info(f"Agent {agent.name} ({agent.agent_id}) has messages to process")
                await agent.process_messages()
                logger.info(f"Agent {agent.name} ({agent.agent_id}) has processed messages")
                
                # If the agent still has messages, keep it in the thinking list
                if agent.has_messages():
                    return
            
            # Remove from thinking and add to available
            self.thinking_agents.remove(agent)  # Updated from busy_agents
            self.available_agents.append(agent)
            
            # Update agent state to 'idle' when it has no more messages to process
            if agent.state.status != 'idle':
                await agent.set_status('idle')
            
        except Exception as e:
            # Handle errors, log them
            logger.error(f"Error processing agent {agent.name} ({agent.agent_id}): {e}", exc_info=True)
            
            # Remove from thinking list
            if agent in self.thinking_agents:  # Updated from busy_agents
                self.thinking_agents.remove(agent)  # Updated from busy_agents
                
                # Update agent state to 'idle' when an error occurs
                if agent.state.status != 'idle':
                    await agent.set_status('idle')
            
            # Add back to available after a short delay
            await asyncio.sleep(1)
            self.available_agents.append(agent)
            
    def stop(self):
        """Stop the agent manager."""
        self.running = False 

    def add_agent(self, agent: BaseAgent):
        """Add a new agent to the available agents pool."""
        logger.debug(f"Adding new agent: {agent.name} ({agent.agent_id})")
        
        # Set the agent server reference
        agent.agent_server = self.agent_server
        
        # Add to available agents
        self.available_agents.append(agent)
        
        return agent 