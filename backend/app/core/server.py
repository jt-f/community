"""
Agent server implementation for managing agents and WebSocket connections.
"""
from typing import Dict, Set, Any
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import uuid
from datetime import datetime

from .models import Message, WebSocketMessage
from .agents.base import BaseAgent
from .agents.system import SystemAgent
from .agents.human import HumanAgent
from .agents.analyst import AnalystAgent
from .agent_manager import AgentManager
from ..utils.message_utils import truncate_message

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
        logger.debug("Agent server started")
        
        # Start the message processing loop
        asyncio.create_task(self._process_messages())
        
    async def stop(self):
        """Stop the agent server."""
        if not self.running:
            return
            
        self.running = False
        self.agent_manager.stop()
        
        logger.debug("Agent server stopped")
        
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
        logger.debug(f"Handling message: {truncate_message(message)}")
        
        # Create a WebSocket message for broadcasting
        try:
            ws_message = WebSocketMessage(
                type="message",
                data={
                    "message": message.dict() if hasattr(message, "dict") else message,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Broadcast the message to all clients
            logger.info(f"Broadcasting message from _handle_message")
            await self.broadcast_message(ws_message)
        except Exception as e:
            logger.error(f"Error broadcasting message from queue: {e}")
        
    async def route_message(self, message: Message):
        """Route a message to the appropriate agent."""
        logger.debug(f"Routing message: {truncate_message(message)}")
        
        # First, broadcast this message to all WebSocket clients
        try:
            # Create a WebSocket message from the agent message
            ws_message = WebSocketMessage(
                type="message",
                data={
                    "message": message.dict() if hasattr(message, "dict") else message,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Broadcast the message to all clients
            logger.info(f"Broadcasting message from route_message")
            await self.broadcast_message(ws_message)
        except Exception as e:
            logger.error(f"Error broadcasting message to WebSocket clients: {e}")
        
        # Check if the message has a receiver attribute
        has_receiver = hasattr(message, 'receiver') and message.receiver is not None
        
        # Check if there's a specific receiver
        if has_receiver and message.receiver != "broadcast":
            logger.info(f"Routing message to {message.receiver}")
            # Check if the receiver is a user ID
            if message.receiver.startswith("user-"):
                # Try to find a human agent for this user
                human_agent = None
                for agent_id, agent in self.agents.items():
                    if agent_id == message.receiver and isinstance(agent, HumanAgent):
                        human_agent = agent
                        break
                
                # If no human agent exists for this user, create one
                if not human_agent:
                    logger.debug(f"Creating new human agent for user {message.receiver}")
                    human_agent = HumanAgent(agent_id=message.receiver)
                    await self.register_agent(human_agent)
                
                # Route the message to the human agent
                logger.info(f"Routing message to human agent {message.receiver}")
                await human_agent.receive_message(message)
                
                # Queue the message for broadcastin
                await self.message_queue.put(message)
                
                # Broadcast the updated state to all clients

                await self.broadcast_state()
                
                return
            
            # Try to find the agent by ID
            if message.receiver in self.agents:
                agent = self.agents[message.receiver]
                logger.info(f"Routing message to AI agent {message.receiver}")
                await agent.receive_message(message)
                
                # Queue the message for broadcasting
                await self.message_queue.put(message)
                
                # Broadcast the updated state to all clients
                await self.broadcast_state()
                
                return
            else:
                logger.warning(f"No agent found for receiver {message.receiver}")
        
        # If no specific receiver or receiver not found, just queue for broadcasting
        logger.info("Queueing message for broadcasting")
        await self.message_queue.put(message)
        
        # Broadcast the updated state to all clients
        await self.broadcast_state()


    async def broadcast_message(self, message: WebSocketMessage):
        """Broadcast a message to all connected WebSocket clients."""
        # Convert to JSON-serializable format
        if isinstance(message, dict):
            data = message
        else:
            data = message.dict()
            
        # Send to all connected clients
        if data['type'] == 'message':
            logger.info(f"Sending message ({data['type']}) to client: {truncate_message(data['data'].get('message', {}))}")
                
        for client in self.websocket_clients:
            try:
                await client.send_json(data)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                
    def register_websocket(self, websocket):
        """Register a WebSocket connection."""
        self.websocket_clients.add(websocket)
        logger.debug(f"WebSocket client registered. Total clients: {len(self.websocket_clients)}")
        
    def unregister_websocket(self, websocket):
        """Unregister a WebSocket connection."""
        self.websocket_clients.discard(websocket)
        logger.debug(f"WebSocket client unregistered. Total clients: {len(self.websocket_clients)}")

    async def register_agent(self, agent: BaseAgent):
        """Register an agent with the server and manager."""
        # Set the agent_server reference in the agent
        agent.agent_server = self
        
        # Register with the server
        self.agents[agent.agent_id] = agent
        logger.debug(f"(register_agent) Added agent {agent.agent_id} to server.agents dictionary")
        
        # Register with the agent manager
        self.agent_manager.register_agent(agent)
        logger.debug(f"(register_agent) Registered agent {agent.agent_id} with agent_manager")
        
        # Log the current state of agents
        logger.debug(f"(register_agent) Current agents in server: {list(self.agents.keys())}")
        logger.debug(f"(register_agent) Current agents in manager: {[a.agent_id for a in self.agent_manager.available_agents + self.agent_manager.thinking_agents]}")
        
        # Broadcast the updated state to all clients
        logger.debug(f"(register_agent) Broadcasting state to all clients")
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
        logger.debug("=== BROADCASTING AGENT STATES TO CLIENTS ===")
        if not self.websocket_clients:
            logger.warning("No WebSocket clients connected. Agent state update not sent.")
            return
            
        try:
            # Log all registered agents for debugging
            logger.debug(f"Total agents in self.agents: {len(self.agents)}")
            for agent_id, agent in self.agents.items():
                logger.debug(f"Agent in self.agents: {agent_id}, type: {type(agent).__name__}")
            
            # Log all agents in agent_manager for debugging
            available_agents = self.agent_manager.available_agents
            thinking_agents = self.agent_manager.thinking_agents
            logger.debug(f"Total agents in agent_manager: {len(available_agents) + len(thinking_agents)}")
            for agent in available_agents:
                logger.debug(f"Available agent in agent_manager: {agent.agent_id}, type: {type(agent).__name__}")
            for agent in thinking_agents:
                logger.debug(f"Thinking agent in agent_manager: {agent.agent_id}, type: {type(agent).__name__}")
            
            # Collect states from all agents
            states = {}
            names = {}
            
            # First, add all agents from self.agents
            for agent_id, agent in self.agents.items():
                try:
                    states[agent_id] = agent.state.dict()
                    names[agent_id] = agent.name
                    logger.debug(f"Added state for agent {agent_id} from self.agents")
                except Exception as e:
                    logger.error(f"Error getting state for agent {agent_id}: {e}")
            
            # Then, ensure all agents from agent_manager are included
            for agent in list(available_agents) + list(thinking_agents):
                if agent.agent_id not in states:
                    try:
                        states[agent.agent_id] = agent.state.dict()
                        names[agent.agent_id] = agent.name
                        logger.debug(f"Added state for agent {agent.agent_id} from agent_manager")
                    except Exception as e:
                        logger.error(f"Error getting state for agent {agent.agent_id} from agent_manager: {e}")
            
            logger.debug(f"Sending state update for {len(states)} agents to {len(self.websocket_clients)} clients")
            
            # Log agent statuses
            statuses = []
            for agent_id, state in states.items():
                status = state.get('status', 'unknown')
                statuses.append(f"{names[agent_id]}: {status}")
            
            message = WebSocketMessage(
                type="state_update",
                data=states
            )
            
            logger.info(f"Broadcasting state update: {statuses}")

            await self.broadcast_message(message)

        except Exception as e:
            logger.error(f"Error broadcasting state: {e}", exc_info=True)
