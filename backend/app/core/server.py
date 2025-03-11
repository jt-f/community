"""
Agent server implementation for managing agents and WebSocket connections.
"""
from typing import Dict, Set
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import uuid

from .models import Message, WebSocketMessage
from .agents.base import BaseAgent
from .agents.system import SystemAgent
from .agents.human import HumanAgent
from .agents.analyst import AnalystAgent
from .agent_manager import AgentManager

from ..utils.logger import get_logger

logger = get_logger(__name__)

class AgentServer:
    """Agent server managing WebSocket connections and agent communication."""
    
    def __init__(self):
        """Initialize the agent server."""
        self.running = False
        self.websocket_clients: Set = set()
        self.message_queue = asyncio.Queue()
        self.agent_manager = AgentManager()
        self.agent_manager.set_server(self)  # Set server reference
        self.agents: Dict[str, BaseAgent] = {}
        
    async def start(self):
        """Start the agent server."""
        if self.running:
            return
            
        self.running = True
        logger.info("Agent server started")
        
        # Start the message processing loop
        asyncio.create_task(self._process_messages())
        
    async def stop(self):
        """Stop the agent server."""
        if not self.running:
            return
            
        self.running = False
        logger.info("Agent server stopped")
        
        # Close all WebSocket connections
        for websocket in list(self.websocket_clients):
            try:
                await websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
            finally:
                await self.unregister_websocket(websocket)
        
    async def _process_messages(self):
        """Process messages in the queue."""
        while self.running:
            try:
                # Get the next message from the queue
                message = await self.message_queue.get()
                
                # Process the message
                await self._handle_message(message)
                
                # Mark the task as done
                self.message_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                
            # Sleep briefly to avoid busy waiting
            await asyncio.sleep(0.01)
            
    async def _handle_message(self, message: Message):
        """Handle a message."""
        # Log the message
        logger.debug(f"Handling message: {message}")
        
        # TODO: Implement message routing logic
        
    async def route_message(self, message: Message):
        """Route a message to the appropriate agent."""
        # Add the message to the queue
        await self.message_queue.put(message)
        
    async def broadcast(self, message: WebSocketMessage):
        """Broadcast a message to all connected WebSocket clients."""
        # Convert to JSON-serializable format
        if isinstance(message, dict):
            data = message
        else:
            data = message.dict()
            
        # Send to all connected clients
        for client in self.websocket_clients:
            try:
                await client.send_json(data)
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")
                
    def register_websocket(self, websocket):
        """Register a WebSocket connection."""
        self.websocket_clients.add(websocket)
        logger.info(f"WebSocket client registered. Total clients: {len(self.websocket_clients)}")
        
    def unregister_websocket(self, websocket):
        """Unregister a WebSocket connection."""
        self.websocket_clients.discard(websocket)
        logger.info(f"WebSocket client unregistered. Total clients: {len(self.websocket_clients)}")

    async def register_agent(self, agent: BaseAgent):
        """Register an agent with the server and manager."""
        self.agents[agent.agent_id] = agent
        self.agent_manager.register_agent(agent)
        logger.info(f"(register_agent) Registered agent {agent.agent_id}")
        logger.info(f"(register_agent) Broadcasting state to all clients")
        await self.broadcast_state()
        
    async def remove_agent(self, agent_id: str):
        """Remove an agent from the server."""
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            self.agent_manager.unregister_agent(agent)
            del self.agents[agent_id]
            logger.debug(f"(remove_agent) Removed agent {agent_id}")
            logger.debug(f"(remove_agent) Broadcasting state to all clients")
            await self.broadcast_state()

    async def broadcast_state(self):
        """Broadcast current agent states to all connected clients."""
        logger.debug("(broadcast_state) Broadcasting state to all clients")
        if not self.websocket_clients:
            return
            
        try:
            states = {
                agent_id: agent.state.dict()
                for agent_id, agent in self.agents.items()
            }
            
            message = WebSocketMessage(
                type="state_update",
                data=states
            )
            
            await self.broadcast(message)
        except Exception as e:
            logger.error(f"Error broadcasting state: {e}")

# Create a singleton instance
agent_server = AgentServer()