from typing import Dict, Set
import asyncio
import zmq.asyncio
from agent import Agent
import logging
from dataclasses import asdict
import os
from dotenv import load_dotenv
from message import Message

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

class CommunicationHub:
    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self.context = zmq.asyncio.Context()
        self.running = False
        logger.info("Communication hub initialized")
        
    def register_agent(self, agent: Agent):
        """Register an agent with the communication hub"""
        self.agents[agent.id] = agent
        logger.debug(f"Registered agent {agent.name}")
        
    def unregister_agent(self, agent: Agent):
        """Unregister an agent from the communication hub"""
        if agent.id in self.agents:
            del self.agents[agent.id]
            logger.debug(f"Unregistered agent {agent.name}")
            
    async def start(self):
        """Start the communication hub"""
        self.running = True
        logging.debug("Communication hub started")
        
    async def stop(self):
        """Stop the communication hub"""
        self.running = False
        logging.debug("Communication hub stopped")
        
    async def message_loop(self):
        """Main message processing loop"""
        logger.debug("Starting message loop")
        while self.running:
            for agent in self.agents.values():
                logger.debug(f"Agent {agent.name} has {len(agent.message_queue)} messages in queue")
                # Process messages in agent's queue
                if agent.message_queue:
                    message = agent.message_queue.pop(0)
                    logger.debug(f"Popping message from agent {agent.name} queue: {message.content}")
                    response = await agent.process_message(message)
                    if response:
                        logger.debug(f"Routing response from agent {agent.name}: {response}")
                        await self.route_message(response)
                
                # Allow agent to think and generate messages
                thought = await agent.think()
                if thought:
                    logger.debug(f"Routing agent {agent.name}'s thought: {thought}")
                    await self.route_message(thought)
                else:
                    logger.debug(f"Agent {agent.name} has no thought")
            #logger.debug("Message loop iteration complete")
            await asyncio.sleep(3)
            #logger.debug("Message loop ready for next iteration")

    async def route_message(self, message: Dict):
        """Route a message to its intended recipient(s)"""
        # Convert dict to Message object if needed
        if isinstance(message, dict):
            message = Message.from_dict(message)
        
        logger.debug(f"Routing message: {message.content}")
        
        if message.recipient_id:
            # Direct message to specific agent
            recipient_id = message.recipient_id
            logger.debug(f"Directing message to agent {recipient_id}")
            target_agent = next((a for a in self.agents.values() if a.id == recipient_id), None)
            if target_agent:
                logger.debug(f"Adding message to agent {target_agent.name} queue")
                target_agent.add_to_queue(message)
            else:
                logger.error(f"Agent {recipient_id} not found")
        else:
            # Broadcast message to all agents
            logger.debug(f"Broadcasting message to {len(self.agents)} agents")
            for agent in self.agents.values():
                if 'system' not in agent.capabilities:
                    logger.debug(f"Adding message to agent {agent.name} queue")
                    agent.add_to_queue(message)
                else:
                    logger.debug(f"Agent {agent.name} is a system agent, skipping")