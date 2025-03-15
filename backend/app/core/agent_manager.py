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
        self.busy_agents = []
        self.running = False
        self.server = None  # Will be set after initialization
        self.max_concurrent_tasks = 100
        
    def set_server(self, server):
        """Set the agent server reference."""
        self.server = server
        
    def register_agent(self, agent: BaseAgent):
        """Register a new agent with the manager."""
        # Set the agent_server reference in the agent
        agent.agent_server = self.server
        self.available_agents.append(agent)
        
    def unregister_agent(self, agent: BaseAgent):
        """Unregister an agent from the manager."""
        state_changed = False
        
        if agent in self.available_agents:
            self.available_agents.remove(agent)
            
        if agent in self.busy_agents:
            self.busy_agents.remove(agent)
            state_changed = True
            
        # Broadcast state update if busy agents list changed
        if state_changed and self.server:
            asyncio.create_task(self.server.broadcast_state())
            logger.info(f"Agent {agent.agent_id} removed from busy list - broadcasting state update")
            
    async def run(self):
        """Run the agent manager loop."""
        self.running = True
        logger.info("Agent manager started")
        
        while self.running:
            # Process available agents
            if self.available_agents and len(self.busy_agents) < self.max_concurrent_tasks:
                # Get the next available agent
                agent = self.available_agents.pop(0)
                self.busy_agents.append(agent)

                # Process the agent in the background
                asyncio.create_task(self._process_agent(agent))
            
            # Sleep to avoid busy waiting
            await asyncio.sleep(0.1)
    
    async def _process_agent(self, agent: BaseAgent):
        """Process a single agent."""
        try:
            # Check if the agent has messages to process
            if agent.has_messages():
                # Update agent state to 'responding' when it starts processing messages
                if agent.state.status != 'responding':
                    agent.state.status = 'responding'
                    if self.server:
                        logger.info(f"Agent {agent.agent_id} state changed to 'responding' - broadcasting state update")
                        await self.server.broadcast_state()
                
                # Process the agent's messages
                logger.info(f"Agent {agent.agent_id} has messages to process")
                await agent.process_messages()
                logger.info(f"Agent {agent.agent_id} has processed messages")
                
                # If the agent still has messages, keep it in the busy list
                if agent.has_messages():
                    return
            
            # Remove from busy and add to available
            self.busy_agents.remove(agent)
            self.available_agents.append(agent)
            
            # Update agent state to 'idle' when it has no more messages to process
            if agent.state.status != 'idle':
                agent.state.status = 'idle'
                if self.server:
                    logger.info(f"Agent {agent.agent_id} state changed to 'idle' - broadcasting state update")
                    await self.server.broadcast_state()
            
        except Exception as e:
            # Handle errors, log them
            logger.error(f"Error processing agent {agent.agent_id}: {e}", exc_info=True)
            
            # Remove from busy list
            if agent in self.busy_agents:
                self.busy_agents.remove(agent)
                
                # Update agent state to 'idle' when an error occurs
                if agent.state.status != 'idle':
                    agent.state.status = 'idle'
                    if self.server:
                        logger.info(f"Agent {agent.agent_id} state changed to 'idle' after error - broadcasting state update")
                        await self.server.broadcast_state()
            
            # Add back to available after a short delay
            await asyncio.sleep(1)
            self.available_agents.append(agent)
            
    def stop(self):
        """Stop the agent manager."""
        self.running = False 

    def add_agent(self, agent: BaseAgent):
        """Add a new agent to the available agents pool."""
        logger.info(f"Adding new agent: {agent.name} ({agent.agent_id})")
        
        # Set the agent server reference
        agent.agent_server = self.server
        
        # Add to available agents
        self.available_agents.append(agent)
        
        return agent 