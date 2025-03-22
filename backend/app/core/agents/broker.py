"""
Message Broker agent implementation.

This agent is responsible for routing messages between agents based on LLM analysis 
of the message content and determining the most appropriate recipient.
"""
from typing import Optional, Dict, List, Any, AsyncGenerator
import logging
from datetime import datetime

from .base import BaseAgent
from ..models import Message
from ...utils.logger import get_logger
from ...utils.message_utils import truncate_message
from ...utils.model_client import model_client, ModelProvider, GenerationParameters

# Import broker config
from .config import BROKER_CONFIG

logger = get_logger(__name__)

class MessageBrokerAgent(BaseAgent):
    """
    Agent that routes messages between other agents based on LLM reasoning.
    
    The broker analyzes both the original message sent to an agent and the response
    that agent produced, then decides which agent should receive the message next.
    """
    
    def __init__(self, name: str = "Broker"):
        """Initialize the message broker agent."""
        super().__init__(name=name)
        self.capabilities = [
            "message_routing",
            "llm_inference",
            "agent_coordination"
        ]
        self.message_history: Dict[str, List[Message]] = {}  # Track message chains by conversation ID
        self.default_model = BROKER_CONFIG.get("model", "mistral-large-latest")
        self.model_provider = ModelProvider(BROKER_CONFIG.get("provider", "mistral"))
        self.default_parameters = GenerationParameters(
            temperature=BROKER_CONFIG.get("temperature", 0.3),
            top_p=0.95,
            max_tokens=300,
            provider=self.model_provider
        )
        self.prompts = BROKER_CONFIG.get("prompts", {})
        
    async def process_message(self, message: Message) -> Optional[Message]:
        """
        Process a message and determine where to route it next.
        
        This is called when a message is specifically sent to the broker.
        """
        try:
            # Set status to thinking
            await self.set_status("thinking")
            
            # Log the message
            logger.debug(f"Broker agent {self.name} processing message: {truncate_message(message)}")
            
            # Store the message in history
            conversation_id = message.conversation_id if hasattr(message, "conversation_id") else "default"
            if conversation_id not in self.message_history:
                self.message_history[conversation_id] = []
            self.message_history[conversation_id].append(message)
            
            # If this is a routing request, handle it
            if hasattr(message, "message_type") and message.message_type == "route_request":
                # Extract the original message and response from the request
                original_message = message.content.get("original_message")
                response_message = message.content.get("response_message")
                
                # Determine the next agent to route to
                next_agent_id = await self._determine_next_agent(original_message, response_message)
                
                # Create a routing decision message
                routing_decision = Message(
                    sender_id=self.agent_id,
                    receiver_id=message.sender_id,
                    content={
                        "next_agent_id": next_agent_id,
                        "original_message_id": original_message.get("id") if isinstance(original_message, dict) else None,
                        "response_message_id": response_message.get("id") if isinstance(response_message, dict) else None
                    },
                    message_type="routing_decision",
                    conversation_id=conversation_id
                )
                
                # Set status to responding
                await self.set_status("responding")
                
                return routing_decision
            
            # For other message types, just acknowledge receipt
            # Set status to responding
            await self.set_status("responding")
            
            # Create an acknowledgment message
            return Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": "Message received by broker agent."},
                message_type="acknowledgment",
                conversation_id=conversation_id if hasattr(message, "conversation_id") else None
            )
            
        except Exception as e:
            logger.error(f"Error processing message in broker agent: {e}", exc_info=True)
            
            # Set status back to idle on error
            await self.set_status("idle")
            
            # Return an error message
            return Message(
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                content={"text": f"I encountered an error: {str(e)}"},
                message_type="error",
                conversation_id=message.conversation_id if hasattr(message, "conversation_id") else None
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
        
        logger.info(f"Broker engaged to determine next receiver for message from {sender_id}")
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
                if is_new_conversation and original_sender and original_sender.startswith("user-"):
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
        logger.info(f"Prompt: {prompt}")
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
        prompt_template = self.prompts.get("new_conversation", """You are a Message Broker responsible for routing initial messages to the appropriate agent in a multi-agent system.

NEW CONVERSATION MESSAGE:
{original_message}

AVAILABLE AGENTS:
{agents_info}

Based on the content of this new message, determine which agent should receive it first. Consider the following:
1. The topic and intent of the message
2. The capabilities of each available agent
3. Which agent would be most appropriate to handle this initial request

Choose the most appropriate agent from the list. You must select one of the available agents listed above.

FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS:
REASONING: [Your step-by-step reasoning about which agent is most appropriate]
SELECTED AGENT ID: [The ID of the selected agent]
""")
        
        # Format the prompt with the message content and agents info
        return prompt_template.format(
            original_message=message_content,
            agents_info=agents_info
        )
    
    async def think(self) -> AsyncGenerator[Optional[Message], None]:
        """Message broker agents do not think autonomously."""
        yield None 