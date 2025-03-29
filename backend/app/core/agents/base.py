"""
Base agent implementation.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, AsyncGenerator, Set, Any, Tuple, Union, ClassVar
from uuid import uuid4
import asyncio
import time
import os
import json

from ..models import Message, WebSocketMessage, AgentState, AgentConfig
from ...utils.logger import get_logger
from ...utils.message_utils import truncate_message
from ...utils.id_generator import generate_short_id

logger = get_logger(__name__)

# Global registries to ensure uniqueness
_used_agent_ids: Set[str] = set()
_used_agent_names: Set[str] = set()

class BaseAgent(ABC):
    """Base agent class defining the core agent interface."""
    
    name: ClassVar[str] = "BaseAgent"
    agent_type: ClassVar[str] = "base"
    description: ClassVar[str] = "Base agent implementation"
    capabilities: ClassVar[List[str]] = []
    config: ClassVar[Dict[str, Any]] = {}
    
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
            
        # Generate a unique shorter ID
        self.agent_id = generate_short_id()
        while self.agent_id in _used_agent_ids:
            self.agent_id = generate_short_id()
                
        self.name = name
        self.message_queue = asyncio.Queue()
        self.last_think_time = 0
        self.think_interval = think_interval
        self._think_counter = 0  # Initialize the think counter
        self.agent_server = None  # Reference to the agent server, set by the agent manager
        self._state = AgentState(
            id=self.agent_id,
            name=self.name,
            type=self.__class__.__name__.lower().replace('agent', ''),  # Extract type from class name
            status="idle",
            queue_size=0,
            last_activity=datetime.now().isoformat(),
            capabilities=self.capabilities or []
        )
        
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
    def id(self) -> str:
        """Get the agent's unique ID."""
        return self.agent_id
    
    @property
    def state(self) -> AgentState:
        """Get the agent's current state."""
        return self._state
    
    async def add_message(self, message: Message) -> None:
        """Add a message to the agent's queue."""
        logger.debug(f"Agent {self.agent_id} received message: '{truncate_message(message.content.get('text'))}'")
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

    async def set_status(self, status: str) -> None:
        """
        Update the agent's status.
        
        Args:
            status: The new status
        """
        self._state.status = status
        self._state.last_activity = datetime.now().isoformat()
        # Notify the agent server of the status change if there is one
        if self.agent_server:
            await self.agent_server.broadcast_state()
    
    async def _should_think(self) -> bool:
        """Determine if the agent should run a thinking cycle."""
        current_time = time.time()
        logger.debug(f"{self.name}:{self.agent_id} Checking if should think")
        logger.debug(f"{self.name}:{self.agent_id} Current time: {current_time} Last think time: {self.last_think_time} Think interval: {self.think_interval}")
        decision_interval =  current_time - self.last_think_time
        logger.debug(f"{self.name}:{self.agent_id} Decision interval: {decision_interval}")
        think_decision = decision_interval > self.think_interval
        logger.debug(f"{self.name}:{self.agent_id} Think decision: {think_decision}")
        return think_decision
    
    async def _think(self) -> AsyncGenerator[Message, None]:
        """
        Perform an internal thinking cycle, without external stimulus.
        
        Agents may override this to provide proactive behavior.
        """
        if self.message_queue.empty():
            logger.debug(f"Agent {self.name} thinking...")
            self._think_counter += 1
            self.last_think_time = time.time()
            yield Message(
                sender_id=self.agent_id,
                receiver_id="broadcast",
                content={"text": f"{self.name} - Thinking cycle {self._think_counter}", "type": "thinking"},
                message_type="thinking"
            )
    
    async def run(self) -> AsyncGenerator[Message, None]:
        """
        Main agent processing loop. Processes messages from the queue and runs thinking cycles.
        
        Yields:
            Message objects representing the agent's responses/actions
        """
        while True:
            try:
                # Check if we should run a thinking cycle
                if await self._should_think():
                    async for response in self._think():
                        yield response
                
                # Check for messages in the queue (non-blocking)
                if not self.message_queue.empty():
                    message = await self.message_queue.get()
                    await self.set_status("responding")
                    
                    # Process the message
                    async for response in self.process_message(message):
                        yield response
                    
                    self.message_queue.task_done()
                    await self.set_status("idle")
                
                # Sleep briefly to prevent CPU spinning
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.exception(f"Error in agent {self.name} run loop: {e}")
                await asyncio.sleep(1)  # Sleep after an error to prevent rapid failures
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current state of the agent as a dictionary."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "type": self.__class__.__name__.lower().replace('agent', ''),
            "status": self._state.status,
            "queue_size": self.message_queue.qsize(),
            "last_activity": self._state.last_activity,
            "capabilities": self.capabilities
        }

    @classmethod
    def clear_registries(cls):
        """Clear the registries of used IDs and names (mainly for testing)."""
        _used_agent_ids.clear()
        _used_agent_names.clear()

    def has_messages(self) -> bool:
        """Check if the agent has messages in its queue."""
        return not self.message_queue.empty()

    async def process_messages(self):
        """Process all messages in the queue."""
        while not self.message_queue.empty():
            message = await self.message_queue.get()
            
            try:
                response = await self.process_message(message)
                logger.info(f"<{self.name}> generated response : '{response.content.get('text')}'")
                await self.agent_server.route_message(response) 
                self.message_queue.task_done()
                await self.set_status("idle")   

            except Exception as e:
                logger.error(f"(process_messages) Error processing message: {e}", exc_info=True)
                self.message_queue.task_done()
                await self.set_status("idle")