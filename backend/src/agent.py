from typing import Dict, List, Optional
from abc import ABC, abstractmethod
import uuid
import logging
import os
from dotenv import load_dotenv
from datetime import datetime

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

class Agent(ABC):
    def __init__(self, name: str, capabilities: List[str], llm_config: Dict):
        self.id = str(uuid.uuid4()) if not hasattr(self, 'id') else self.id
        self.name = name
        self.capabilities = capabilities
        self.llm_config = llm_config
        self.message_queue = []
        self.status = "idle"
        self.last_activity = datetime.now()
        logger.info(f"Agent {self.name} initialized with status {self.status} and ID {self.id}")
        
    def update_status(self, new_status: str):
        """Update agent status and last activity time"""
        self.status = new_status
        self.last_activity = datetime.now()
        logger.debug(f"Agent {self.name} status updated to {new_status}")
        
    @abstractmethod
    async def process_message(self, message: Dict) -> Optional[Dict]:
        """Process incoming messages and generate responses"""
        logger.debug(f"Agent {self.name} processing message: {message}")
        self.update_status("busy")
        pass
    
    @abstractmethod
    async def think(self) -> Optional[Dict]:
        """Internal processing loop for autonomous behavior"""
        logger.debug(f"Agent {self.name} thinking")
        self.update_status("active")
        pass
    
    def add_to_queue(self, message: Dict):
        """Add message to agent's queue"""
        logger.debug(f"Agent {self.name} received message: {message.content} and added to queue")
        self.message_queue.append(message)
        self.update_status("busy" if self.status == "idle" else self.status)
        logger.debug(f"Agent {self.name} now has {len(self.message_queue)} messages in queue")
