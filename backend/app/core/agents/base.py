"""
Base agent implementation.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, AsyncGenerator, Set
from uuid import uuid4
import asyncio
import time

from ..models import Message, AgentState, AgentConfig
from ...utils.logger import get_logger

logger = get_logger(__name__)

# Global registries to ensure uniqueness
_used_agent_ids: Set[str] = set()
_used_agent_names: Set[str] = set()

class BaseAgent(ABC):
    """Base agent class defining the core agent interface."""
    
    def __init__(self, name: str, think_interval: float = 60.0):
        """
        Initialize a new agent.
        
        Args:
            name: Human readable name for the agent
            think_interval: Time in seconds between thinking cycles
            
        Raises:
            ValueError: If the name is already in use by another agent
        """
        if name in _used_agent_names:
            raise ValueError(f"Agent name '{name}' is already in use")
            
        # Generate a unique UUID
        while True:
            new_id = str(uuid4())
            if new_id not in _used_agent_ids:
                break
                
        self.agent_id = new_id
        self.name = name
        self.message_queue = asyncio.Queue()
        self.last_think_time = 0
        self.think_interval = think_interval
        self._think_counter = 0  # Initialize the think counter
        self.agent_server = None  # Reference to the agent server, set by the agent manager
        
        # Register the agent's ID and name
        _used_agent_ids.add(self.agent_id)
        _used_agent_names.add(self.name)
        
    def __del__(self):
        """Clean up agent registration when the object is destroyed."""
        if hasattr(self, 'agent_id'):
            _used_agent_ids.discard(self.agent_id)
        if hasattr(self, 'name'):
            _used_agent_names.discard(self.name)
        
    @property
    def state(self) -> AgentState:
        """Get the current agent state."""
        return AgentState(
            id=self.agent_id,
            name=self.name,
            status="idle",
            queue_size=0,
            last_activity=datetime.now().isoformat(),
            capabilities=[]
        )
    
    async def add_message(self, message: Message) -> None:
        """Add a message to the agent's queue."""
        logger.debug(f"Agent {self.agent_id} received message: {message.content}")
        await self.message_queue.put(message)
    
    async def get_next_message(self) -> Optional[Message]:
        """Non-blocking check for next message."""
        try:
            return self.message_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    @abstractmethod
    async def process_message(self, message: Message) -> Optional[Message]:
        """Process a message and optionally generate a response."""
        pass
    
    @abstractmethod
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """
        Internal processing loop for autonomous behavior.
        Yields messages that should be sent to other agents.
        """
        pass
    
    async def run(self) -> AsyncGenerator[Optional[Message], None]:
        """Main agent processing loop."""
        logger.debug(f"{self.agent_id} Running agent {self.name}")
        
        # First check for any messages in the queue
        message = await self.get_next_message()
        if message:
            try:
                response = await self.process_message(message)
                if response:
                    yield response
            except Exception as e:
                logger.error(f"{self.agent_id} Error processing message: {e} for message: {message.content}")
                return
        
        # Then run one think cycle if it's time
        if self.should_think():
            logger.debug(f"{self.agent_id} Running think cycle")
            try:
                async for thought in self.think():
                    if thought:
                        yield thought
                    else:
                        logger.debug(f"{self.agent_id} No thought")
            except Exception as e:
                logger.error(f"Error in think cycle: {e}")
                return
        
        # Sleep briefly to prevent CPU overuse
        await asyncio.sleep(0.1)
    
    def should_think(self) -> bool:
        """Determine if the agent should run a thinking cycle."""
        current_time = time.time()
        logger.debug(f"{self.name}:{self.agent_id} Checking if should think")
        logger.debug(f"{self.name}:{self.agent_id} Current time: {current_time} Last think time: {self.last_think_time} Think interval: {self.think_interval}")
        decision_interval =  current_time - self.last_think_time
        logger.debug(f"{self.name}:{self.agent_id} Decision interval: {decision_interval}")
        think_decision = decision_interval > self.think_interval
        logger.debug(f"{self.name}:{self.agent_id} Think decision: {think_decision}")
        return think_decision
    
    async def think_once(self) -> Optional[Message]:
        """Run a single thinking cycle. Override in subclasses."""
        self.last_think_time = time.time()
        self._think_counter += 1  # Increment the think counter
        return None
    
    async def think_counter(self) -> int:
        """Get the current think counter."""
        return self._think_counter

    async def enqueue_message(self, message: Message):
        """Add a message to this agent's queue."""
        await self.message_queue.put(message)
        
    @classmethod
    def clear_registries(cls):
        """Clear the registries of used IDs and names (mainly for testing)."""
        _used_agent_ids.clear()
        _used_agent_names.clear() 