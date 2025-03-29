"""
Agent server implementation for managing agents and WebSocket connections.
"""
from typing import Dict, Set, Any, AsyncGenerator
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import uuid
from datetime import datetime
from collections import defaultdict

from .models import Message, WebSocketMessage
from .agents.base import BaseAgent
from .agents.system import SystemAgent
from .agents.human import HumanAgent
from .agents.analyst import AnalystAgent
from .agents.broker import MessageBrokerAgent
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
        self.message_broker = None  # Will be set during start()
        
        # Add a message history cache to track conversations
        # This is a simple in-memory store - in production this should be persisted
        self.message_history = {}  # message_id -> Message
        self.message_pairs = defaultdict(dict)  # Maps message IDs to their replies
        
    async def start(self):
        """Start the agent server."""
        if self.running:
            return
            
        self.running = True
        logger.debug("Agent server started")
        
        # Create and register the message broker agent
        if not self.message_broker:
            logger.debug("Creating message broker agent")
            self.message_broker = MessageBrokerAgent(name="Message Broker")
            await self.register_agent(self.message_broker)
            logger.debug(f"Message broker agent created with ID: {self.message_broker.agent_id}")
        
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
                logger.error(f"(server) Error processing message: {e}")
                
            # Sleep briefly to avoid busy waiting
            await asyncio.sleep(0.01)
            
    async def _handle_message(self, message: Message):
        """Handle a message."""
        # Log the message
        logger.debug(f"Handling message: {truncate_message(message)}")
        
        # Store the message in message history
        if hasattr(message, 'message_id') and message.message_id:
            self.message_history[message.message_id] = message
            
            # If this is a reply, track the relationship
            if hasattr(message, 'in_reply_to') and message.in_reply_to:
                self.message_pairs[message.in_reply_to]['response'] = message
                self.message_pairs[message.message_id]['original'] = self.message_history.get(message.in_reply_to)
        
        # Create a WebSocket message for broadcasting
        try:
            ws_message = WebSocketMessage(
                type="message",
                data={
                    "message": message.model_dump() if hasattr(message, "model_dump") else message,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Broadcast the message to all clients
            await self.broadcast_message(ws_message)
        except Exception as e:
            logger.error(f"Error broadcasting message from queue: {e}")
        
    async def route_message(self, message: Message):
        """Route a message to the appropriate agent."""
        logger.info(f"Server routing message ({message.message_id}) from <{self.agents[message.sender_id].name}>")
        
        # First, store the message in message history
        self.message_history[message.message_id] = message
        
        # If this is a reply, track the relationship
        if hasattr(message, 'in_reply_to') and message.in_reply_to:
            self.message_pairs[message.in_reply_to]['response'] = message
            if message.in_reply_to in self.message_history:
                self.message_pairs[message.message_id]['original'] = self.message_history[message.in_reply_to]
                logger.info(f"Recorded message {message.message_id} as response to {message.in_reply_to}")
            else:
                logger.warning(f"Original message {message.in_reply_to} not found in history, using placeholder")
                self.message_pairs[message.message_id]['original'] = Message(
                    message_id=message.in_reply_to,
                    sender_id="unknown",
                    content={"text": "Original message not found in history"},
                    message_type="text"
                )
    
        # Skip if message is None
        if message is None:
            logger.warning("Attempted to route None message")
            return
        
        # The message broker should handle all routing decisions
        # If this message already has an explicit receiver_id, handle direct routing
        receiver_id = None
        if hasattr(message, 'receiver_id'):
            receiver_id = message.receiver_id
        elif hasattr(message, 'receiver'):
            receiver_id = message.receiver
        
        # Check if there's a specific receiver set by the broker
        if receiver_id and receiver_id != "broadcast":
            agent_name = self.agents[receiver_id].name
            logger.info(f"Routing message to explicit receiver: {agent_name}")
            
            # Check if the receiver is a user ID
            if receiver_id.startswith("user-"):
                # Try to find a human agent for this user
                human_agent = None
                for agent_id, agent in self.agents.items():
                    if agent_id == receiver_id and isinstance(agent, HumanAgent):
                        human_agent = agent
                        break
                
                # If no human agent exists for this user, create one
                if not human_agent:
                    logger.info(f"Creating new human agent : {agent_name}({receiver_id})")
                    human_agent = HumanAgent(agent_id=receiver_id)
                    await self.register_agent(human_agent)
                
                # Route the message to the human agent
                logger.info(f"Routing message to human agent {receiver_id}")
                await human_agent.add_message(message)
                
                # Broadcast the updated state to all clients
                await self.broadcast_state()
                
                return
            
            # Try to find the agent by ID
            if receiver_id in self.agents:
                agent = self.agents[receiver_id]
                logger.info(f"Routing message to Agent {agent.name}")
                await agent.add_message(message)
                
                # Broadcast the updated state to all clients
                await self.broadcast_state()
                
                return
            else:
                logger.warning(f"No agent found for receiver {receiver_id}")
        
        # For messages without explicit receiver_id, use the message broker
        # This is the primary path where message broker decides routing
        if self.message_broker:
            logger.info(f"Using message broker to route message: '{truncate_message(message.content.get('text'))}'")
            
            # Get previous message if this is a response
            original_message = None
            
            logger.info(f"Message_id: {message.message_id}")
            logger.info(f"Message pairs: {self.message_pairs}")

            # First check our message pair tracking
            if hasattr(message, 'message_id') and message.message_id in self.message_pairs and 'original' in self.message_pairs[message.message_id]:
                original_message = self.message_pairs[message.message_id]['original']
                logger.info(f"Found original message for {message.message_id} from message pairs")
            # Then check in_reply_to
            elif hasattr(message, 'in_reply_to') and message.in_reply_to:
                logger.info(f"Message {message.message_id} is a reply to {message.in_reply_to}")
                # Check if we have the original message in our history
                if message.in_reply_to in self.message_history:
                    original_message = self.message_history[message.in_reply_to]
                    logger.info(f"Found original message in history: '{truncate_message(original_message.content.get('text'))}'")
                else:
                    # Create a placeholder - in a real implementation, you'd retrieve from a database
                    logger.warning(f"Original message {message.in_reply_to} not found in history, using placeholder")
                    original_message = Message(
                        message_id=message.in_reply_to,
                        sender_id="unknown",
                        content={"text": "Original message not found in history"},
                        message_type="text"
                    )
            
            # If we can't find an original message, it's a new conversation
            if not original_message:
                logger.info(f"Message {message.message_id} appears to be starting a new conversation")
                # This is a new conversation, let the broker decide if it should go to a specific agent
                # For now, just send the message as both original and response
                original_message = message
                logger.debug(f"Setting both original and response to the same message for new conversation")
            
            try:
                # Determine the next agent using the broker
                logger.debug(f"Asking broker to route: original={truncate_message(original_message)}, response={truncate_message(message)}")
                
                # Make sure original_sender_id is passed to the broker for consideration in routing
                original_sender_id = original_message.sender_id if hasattr(original_message, 'sender_id') else None
                logger.debug(f"Original sender ID: {original_sender_id}")
                
                next_agent_id = await self.message_broker.route_message_chain(original_message, message, original_sender_id)
                
                if next_agent_id and next_agent_id in self.agents:
                    next_agent = self.agents[next_agent_id]
                    logger.info(f"Broker routing message to {next_agent.name}")
                    
                    # Create a new message with the receiver_id set by the broker
                    routed_message = None
                    if hasattr(message, 'model_dump'):
                        message_dict = message.model_dump()
                        message_dict['receiver_id'] = next_agent_id
                        routed_message = Message(**message_dict)
                    else:
                        # For dict-like objects
                        routed_message = message.copy() if hasattr(message, 'copy') else dict(message)
                        routed_message['receiver_id'] = next_agent_id
                    
                    # Send the message to the selected agent
                    await next_agent.add_message(routed_message)
                    
                    # Broadcast the updated state
                    await self.broadcast_state()
                    return
                else:
                    logger.warning(f"Broker returned invalid agent ID: {next_agent_id}")
            except Exception as e:
                logger.error(f"Error using message broker for routing: {e}", exc_info=True)
        else:
            logger.warning("No message broker available for routing")
        
        # Then broadcast this message to all WebSocket clients
        try:
            # Create a WebSocket message from the agent message
            ws_message = WebSocketMessage(
                type="message",
                data={
                    "message": message.model_dump() if hasattr(message, "model_dump") else message,
                    "timestamp": datetime.now().isoformat()
                }
            )
            logger.info(f"Server broadcasting message to ws clients: {ws_message}")
            # Broadcast the message to all clients

            await self.broadcast_message(ws_message)
        except Exception as e:
            logger.error(f"Error broadcasting message to WebSocket clients: {e}")
        
        # If broker routing failed or no broker is available, queue for broadcast only
        logger.info("Broker routing failed or not available, queueing message for broadcasting only")
        await self.message_queue.put(message)
        
        # Broadcast the updated state to all clients
        await self.broadcast_state()

    async def broadcast_message(self, message: WebSocketMessage):
        """Broadcast a message to all connected WebSocket clients."""
        # Convert to JSON-serializable format
        if isinstance(message, dict):
            data = message
        else:
            data = message.model_dump()
            
        # Send to all connected clients
        if data['type'] == 'message':
            logger.info(f"Sending message ({data['type']}) to client: {truncate_message(data['data'].get('message', {}))}")
                
        for client in self.websocket_clients:
            try:
                await client.send_json(data)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                
    async def process_message(self, message: Message) -> AsyncGenerator[Message, None]:
        """Process an incoming message and route it to the appropriate agent."""
        logger.info(f"message ({message.message_id}) passed to agent server")
        try:
            # Get the receiver agent
            receiver_id = message.receiver_id
            receiver = self.agents.get(receiver_id)
            # Get the sender agent
            sender_id = message.sender_id
            sender = self.agents.get(sender_id)

            
            # For non-human agents, process the message normally
            if receiver:
                logger.info(f"message ({message.message_id}) passed to receiving agent {receiver.name}")
                async for response in receiver.process_message(message):
                    logger.info(f"message ({response.message_id}) generated in response to message ({message.message_id}) by {receiver.name}")
                    yield response
            else:
                logger.warning(f"Unknown receiver: {receiver_id}")
                yield Message(
                    sender_id=self.system_agent.agent_id,
                    receiver_id=message.sender_id,
                    content={"text": f"Error: Unknown receiver {receiver_id}", "type": "error"},
                    message_type="error"
                )
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            yield Message(
                sender_id=self.system_agent.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"Error processing message: {str(e)}", "type": "error"},
                message_type="error"
            )

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
                    states[agent_id] = agent.state.model_dump()
                    names[agent_id] = agent.name
                    logger.debug(f"Added state for agent {agent_id} from self.agents")
                except Exception as e:
                    logger.error(f"Error getting state for agent {agent_id}: {e}")
            
            # Then, ensure all agents from agent_manager are included
            for agent in list(available_agents) + list(thinking_agents):
                if agent.agent_id not in states:
                    try:
                        states[agent.agent_id] = agent.state.model_dump()
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
