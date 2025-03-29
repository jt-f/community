import asyncio
import time
from typing import List, Optional, Dict, Any
from app.core.models import Message, WebSocketMessage
from app.core.agents.base import BaseAgent
from ..utils.logger import get_logger
from ..utils.message_utils import truncate_message

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
        logger.debug(f"Registering agent {agent.name} ({agent.agent_id}) with agent manager")
        
        # Set the agent_server reference in the agent
        agent.agent_server = self.agent_server
        
        # Check if agent is already registered
        for existing_agent in self.available_agents + self.thinking_agents:
            if existing_agent.agent_id == agent.agent_id:
                logger.warning(f"Agent {agent.agent_id} already registered with agent manager")
                return
        
        # Add to available agents
        self.available_agents.append(agent)
        logger.debug(f"Agent {agent.name} added to available agents")
        logger.debug(f"Total available agents: {len(self.available_agents)}")
        logger.debug(f"Total thinking agents: {len(self.thinking_agents)}")
        
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
            logger.debug(f"Agent {agent.name} removed from thinking list - broadcasting state update")
            
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
        """Process an agent's messages and thinking cycles."""
        try:
            # Run the agent's processing loop to get its responses
            async for response in agent.run():
                if response:
                    # Add the response to the server's message queue for routing
                    await self.agent_server.message_queue.put(response)
                    
                    # If the response is a message, add it to the message history
                    if hasattr(self.agent_server, 'message_history'):
                        self.agent_server.message_history[response.message_id] = response
                    
                    # Log the response for debugging
                    logger.debug(f"Agent {agent.name} produced response: {truncate_message(response.content.get('text', ''))}")
        except Exception as e:
            logger.error(f"Error processing agent {agent.name}: {e}")
        finally:
            # Move the agent back to available agents
            if agent in self.thinking_agents:
                self.thinking_agents.remove(agent)
                self.available_agents.append(agent)
                
                # Broadcast the state change
                if self.agent_server:
                    asyncio.create_task(self.agent_server.broadcast_state())
            
    def stop(self):
        """Stop the agent manager."""
        self.running = False 

    def add_agent(self, agent: BaseAgent):
        """Add a new agent to the available agents pool."""
        logger.debug(f"Adding new agent: {agent.name} ({agent.agent_id})")
        
        # Use the register_agent method to avoid code duplication
        self.register_agent(agent)
        
        return agent 