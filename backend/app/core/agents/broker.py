"""
Message Broker agent implementation.

This agent is responsible for routing messages between agents based on LLM analysis 
of the message content and determining the most appropriate recipient.
"""
from typing import AsyncGenerator, ClassVar, List, Dict, Any, Optional
import asyncio
from datetime import datetime
import random

from ..models import Message, WebSocketMessage
from .base import BaseAgent
from ...utils.logger import get_logger
from ...utils.message_utils import truncate_message
from ...utils.model_client import model_client, ModelProvider, GenerationParameters

# Import broker config
from .config import BROKER_CONFIG

logger = get_logger(__name__)

class MessageBrokerAgent(BaseAgent):
    """
    Message broker agent that routes messages between other agents.
    This agent handles the core communication logic of the system.
    """
    
    name: ClassVar[str] = "Message Broker"
    agent_type: ClassVar[str] = "broker"
    description: ClassVar[str] = "Routes messages between agents and manages communication"
    capabilities: ClassVar[List[str]] = [
        "message_routing",
        "broadcast_management",
        "delivery_confirmation",
        "message_filtering"
    ]
    
    def __init__(self, name: str = "Message Broker", think_interval: float = 30.0):
        """Initialize the message broker agent."""
        super().__init__(name=name, think_interval=think_interval)
        self.routing_table = {}  # Maps agent IDs to their last known status
        self.message_counter = 0
        self.last_activity_map = {}  # Maps agent IDs to their last activity time
        self.message_history = {}  # Track message chains by message ID
        self.default_model = BROKER_CONFIG.get("model", "mistral-large-latest")
        self.model_provider = ModelProvider(BROKER_CONFIG.get("provider", "mistral"))
        self.default_parameters = GenerationParameters(
            temperature=BROKER_CONFIG.get("temperature", 0.3),
            top_p=0.95,
            max_tokens=300,
            provider=self.model_provider
        )
        self.prompts = BROKER_CONFIG.get("prompts", {})
        self.last_status_update = 0  # Track last status update time
        self.status_update_interval = 180  # 3 minutes in seconds
    
    async def process_message(self, message: Message) -> AsyncGenerator[Message, None]:
        """
        Process an incoming message and route it to the appropriate recipient(s).
        If the receiver_id is 'broadcast', the message is sent to all available agents.
        """
        self.message_counter += 1
        receiver_id = message.receiver_id
        sender_id = message.sender_id
        
        # Update the last activity timestamp for the sender
        self.last_activity_map[sender_id] = datetime.now().isoformat()
        
        # Skip processing if we're the sender to avoid recursive loops
        if sender_id == self.agent_id:
            logger.debug(f"Broker skipping message from itself: {message.message_id}")
            return
        
        # If this is a broadcast message, route it to all agents except the sender
        if receiver_id == "broadcast":
            logger.debug(f"Broker handling broadcast message from {sender_id}")
            
            # Get all available agents from the agent server
            if self.agent_server and self.agent_server.agents:
                for agent_id, agent in self.agent_server.agents.items():
                    # Don't send broadcast back to sender
                    if agent_id != sender_id and agent_id != self.agent_id:
                        # Create a copy of the message with the specific agent as receiver
                        routed_message = Message(
                            message_id=message.message_id,
                            sender_id=sender_id,
                            receiver_id=agent_id,
                            content=message.content,
                            timestamp=message.timestamp,
                            message_type=message.message_type,
                            reply_to_id=message.reply_to_id
                        )
                        
                        # Add message to the agent's queue
                        logger.debug(f"Broker routing broadcast message to {agent_id}")
                        await agent.add_message(routed_message)
                        
                        # Update the last activity timestamp for the receiver
                        self.last_activity_map[agent_id] = datetime.now().isoformat()
        
        # If this is a direct message, route it to the specific recipient
        elif receiver_id in self.agent_server.agents:
            logger.debug(f"Broker routing message from {sender_id} to {receiver_id}")
            recipient = self.agent_server.agents[receiver_id]
            
            # Add message to the recipient's queue
            await recipient.add_message(message)
            
            # Update the last activity timestamp for the receiver
            self.last_activity_map[receiver_id] = datetime.now().isoformat()
            
            # Send confirmation message back to the sender
            confirmation = Message(
                sender_id=self.agent_id,
                receiver_id=sender_id,
                content={"text": f"Message delivered to {receiver_id}", "type": "delivery_confirmation"},
                message_type="confirmation",
                reply_to_id=message.message_id
            )
            
            yield confirmation
        
        # If the recipient doesn't exist, send an error message back to the sender
        else:
            logger.warning(f"Broker could not find recipient {receiver_id} for message from {sender_id}")
            
            error_message = Message(
                sender_id=self.agent_id,
                receiver_id=sender_id,
                content={"text": f"Error: Recipient {receiver_id} not found", "type": "delivery_error"},
                message_type="error",
                reply_to_id=message.message_id
            )
            
            yield error_message
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """
        Periodically check the health of all agents and update the routing table.
        This method is required by the BaseAgent abstract class.
        """
        while True:
            if await self._should_think():
                # Update the routing table with the current status of all agents
                if self.agent_server and self.agent_server.agents:
                    current_time = datetime.now().timestamp()
                    active_agents = 0
                    
                    for agent_id, agent in self.agent_server.agents.items():
                        if agent_id == self.agent_id:
                            continue  # Skip self
                        
                        # Update the routing table with the agent's state
                        self.routing_table[agent_id] = {
                            "id": agent_id,
                            "name": agent.name,
                            "status": agent._state.status,
                            "last_activity": self.last_activity_map.get(agent_id, "unknown")
                        }
                        
                        if agent._state.status != "idle":
                            active_agents += 1
                    
                    # Send status update every 3 minutes
                    if current_time - self.last_status_update >= self.status_update_interval:
                        status_message = f"System status: {len(self.routing_table)} registered agents, {active_agents} active"
                        
                        yield Message(
                            sender_id=self.agent_id,
                            receiver_id="broadcast",
                            content={
                                "text": status_message,
                                "data": {
                                    "agent_count": len(self.routing_table),
                                    "active_count": active_agents,
                                    "message_count": self.message_counter
                                },
                                "type": "system_status"
                            },
                            message_type="status"
                        )
                        self.last_status_update = current_time
                
                # Update last think time
                self.last_think_time = datetime.now().timestamp()
            
            # Sleep to avoid busy waiting
            await asyncio.sleep(10)
    
    async def route_message_chain(self, original_message: Message, response_message: Message, original_sender_id: str = None) -> str:
        """
        Analyze a message and its response, and determine where to route it next.
        
        This is the main public method to be called by other components when they
        need to route a message. The broker is solely responsible for determining
        the receiver_id, but it does NOT modify the message directly. Instead, it
        returns the ID, and the caller is responsible for creating a new message
        with the appropriate receiver_id.
        
        Args:
            original_message: The message sent to an agent
            response_message: The response produced by that agent
            original_sender_id: ID of the original sender that triggered this conversation
            
        Returns:
            The agent ID to route the message to next
        """
        sender_id = None
        if hasattr(response_message, 'sender_id'):
            sender_id = response_message.sender_id 
        elif isinstance(response_message, dict) and 'sender_id' in response_message:
            sender_id = response_message['sender_id']
        
        agent_name = self.agent_server.agents[sender_id].name
        logger.info(f"Broker will determine next receiver for message from {agent_name}")
        return await self._determine_next_agent(original_message, response_message, original_sender_id)
    
    async def _determine_next_agent(self, original_message: Any, response_message: Any, original_sender_id: str = None) -> str:
        """
        Use LLM reasoning to determine which agent should receive the message next.
        
        Args:
            original_message: The original message (can be dict or Message object)
            response_message: The response message (can be dict or Message object)
            original_sender_id: ID of the original sender that triggered this conversation
            
        Returns:
            The agent ID to route the message to
        """
        # Check if this is a new conversation (original & response are the same)
        is_new_conversation = False
        
        # Extract IDs for logging purposes
        original_id = original_message.message_id if hasattr(original_message, 'message_id') else None
        if not original_id and isinstance(original_message, dict):
            original_id = original_message.get("message_id", "unknown")
            
        response_id = response_message.message_id if hasattr(response_message, 'message_id') else None
        if not response_id and isinstance(response_message, dict):
            response_id = response_message.get("message_id", "unknown")
        
        if original_id and response_id and original_id == response_id:
            is_new_conversation = True
            logger.info("Detected new conversation - same message used as original and response")
        
        # Extract message content
        original_content = self._extract_message_content(original_message)
        response_content = self._extract_message_content(response_message)
        
        # Get message senders if available
        original_sender = self._extract_sender(original_message)
        # If original_sender_id is provided as a parameter, prioritize it
        if original_sender_id:
            original_sender = original_sender_id
            logger.debug(f"Using provided original_sender_id: {original_sender_id}")
            
        response_sender = self._extract_sender(response_message)
        
        # Get a list of available agents from the server
        available_agents = []
        original_sender_agent = None
        
        if self.agent_server and hasattr(self.agent_server, "agents"):
            for agent_id, agent in self.agent_server.agents.items():
                # Skip the broker itself
                if agent_id == self.agent_id:
                    continue
                
                # Skip the sender of the response (don't route back to same agent)
                if agent_id == response_sender:
                    logger.debug(f"Skipping {agent_id} as it's the sender of the response")
                    continue
                
                # For new conversations from humans, prioritize intelligent agents
                if is_new_conversation and original_sender:
                    sender_agent = self.agent_server.agents.get(original_sender)
                    if sender_agent and sender_agent.state.type.lower() == 'human':
                        # Skip routing new human messages to other humans or system agents
                        if agent.state.type.lower() in ['human', 'system']:
                            logger.debug(f"Skipping {agent_id} for new human conversation as it's a {agent.state.type}")
                            continue
                
                # Track if this agent is the original sender
                if agent_id == original_sender:
                    original_sender_agent = {
                        "id": agent_id,
                        "name": agent.name,
                        "type": agent.state.type,
                        "capabilities": agent.state.capabilities if hasattr(agent.state, "capabilities") else [],
                        "is_original_sender": True
                    }
                    logger.debug(f"Found original sender agent: {agent_id}")
                else:
                    available_agents.append({
                        "id": agent_id,
                        "name": agent.name,
                        "type": agent.state.type,
                        "capabilities": agent.state.capabilities if hasattr(agent.state, "capabilities") else [],
                        "is_original_sender": False
                    })
        
        # Add the original sender as the first in the list if found
        if original_sender_agent:
            available_agents.insert(0, original_sender_agent)
            
        # If no available agents, return empty string
        if not available_agents:
            logger.warning("No available agents to route to")
            return ""
        
        # For new conversations, we can use a simplified routing strategy
        if is_new_conversation:
            prompt = self._format_new_conversation_prompt(original_content, available_agents)
        else:
            # Format the regular routing prompt
            prompt = self._format_routing_prompt(original_content, response_content, available_agents, original_sender)
        
        # Generate the routing decision using the LLM
        routing_decision = await self._generate_routing_decision(prompt)
        logger.info(f"Routing decision: {routing_decision}")
        
        # Parse the routing decision to extract the agent ID
        next_agent_id = self._parse_routing_decision(routing_decision, available_agents)
        
        logger.debug(f"Final routing decision: {next_agent_id}")
        return next_agent_id
    
    async def _generate_routing_decision(self, prompt: str) -> str:
        """Generate a routing decision using the LLM."""
        logger.info(f"Generating routing decision on behalf of {self.name}")

        # Use the model client with the specified provider
        async with model_client as client:
            return await client.generate(
                prompt=prompt, 
                model=self.default_model, 
                parameters=self.default_parameters
            )
    
    def _extract_message_content(self, message: Any) -> str:
        """Extract content from a message object or dictionary."""
        if message is None:
            return ""
            
        try:
            # If it's a Message object
            if hasattr(message, "content"):
                content = message.content
                if isinstance(content, dict) and "text" in content:
                    return content["text"]
                elif isinstance(content, str):
                    return content
                else:
                    return str(content)
            
            # If it's a dictionary
            elif isinstance(message, dict):
                if "content" in message:
                    content = message["content"]
                    if isinstance(content, dict) and "text" in content:
                        return content["text"]
                    elif isinstance(content, str):
                        return content
                    else:
                        return str(content)
                elif "text" in message:
                    return message["text"]
                else:
                    return str(message)
            
            # Fallback
            return str(message)
        except Exception as e:
            logger.error(f"Error extracting message content: {e}", exc_info=True)
            return str(message)
    
    def _format_routing_prompt(self, original_content: str, response_content: str, available_agents: List[Dict], original_sender: str = None) -> str:
        """Format the routing prompt for the LLM."""
        agents_info = "\n".join([
            f"- {agent['name']} (ID: {agent['id']}): Type: {agent['type']}, Capabilities: {', '.join(agent['capabilities'])}" +
            (" (ORIGINAL SENDER)" if agent.get('is_original_sender', False) else "")
            for agent in available_agents
        ])
        
        # Add context about original sender if available
        original_sender_context = ""
        if original_sender:
            original_sender_context = f"\nORIGINAL SENDER: {original_sender}\n"
            original_sender_context += "NOTE: The original sender is often a good candidate to route responses back to, unless there is a clearly better choice based on the message content."
        
        # Use the routing prompt from config if available
        prompt_template = self.prompts.get("routing", """Error: No routing prompt found in config""")
        
        # Format the prompt with the message content and agents info
        return prompt_template.format(
            original_message=original_content,
            response_message=response_content,
            agents_info=agents_info + original_sender_context
        )
    
    def _parse_routing_decision(self, decision: str, available_agents: List[Dict]) -> str:
        """
        Parse the LLM's routing decision to extract the agent ID.
        If no valid agent ID is found, return the first available agent ID as a fallback.
        """

        try:
            # Try to extract the agent ID using a simple parsing approach
            lines = decision.strip().split("\n")
            for line in lines:
                if line.strip().startswith("SELECTED AGENT ID:"):
                    agent_id = line.split("SELECTED AGENT ID:")[1].strip()
                    # Remove any quotes or extra characters
                    agent_id = agent_id.strip('"\'[]() ')
                    
                    # Verify this is a valid agent ID
                    if any(agent["id"] == agent_id for agent in available_agents):
                        return agent_id
            
            # If we couldn't find a valid agent ID, log a warning and use the first available agent
            logger.warning(f"Could not parse valid agent ID from LLM response: {decision}")
            if available_agents:
                return available_agents[0]["id"]
            else:
                logger.error("No available agents to route to")
                return ""
                
        except Exception as e:
            logger.error(f"Error parsing routing decision: {e}", exc_info=True)
            # Fallback to the first available agent
            if available_agents:
                return available_agents[0]["id"]
            else:
                return ""
    
    def _extract_sender(self, message: Any) -> str:
        """Extract the sender ID from a message object or dictionary."""
        if message is None:
            return None
            
        try:
            # If it's a Message object
            if hasattr(message, "sender_id"):
                return message.sender_id
            
            # If it's a dictionary
            elif isinstance(message, dict) and "sender_id" in message:
                return message["sender_id"]
            
            # Fallback
            return None
        except Exception as e:
            logger.error(f"Error extracting sender: {e}", exc_info=True)
            return None
            
    def _format_new_conversation_prompt(self, message_content: str, available_agents: List[Dict]) -> str:
        """Format a prompt for routing a new conversation (initial message)."""
        agents_info = "\n".join([
            f"- {agent['name']} (ID: {agent['id']}): Type: {agent['type']}, Capabilities: {', '.join(agent['capabilities'])}"
            for agent in available_agents
        ])
        
        # Use a simplified prompt for new conversations
        prompt_template = self.prompts.get("new_conversation", """Generate an error message""")
        
        # Format the prompt with the message content and agents info
        return prompt_template.format(
            original_message=message_content,
            agents_info=agents_info
        )
    
    async def _should_think(self) -> bool:
        """Check if it's time to think."""
        current_time = datetime.now().timestamp()
        return current_time - self.last_think_time >= self.think_interval
    
    async def _think(self) -> AsyncGenerator[Message, None]:
        """
        Periodically check the health of all agents and update the routing table.
        """
        if self.message_queue.empty():
            self.last_think_time = datetime.now().timestamp()
            
            # Update the routing table with the current status of all agents
            if self.agent_server and self.agent_server.agents:
                current_time = datetime.now().isoformat()
                active_agents = 0
                
                for agent_id, agent in self.agent_server.agents.items():
                    if agent_id == self.agent_id:
                        continue  # Skip self
                    
                    # Update the routing table with the agent's state
                    self.routing_table[agent_id] = {
                        "id": agent_id,
                        "name": agent.name,
                        "status": agent._state.status,
                        "last_activity": self.last_activity_map.get(agent_id, "unknown")
                    }
                    
                    if agent._state.status != "idle":
                        active_agents += 1
                
                # Occasionally send a status update to all agents
                if random.random() < 0.2:  # 20% chance on each think cycle
                    status_message = f"System status: {len(self.routing_table)} registered agents, {active_agents} active"
                    
                    yield Message(
                        sender_id=self.agent_id,
                        receiver_id="broadcast",
                        content={
                            "text": status_message,
                            "data": {
                                "agent_count": len(self.routing_table),
                                "active_count": active_agents,
                                "message_count": self.message_counter
                            },
                            "type": "system_status"
                        },
                        message_type="status"
                    )
    
    async def route_message_chain(self, original_message: Message, response_message: Message, original_sender_id: str = None) -> str:
        """
        Analyze a message and its response, and determine where to route it next.
        
        This is the main public method to be called by other components when they
        need to route a message. The broker is solely responsible for determining
        the receiver_id, but it does NOT modify the message directly. Instead, it
        returns the ID, and the caller is responsible for creating a new message
        with the appropriate receiver_id.
        
        Args:
            original_message: The message sent to an agent
            response_message: The response produced by that agent
            original_sender_id: ID of the original sender that triggered this conversation
            
        Returns:
            The agent ID to route the message to next
        """
        sender_id = None
        if hasattr(response_message, 'sender_id'):
            sender_id = response_message.sender_id 
        elif isinstance(response_message, dict) and 'sender_id' in response_message:
            sender_id = response_message['sender_id']
        
        agent_name = self.agent_server.agents[sender_id].name
        logger.info(f"Broker will determine next receiver for message from {agent_name}")
        return await self._determine_next_agent(original_message, response_message, original_sender_id)
    
    async def _determine_next_agent(self, original_message: Any, response_message: Any, original_sender_id: str = None) -> str:
        """
        Use LLM reasoning to determine which agent should receive the message next.
        
        Args:
            original_message: The original message (can be dict or Message object)
            response_message: The response message (can be dict or Message object)
            original_sender_id: ID of the original sender that triggered this conversation
            
        Returns:
            The agent ID to route the message to
        """
        # Check if this is a new conversation (original & response are the same)
        is_new_conversation = False
        
        # Extract IDs for logging purposes
        original_id = original_message.message_id if hasattr(original_message, 'message_id') else None
        if not original_id and isinstance(original_message, dict):
            original_id = original_message.get("message_id", "unknown")
            
        response_id = response_message.message_id if hasattr(response_message, 'message_id') else None
        if not response_id and isinstance(response_message, dict):
            response_id = response_message.get("message_id", "unknown")
        
        if original_id and response_id and original_id == response_id:
            is_new_conversation = True
            logger.info("Detected new conversation - same message used as original and response")
        
        # Extract message content
        original_content = self._extract_message_content(original_message)
        response_content = self._extract_message_content(response_message)
        
        # Get message senders if available
        original_sender = self._extract_sender(original_message)
        # If original_sender_id is provided as a parameter, prioritize it
        if original_sender_id:
            original_sender = original_sender_id
            logger.debug(f"Using provided original_sender_id: {original_sender_id}")
            
        response_sender = self._extract_sender(response_message)
        
        # Get a list of available agents from the server
        available_agents = []
        original_sender_agent = None
        
        if self.agent_server and hasattr(self.agent_server, "agents"):
            for agent_id, agent in self.agent_server.agents.items():
                # Skip the broker itself
                if agent_id == self.agent_id:
                    continue
                
                # Skip the sender of the response (don't route back to same agent)
                if agent_id == response_sender:
                    logger.debug(f"Skipping {agent_id} as it's the sender of the response")
                    continue
                
                # For new conversations from humans, prioritize intelligent agents
                if is_new_conversation and original_sender:
                    sender_agent = self.agent_server.agents.get(original_sender)
                    if sender_agent and sender_agent.state.type.lower() == 'human':
                        # Skip routing new human messages to other humans or system agents
                        if agent.state.type.lower() in ['human', 'system']:
                            logger.debug(f"Skipping {agent_id} for new human conversation as it's a {agent.state.type}")
                            continue
                
                # Track if this agent is the original sender
                if agent_id == original_sender:
                    original_sender_agent = {
                        "id": agent_id,
                        "name": agent.name,
                        "type": agent.state.type,
                        "capabilities": agent.state.capabilities if hasattr(agent.state, "capabilities") else [],
                        "is_original_sender": True
                    }
                    logger.debug(f"Found original sender agent: {agent_id}")
                else:
                    available_agents.append({
                        "id": agent_id,
                        "name": agent.name,
                        "type": agent.state.type,
                        "capabilities": agent.state.capabilities if hasattr(agent.state, "capabilities") else [],
                        "is_original_sender": False
                    })
        
        # Add the original sender as the first in the list if found
        if original_sender_agent:
            available_agents.insert(0, original_sender_agent)
            
        # If no available agents, return empty string
        if not available_agents:
            logger.warning("No available agents to route to")
            return ""
        
        # For new conversations, we can use a simplified routing strategy
        if is_new_conversation:
            prompt = self._format_new_conversation_prompt(original_content, available_agents)
        else:
            # Format the regular routing prompt
            prompt = self._format_routing_prompt(original_content, response_content, available_agents, original_sender)
        
        # Generate the routing decision using the LLM
        routing_decision = await self._generate_routing_decision(prompt)
        logger.info(f"Routing decision: {routing_decision}")
        
        # Parse the routing decision to extract the agent ID
        next_agent_id = self._parse_routing_decision(routing_decision, available_agents)
        
        logger.debug(f"Final routing decision: {next_agent_id}")
        return next_agent_id
    
    async def _generate_routing_decision(self, prompt: str) -> str:
        """Generate a routing decision using the LLM."""
        logger.info(f"Generating routing decision on behalf of {self.name}")

        # Use the model client with the specified provider
        async with model_client as client:
            return await client.generate(
                prompt=prompt, 
                model=self.default_model, 
                parameters=self.default_parameters
            )
    
    def _extract_message_content(self, message: Any) -> str:
        """Extract content from a message object or dictionary."""
        if message is None:
            return ""
            
        try:
            # If it's a Message object
            if hasattr(message, "content"):
                content = message.content
                if isinstance(content, dict) and "text" in content:
                    return content["text"]
                elif isinstance(content, str):
                    return content
                else:
                    return str(content)
            
            # If it's a dictionary
            elif isinstance(message, dict):
                if "content" in message:
                    content = message["content"]
                    if isinstance(content, dict) and "text" in content:
                        return content["text"]
                    elif isinstance(content, str):
                        return content
                    else:
                        return str(content)
                elif "text" in message:
                    return message["text"]
                else:
                    return str(message)
            
            # Fallback
            return str(message)
        except Exception as e:
            logger.error(f"Error extracting message content: {e}", exc_info=True)
            return str(message)
    
    def _format_routing_prompt(self, original_content: str, response_content: str, available_agents: List[Dict], original_sender: str = None) -> str:
        """Format the routing prompt for the LLM."""
        agents_info = "\n".join([
            f"- {agent['name']} (ID: {agent['id']}): Type: {agent['type']}, Capabilities: {', '.join(agent['capabilities'])}" +
            (" (ORIGINAL SENDER)" if agent.get('is_original_sender', False) else "")
            for agent in available_agents
        ])
        
        # Add context about original sender if available
        original_sender_context = ""
        if original_sender:
            original_sender_context = f"\nORIGINAL SENDER: {original_sender}\n"
            original_sender_context += "NOTE: The original sender is often a good candidate to route responses back to, unless there is a clearly better choice based on the message content."
        
        # Use the routing prompt from config if available
        prompt_template = self.prompts.get("routing", """Error: No routing prompt found in config""")
        
        # Format the prompt with the message content and agents info
        return prompt_template.format(
            original_message=original_content,
            response_message=response_content,
            agents_info=agents_info + original_sender_context
        )
    
    def _parse_routing_decision(self, decision: str, available_agents: List[Dict]) -> str:
        """
        Parse the LLM's routing decision to extract the agent ID.
        If no valid agent ID is found, return the first available agent ID as a fallback.
        """

        try:
            # Try to extract the agent ID using a simple parsing approach
            lines = decision.strip().split("\n")
            for line in lines:
                if line.strip().startswith("SELECTED AGENT ID:"):
                    agent_id = line.split("SELECTED AGENT ID:")[1].strip()
                    # Remove any quotes or extra characters
                    agent_id = agent_id.strip('"\'[]() ')
                    
                    # Verify this is a valid agent ID
                    if any(agent["id"] == agent_id for agent in available_agents):
                        return agent_id
            
            # If we couldn't find a valid agent ID, log a warning and use the first available agent
            logger.warning(f"Could not parse valid agent ID from LLM response: {decision}")
            if available_agents:
                return available_agents[0]["id"]
            else:
                logger.error("No available agents to route to")
                return ""
                
        except Exception as e:
            logger.error(f"Error parsing routing decision: {e}", exc_info=True)
            # Fallback to the first available agent
            if available_agents:
                return available_agents[0]["id"]
            else:
                return ""
    
    def _extract_sender(self, message: Any) -> str:
        """Extract the sender ID from a message object or dictionary."""
        if message is None:
            return None
            
        try:
            # If it's a Message object
            if hasattr(message, "sender_id"):
                return message.sender_id
            
            # If it's a dictionary
            elif isinstance(message, dict) and "sender_id" in message:
                return message["sender_id"]
            
            # Fallback
            return None
        except Exception as e:
            logger.error(f"Error extracting sender: {e}", exc_info=True)
            return None
            
    def _format_new_conversation_prompt(self, message_content: str, available_agents: List[Dict]) -> str:
        """Format a prompt for routing a new conversation (initial message)."""
        agents_info = "\n".join([
            f"- {agent['name']} (ID: {agent['id']}): Type: {agent['type']}, Capabilities: {', '.join(agent['capabilities'])}"
            for agent in available_agents
        ])
        
        # Use a simplified prompt for new conversations
        prompt_template = self.prompts.get("new_conversation", """Generate an error message""")
        
        # Format the prompt with the message content and agents info
        return prompt_template.format(
            original_message=message_content,
            agents_info=agents_info
        )
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Message broker agents do not think autonomously."""
        yield None 