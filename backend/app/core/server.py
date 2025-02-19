"""
Agent server implementation for managing agents and WebSocket connections.
"""
from typing import Dict, Set
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .models import Message, WebSocketMessage
from .agents.base import BaseAgent
from .agents.default import SystemAgent, HumanAgent, AnalystAgent
from ..utils.logger import get_logger

logger = get_logger(__name__)

class AgentServer:
    """Agent server managing WebSocket connections and agent communication."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.agents: Dict[str, BaseAgent] = {}
        self._running = False
        
    async def connect(self, websocket: WebSocket):
        """Handle new WebSocket connection."""
        try:
            # Only add to active connections if it's not already there
            if websocket not in self.active_connections:
                self.active_connections.add(websocket)
                logger.info("New WebSocket connection added")
                
                # Send initial state only if the connection is established
                if (websocket.client_state == WebSocketState.CONNECTED and 
                    websocket.application_state == WebSocketState.CONNECTED):
                    logger.info("(connect) Broadcasting state")
                    await self.broadcast_state()
                    logger.info("(connect) Finished broadcasting state")
        except Exception as e:
            logger.error(f"Error in connect: {e}")
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        
    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection."""
        try:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
                logger.info("WebSocket connection removed")
        except Exception as e:
            logger.error(f"Error in disconnect: {e}")

    async def route_message(self, message: Message) -> None:
        """Route a message to the appropriate agent(s) queue."""
        try:
            sender_id = message.sender_id
            receiver_id = message.receiver_id

            if receiver_id:
                # Direct message to specific agent
                if receiver_id in self.agents:
                    logger.info(f"Routing message from {sender_id} to {receiver_id}")
                    await self.agents[receiver_id].add_message(message)
                elif receiver_id == "all":
                    logger.info(f"Routing message from {sender_id} to all agents")
                    for agent_id, agent in self.agents.items():
                        if agent_id != sender_id:
                            await agent.add_message(message)
                else:
                    logger.warning(f"Recipient agent {receiver_id} not found")
            else:
                # Broadcast to all agents except sender
                logger.info(f"Not routing to any agents")
                return
        except Exception as e:
            logger.error(f"Error routing message: {e}")
        
    async def broadcast_state(self):
        """Broadcast current agent states to all connected clients."""
        logger.info("(broadcast_state) Broadcasting state to all clients")
        if not self.active_connections:
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
        
    async def broadcast(self, message: WebSocketMessage):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        logger.info(f"(broadcast) message to broadcast: {message.dict()}")
        
        # If this is a message (not a state update), route it to agent queues first
        if message.type == "message":
            await self.route_message(Message(**message.data))
            
        disconnected = set()
        for connection in self.active_connections:
            try:
                # Only send to connections that are fully established
                if (connection.client_state == WebSocketState.CONNECTED and 
                    connection.application_state == WebSocketState.CONNECTED):
                    try:
                        await connection.send_json(message.dict())
                    except Exception as e:
                        logger.error(f"Error sending message: {e}")
                        disconnected.add(connection)
                else:
                    logger.debug(f"Skipping disconnected/unaccepted WebSocket")
                    disconnected.add(connection)
            except Exception as e:
                logger.error(f"Error checking connection state: {e}")
                disconnected.add(connection)
                
        # Remove disconnected clients
        if disconnected:
            logger.info(f"Removing {len(disconnected)} disconnected clients")
            self.active_connections.difference_update(disconnected)

        logger.info('Finished broadcasting')
        
    async def register_agent(self, agent: BaseAgent):
        """Register a new agent with the server."""
        self.agents[agent.id] = agent
        logger.info(f"(register_agent) Registered agent {agent.id}")
        logger.info(f"(register_agent) Broadcasting state to all clients")
        await self.broadcast_state()
        
    async def remove_agent(self, agent_id: str):
        """Remove an agent from the server."""
        if agent_id in self.agents:
            del self.agents[agent_id]
            logger.info(f"(remove_agent) Removed agent {agent_id}")
            logger.info(f"(remove_agent) Broadcasting state to all clients")
            await self.broadcast_state()

    async def start(self):
        """Start the agent server."""
        if self._running:
            return
            
        logger.info("Starting agent server...")
        self._running = True
        
        # Create default agents
        system_agent = SystemAgent()
        human_agent = HumanAgent()
        analyst_agent = AnalystAgent()
        
        # Register default agents
        await self.register_agent(system_agent)
        await self.register_agent(human_agent)
        await self.register_agent(analyst_agent)
        
        logger.info(f"Created default agents: System, Human, and Analyst")
        
        # Start background tasks
        asyncio.create_task(self._run_agents())

    async def stop(self):
        """Stop the agent server."""
        logger.info("Stopping agent server...")
        self._running = False
        
        # Close all WebSocket connections
        for websocket in list(self.active_connections):
            try:
                await websocket.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
            finally:
                await self.disconnect(websocket)

    async def _run_agents(self):
        """Background task to run agent processing loops."""
        last_state_update = 0
        STATE_UPDATE_INTERVAL = 30.0  # Update state every 30 seconds
        
        # Keep track of agent think tasks
        think_tasks = {}
        
        while self._running:
            try:
                current_time = asyncio.get_event_loop().time()
                
                # Process agent messages and thinking
                if self.agents:
                    for agent_id, agent in self.agents.items():
                        # Always check messages from each agent
                        if agent_id not in think_tasks or think_tasks[agent_id].done():
                            # Start a new processing cycle
                            logger.debug(f"(_run_agents) Starting processing cycle for agent {agent.name}")
                            think_tasks[agent_id] = asyncio.create_task(self._process_agent_messages(agent))
                        
                        # Check for completed tasks and handle their results
                        if agent_id in think_tasks and think_tasks[agent_id].done():
                            try:
                                message = await think_tasks[agent_id]
                                if message and self._running:
                                    logger.info(f"(_run_agents) Broadcasting message from agent {agent.name}")
                                    await self.broadcast(WebSocketMessage(
                                        type="message",
                                        data=message.dict()
                                    ))
                            except Exception as e:
                                logger.error(f"Error handling task result for agent {agent.name}: {e}")

                # Update states periodically
                if current_time - last_state_update >= STATE_UPDATE_INTERVAL:
                    if self._running:
                        logger.debug("(_run_agents) Broadcasting state update")
                        await self.broadcast_state()
                        last_state_update = current_time

                # Small sleep to prevent CPU overuse
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in agent processing loop: {e}")
                await asyncio.sleep(1)  # Wait longer on error

    async def _process_agent_messages(self, agent: BaseAgent):
        """Process messages for a single agent."""
        try:
            # Get the message iterator
            message_iterator = agent.run()
            
            # Process messages until we get None or StopAsyncIteration
            try:
                async for message in message_iterator:
                    if message and self._running:
                        return message  # Return the first message we get
                    await asyncio.sleep(0.1)  # Small sleep to prevent CPU overuse
                    
            except StopAsyncIteration:
                logger.debug(f"No more messages from agent {agent.name}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing messages for agent {agent.name}: {e}")
            return None

# Create a singleton instance
agent_server = AgentServer() 