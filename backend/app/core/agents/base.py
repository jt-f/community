"""
Base agent implementation.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, AsyncGenerator
from uuid import uuid4

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
        while True:
            logger.info(f"(base_agent) Running agent {self.name}")
            logger.info(f"(base_agent) Getting next message")
            message = await self.get_next_message()
            if message:
                self._state = "busy"
                try:
                    response = await self.process_message(message)
                    if response:
                        self._last_activity = datetime.now().isoformat()
                        yield response
                except Exception as e:
                    logger.error(f"(base_agent) Error processing message: {e} for message: {message.content}")
                    self._state = "error"
                    continue
            
            # Run autonomous behavior
            logger.info(f"(base_agent) Running think cycle")
            self._state = "active"
            try:
                async for thought in self.think():
                    if thought:
                        self._last_activity = datetime.now().isoformat()
                        logger.info(f"(base_agent) Yielding thought: {thought.content}")
                        yield thought
            except Exception as e:
                logger.error(f"Error in think cycle: {e}")
                self._state = "error"
                continue
            
            # Update state if queue is empty
            if not self._message_queue:
                self._state = "idle"
            
            # Sleep briefly to prevent CPU overuse
            await asyncio.sleep(0.1) 