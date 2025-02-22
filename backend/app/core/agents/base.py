"""
Base agent implementation.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, AsyncGenerator
from uuid import uuid4
import asyncio

from ..models import Message, AgentState, AgentConfig
from ...utils.logger import get_logger

logger = get_logger(__name__)

class BaseAgent(ABC):
    """Base agent class defining the core agent interface."""
    
    def __init__(self, name: str, capabilities: List[str], llm_config: Optional[Dict] = None):
        self.id = str(uuid4())
        self.name = name
        self.capabilities = capabilities
        self.llm_config = llm_config or {}
        self._message_queue: List[Message] = []
        self._state = "idle"
        self._last_activity = datetime.now().isoformat()
        self._think_counter = 0  # Counter for think cycles
        
    @property
    def state(self) -> AgentState:
        """Get the current agent state."""
        return AgentState(
            id=self.id,
            name=self.name,
            status=self._state,
            queue_size=len(self._message_queue),
            last_activity=self._last_activity,
            capabilities=self.capabilities
        )
    
    async def add_message(self, message: Message) -> None:
        """Add a message to the agent's queue."""
        logger.debug(f"Agent {self.name} received message: {message.content}")
        self._message_queue.append(message)
        self._state = "busy"
        self._last_activity = datetime.now().isoformat()
    
    async def get_next_message(self) -> Optional[Message]:
        """Get the next message from the queue."""
        if self._message_queue:
            self._last_activity = datetime.now().isoformat()
            return self._message_queue.pop(0)
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
        logger.debug(f"{self.name} Running agent {self.name}")
        
        # First check for any messages in the queue
        message = await self.get_next_message()
        if message:
            self._state = "busy"
            try:
                response = await self.process_message(message)
                if response:
                    self._last_activity = datetime.now().isoformat()
                    yield response
            except Exception as e:
                logger.error(f"{self.name} Error processing message: {e} for message: {message.content}")
                self._state = "error"
                return
        
        # Then run one think cycle if it's time
        self._think_counter += 1
        logger.debug(f"{self.name} Think counter: {self._think_counter}")
        
        if self.should_think():
            logger.debug(f"{self.name} Running think cycle")
            self._state = "active"
            self._think_counter = 0
            try:
                async for thought in self.think():
                    if thought:
                        self._last_activity = datetime.now().isoformat()
                        logger.debug(f"{self.name} Yielding thought: {thought.content}")
                        yield thought
                    else:
                        logger.debug(f"{self.name} No thought")
                # Reset counter after successful think cycle

            except Exception as e:
                logger.error(f"Error in think cycle: {e}")
                self._state = "error"
                return
        else:
            logger.debug(f"{self.name} Not thinking : counter is {self._think_counter}")
        
        # Update state if queue is empty
        if not self._message_queue:
            self._state = "idle"
            
        # Sleep briefly to prevent CPU overuse
        await asyncio.sleep(0.1)
    
    def should_think(self) -> bool:
        """Determine if the agent should run a think cycle based on counter."""
        # Default implementation - subclasses should override
        return False

    async def think_counter(self) -> int:
        """Get the current think counter."""
        return self._think_counter 