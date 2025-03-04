import asyncio
import time
from collections import deque
from typing import Set, Optional, Dict, Any
from app.core.models import Message, WebSocketMessage
from app.core.agents.base import BaseAgent
from ..utils.logger import get_logger

logger = get_logger(__name__)

class AgentManager:
    def __init__(self):
        self.available_agents = deque()  # Use deque for O(1) append/popleft
        self.busy_agents = set()
        self.running = False
        self.max_concurrent_tasks = 100
        self.server = None  # Will be set by the server
        
    def set_server(self, server):
        """Set the agent server reference."""
        self.server = server
        
    def register_agent(self, agent: BaseAgent):
        """Register a new agent with the manager."""
        # Set the agent_server reference in the agent
        agent.agent_server = self.server
        self.available_agents.append(agent)
        
    def unregister_agent(self, agent: BaseAgent):
        """Unregister an agent from the manager."""
        if agent in self.available_agents:
            self.available_agents.remove(agent)
        if agent in self.busy_agents:
            self.busy_agents.remove(agent)
            
    async def run(self):
        """Main loop that processes available agents."""
        self.running = True
        pending_tasks = set()
        
        while self.running:
            # Process any available agents
            while self.available_agents and len(pending_tasks) < self.max_concurrent_tasks:
                agent = self.available_agents.popleft()
                self.busy_agents.add(agent)
                
                # Create and track the task
                task = asyncio.create_task(self._process_agent(agent))
                pending_tasks.add(task)
                # Use a lambda that captures the task to remove it when done
                task.add_done_callback(lambda t=task: pending_tasks.discard(t))
            
            # If no agents are available, wait a bit
            if not self.available_agents and not pending_tasks:
                await asyncio.sleep(0.1)
                continue
                
            # Wait for at least one task to complete if we have no available agents
            if not self.available_agents and pending_tasks:
                done, _ = await asyncio.wait(
                    pending_tasks, 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Handle any exceptions from completed tasks
                for task in done:
                    try:
                        await task
                    except Exception as e:
                        print(f"Error in agent task: {e}")
    
    async def _process_agent(self, agent: BaseAgent):
        """Process a single agent and return it to the available queue when done."""
        try:
            # Process messages
            message = await agent.get_next_message()
            if message:
                logger.info(f"Agent {agent.name} processing message: {message.content}")
                message_response = await agent.process_message(message)
                logger.info(f"Agent {agent.name} has processed message")
                
                if message_response and self.server:
                    logger.info(f"Agent {agent.name} has a message response")
                    logger.info(f"Message response: {message_response}")
                    
                    # Route the message to the appropriate agent
                    if message_response.receiver_id:
                        logger.info(f"Routing response from {agent.name} to {message_response.receiver_id}")
                        await self.server.route_message(message_response)
                    
                    # Broadcast the message to all WebSocket clients
                    await self.server.broadcast(WebSocketMessage(
                        type="message",
                        data=message_response.dict()
                    ))
            
            # Run thinking cycle if needed
            if agent.should_think():
                logger.info(f"Agent {agent.name} should think")
                logger.info(f"Agent {agent.name} is thinking")
                thought = await agent.think_once()
                logger.info(f"Agent {agent.name} has thought")
                
                if thought and self.server:
                    logger.info(f"Agent {agent.name} has generated a thought: {thought}")
                    
                    # Route the thought if it has a receiver
                    if thought.receiver_id:
                        logger.info(f"Routing thought from {agent.name} to {thought.receiver_id}")
                        await self.server.route_message(thought)
                    
                    # Broadcast the thought to all WebSocket clients
                    await self.server.broadcast(WebSocketMessage(
                        type="message",
                        data=thought.dict()
                    ))
            
            # Return agent to available pool
            self.busy_agents.remove(agent)
            self.available_agents.append(agent)
        except Exception as e:
            # Handle errors, log them
            logger.error(f"Error processing agent {agent.agent_id}: {e}", exc_info=True)
            self.busy_agents.remove(agent)
            # Add back to available after a short delay
            await asyncio.sleep(1)
            self.available_agents.append(agent)
            
    def stop(self):
        """Stop the agent manager."""
        self.running = False 