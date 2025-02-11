from agent import Agent
import logging
import asyncio
from typing import Dict, Any
from message import Message
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class SystemAgent(Agent):
    def __init__(self):
        # Use a fixed ID for the system agent
        self.id = "system"
        name = "System"
        capabilities = ["system"]
        llm_config = {}

        super().__init__(name=name, capabilities=capabilities, llm_config=llm_config)

    async def process_message(self, message):
        """System agent doesn't process messages"""
        return None
    
    async def think(self):
        """System agent doesn't think autonomously"""
        return None

class HumanAgent(Agent):
    def __init__(self):
        # Use a fixed ID for the human agent
        self.id = "human"
        name = "Human"
        capabilities = ["human"]
        llm_config = {}

        super().__init__(name=name, capabilities=capabilities, llm_config=llm_config)

    async def process_message(self, message):
        """Human agent doesn't process messages"""
        return None
    
    async def think(self):
        """Human agent doesn't think autonomously"""
        return None

class BasicAgent(Agent):
    def __init__(self, name: str, capabilities: list = None, llm_config: Dict[str, Any] = None):
        # Set default values if not provided
        capabilities = capabilities or ["basic"]
        llm_config = llm_config or {"model": "basic"}
        # Call parent constructor with all required arguments
        super().__init__(name=name, capabilities=capabilities, llm_config=llm_config)
        
    async def process_message(self, message):
        """Process incoming messages and generate responses"""
        try:
            # Log the received message
            logger.debug(f"{self.name} processing message: {message.content}")
            
            # Echo the message back with agent name and add some context based on capabilities
            response = f"{self.name} received: {message.content}"
            
            # Add some specific responses based on agent capabilities
            if "echo" in self.capabilities:
                response += "\nI am an echo agent, I repeat what I hear!"
            elif "help" in self.capabilities:
                response += "\nI am an assistant agent, how can I help you?"
            elif "analyze" in self.capabilities:
                response += "\nLet me analyze that for you..."
                
            return Message(
                sender_id=self.id,
                sender_name=self.name,
                recipient_id=message.sender_id,  # Reply to the sender
                content=response,
                timestamp=datetime.now()  # Add current timestamp
            )
        except Exception as e:
            logger.error(f"Error processing message in {self.name}: {e}")
            return Message(
                sender_id=self.id,
                sender_name=self.name,
                recipient_id=message.sender_id,  # Reply to the sender
                content=f"Error processing message: {str(e)}",
                timestamp=datetime.now()  # Add current timestamp
            )
    
    async def think(self):
        """Internal processing loop for autonomous behavior"""
        try:
            # Periodically check if agent should initiate any actions
            if "proactive" in self.capabilities:
                # Example of proactive behavior - send a status update
                return Message(
                    sender_id=self.id,
                    sender_name=self.name,
                    content=f"{self.name} is actively monitoring...",
                    recipient_id=None,  # Broadcast to all
                    timestamp=datetime.now()  # Add current timestamp
                )
            return None
                    
        except Exception as e:
            logger.error(f"Error in think loop for {self.name}: {e}")
            return None

def create_test_agents():
    """Create test agents for the community"""
    agents = []
    
    # Always add the system agent first
    system_agent = SystemAgent()
    agents.append(system_agent)
    logger.debug(f"Created system agent with ID: {system_agent.id}")
    
    # Add the human agent
    human_agent = HumanAgent()
    agents.append(human_agent)
    logger.debug(f"Created human agent with ID: {human_agent.id}")
    
    # Define agent configurations
    agent_configs = [
        {
            "name": "Analyzer",
            "capabilities": ["analyze", "proactive"],
            "llm_config": {"model": "basic"}
        }
        # ,
    #     {
    #         "name": "Assistant",
    #         "capabilities": ["help", "assist"],
    #         "llm_config": {"model": "basic"}
    #     },
    #     {
    #         "name": "Echo",
    #         "capabilities": ["echo"],
    #         "llm_config": {"model": "basic"}
    #     }
    ]
    
    # Create agents from configurations
    for config in agent_configs:
        logger.debug(f"Creating agent: {config['name']} with capabilities: {config['capabilities']}")
        try:
            agent = BasicAgent(
                name=config["name"],
                capabilities=config["capabilities"],
                llm_config=config["llm_config"]
            )
            agents.append(agent)
            logger.debug(f"Created agent: {agent.name} with capabilities: {agent.capabilities}")
        except Exception as e:
            logger.error(f"Error creating agent {config['name']}: {e}")
    
    return agents 