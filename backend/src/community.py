from typing import Dict, List

import logging
import os
from dotenv import load_dotenv
from agent import Agent
from communication import CommunicationHub

# Load environment variables from .env file
load_dotenv()

# Get the logging level from the .env file
logging_level = os.getenv('LOGGING_LEVEL', 'INFO').upper()

# Set up logging configuration
logging.basicConfig(
    level=getattr(logging, logging_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Community:
    def __init__(self, name: str):
        self.name = name
        self.agents: Dict[str, Agent] = {}
        self.comm_hub = CommunicationHub()
        logger.info("Community created") 
        
    def add_agent(self, agent: Agent):
        """Add a new agent to the community"""
        logging.debug(f"Adding agent {agent.id} to community {self.name}")
        self.agents[agent.id] = agent
        self.comm_hub.register_agent(agent)
        
    def remove_agent(self, agent_id: str):
        """Remove an agent from the community"""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            self.comm_hub.unregister_agent(agent)
            del self.agents[agent_id]
            
    async def start(self):
        """Start the community's communication hub"""
        self.comm_hub.running = True
        logger.debug(f"Community {self.name} started")

    async def run(self):
        """Run the community's message loop"""
        logger.debug(f"Community {self.name} running message loop")
        await self.comm_hub.message_loop()
        logger.debug(f"Community {self.name} message loop finished")
            
    async def stop(self):
        """Stop the community"""
        # Update all agents to offline status
        # for agent in self.agents.values():
        #     update_agent_monitor(agent, "offline")
        await self.comm_hub.stop()

    async def broadcast_message(self, message):
        """Broadcast a message to all agents"""
        logging.debug(f"Broadcasting message: {message.content}")
        # Send to monitoring
        # await broadcast_message(message)
        # Send to agents
        await self.comm_hub.route_message(message) 
