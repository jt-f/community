from typing import Dict, Set
import asyncio
import zmq.asyncio
from agent import Agent
import logging
from dataclasses import asdict
import os
from dotenv import load_dotenv
from message import Message
from fastapi import WebSocket
from datetime import datetime
from population import create_test_agents

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

class Community:
    def __init__(self, name: str = "Main Community"):
        self.name = name
        #self.agents: Dict[str, Agent] = {}
        self.context = zmq.asyncio.Context()
        self.running = False
        self.active_connections: Set[WebSocket] = set()
        self.agents = create_test_agents()
        logger.debug(f"Community '{name}' initialized")
        
    def reset_state(self):
        """Reset all state to initial values"""
        self.active_connections = set()
        self.running = False
        logger.debug("Community state reset")

    async def connect(self, websocket: WebSocket):
        """Handle new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.debug(f"Client connected. Total connections: {len(self.active_connections)}")
        
        # Send current state to the new client
        try:
            current_state = {
                "type": "state_update",
                "data": {
                    agent.id: {
                        "id": agent.id,
                        "name": agent.name,
                        "status": agent.status,
                        "queue_size": len(agent.message_queue),
                        "capabilities": agent.capabilities,
                        "last_activity": agent.last_activity.isoformat()
                    }
                    for agent in self.agents
                }
            }
            logger.debug(f"Sending current state to new client: {current_state}")
            await websocket.send_json(current_state)
        except Exception as e:
            logger.error(f"Error sending current state: {e}")
            await self.disconnect(websocket)

    async def disconnect(self, websocket: WebSocket):
        """Safely disconnect a WebSocket connection"""
        try:
            if websocket in self.active_connections:
                # First remove from active connections to prevent any new messages
                self.active_connections.remove(websocket)
                logger.debug(f"Removed connection from active set. Total connections: {len(self.active_connections)}")
                
                try:
                    # Check if the connection is already closed
                    if not websocket.client_state.DISCONNECTED:
                        await websocket.close()
                        logger.debug("WebSocket closed successfully")
                except RuntimeError as e:
                    # Ignore "already closed" errors as they're expected in some cases
                    if "already completed" not in str(e) and "close message has been sent" not in str(e):
                        logger.error(f"Error closing websocket: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error closing websocket: {e}")
                
                # If this was the last connection, reset the state
                if not self.active_connections:
                    self.reset_state()
                    logger.debug("Last client disconnected, state reset")
        except Exception as e:
            logger.error(f"Error during disconnect cleanup: {e}")
            # Ensure connection is removed even if there's an error
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        
    def register_agent(self, agent: Agent):
        """Register an agent with the community"""
        self.agents[agent.id] = agent
        logger.debug(f"Registered agent {agent.name}")
        
    def unregister_agent(self, agent: Agent):
        """Unregister an agent from the community"""
        if agent.id in self.agents:
            del self.agents[agent.id]
            logger.debug(f"Unregistered agent {agent.name}")
            
    async def start(self):
        """Start the community and its message loop"""
        self.running = True
        logger.debug("Community started")
        # Start the message loop as a background task
        asyncio.create_task(self.message_loop())
        logger.debug("Message loop started as background task")
            
    async def stop(self):
        """Stop the community and clean up resources"""
        logger.info("Stopping community...")
        self.running = False
        
        # Close all active connections
        for connection in list(self.active_connections):
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        
        self.active_connections.clear()
        logger.info("Community stopped successfully")

    async def send_state_update(self):
        # Send state update to all clients
        await self.broadcast_to_clients({
            "type": "state_update",
            "data": {
                agent.id: {
                    "id": agent.id,
                    "name": agent.name,
                    "status": agent.status,
                    "queue_size": len(agent.message_queue),
                    "capabilities": agent.capabilities,
                    "last_activity": agent.last_activity.isoformat()
                }
                for agent in self.agents
            }
        })     

    async def message_loop(self):
        """Main message processing loop"""
        logger.info("Starting message loop")
        try:
            while self.running:
                for agent in self.agents:
                    if not self.running:  # Check if we should stop
                        break
                        
                    logger.debug(f"Processing agent {agent.name}")
                    # Process messages in agent's queue
                    if agent.message_queue:
                        message = agent.message_queue.pop(0)
                        logger.debug(f"Processing message from queue: {message.content}")
                        response = await agent.process_message(message)
                        if response:
                            await self.route_message(response)
                    
                    # Allow agent to think and generate messages
                    thought = await agent.think()
                    if thought:
                        await self.route_message(thought)
                
                # Send state update if we're still running
                if self.running:
                    await self.send_state_update()
                    await asyncio.sleep(3)
                
        except asyncio.CancelledError:
            logger.info("Message loop cancelled")
        except Exception as e:
            logger.error(f"Error in message loop: {e}")
        finally:
            logger.info("Message loop stopped")

    async def broadcast_to_clients(self, message: dict):
        """Broadcast a message to all connected WebSocket clients"""
        logger.info(f"Broadcasting '{message['type']}' message to {len(self.active_connections)} clients")
        # Make a copy of connections to safely iterate
        current_connections = self.active_connections.copy()
        dead_connections = set()
        
        # Send updates to WebSocket clients
        for connection in current_connections:
            try:
                if connection in self.active_connections:  # Double check connection is still active
                    await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending updates: {e}")
                dead_connections.add(connection)
                
        # Clean up dead connections
        for dead_conn in dead_connections:
            await self.disconnect(dead_conn)

    async def route_message(self, message: Dict):
        """Route a message to its intended recipient(s)"""
        # Convert dict to Message object if needed
        if isinstance(message, dict):
            message = Message.from_dict(message)
        
        logger.info(f"Routing message: {message}")
        
        # First broadcast the message to all WebSocket clients
        await self.broadcast_to_clients({
            "type": "message",
            "data": message.to_dict()
        })
        
        if message.recipient_id:
            # Direct message to specific agent
            recipient_id = message.recipient_id
            logger.debug(f"Directing message to agent {recipient_id}")
            target_agent = next((a for a in self.agents if a.id == recipient_id), None)
            if target_agent:
                logger.debug(f"Adding message to agent {target_agent.name} queue")
                target_agent.add_to_queue(message)
            else:
                logger.error(f"Agent {recipient_id} not found")
        else:
            # Broadcast message to all agents
            logger.debug(f"Broadcasting message to {len(self.agents)} agents")
            for agent in self.agents:
                if 'system' not in agent.capabilities:
                    logger.debug(f"Adding message to agent {agent.name} queue")
                    agent.add_to_queue(message)
                else:
                    logger.debug(f"Agent {agent.name} is a system agent, skipping")

        await self.send_state_update()