"""
gRPC server implementation for agent registration service
"""
import asyncio
import time
import uuid
import sys
import os
import re
from typing import Dict, Optional

# Add the parent directory to sys.path so we can import the generated modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import generated gRPC code
from generated.agent_registration_service_pb2 import (
    AgentRegistrationResponse, AgentUnregistrationResponse, 
    Command, CommandResultResponse
)
from generated.agent_registration_service_pb2_grpc import (
    AgentRegistrationServiceServicer, add_AgentRegistrationServiceServicer_to_server
)

# Import shared modules
from shared_models import setup_logging, AgentStatus
import state
import agent_manager

logger = setup_logging(__name__)

# Global variables
# Map of agent_id to stream context
agent_command_streams = {}
# Lock for accessing the command streams
command_stream_lock = asyncio.Lock()
# Map of command_id to pending commands and their associated agent_id
pending_commands = {}  # { command_id: {"command": Command, "agent_id": agent_id} }
# Map of command_id to completed command results
command_results = {}

class AgentRegistrationServicer(AgentRegistrationServiceServicer):
    """Implementation of the AgentRegistrationService"""
    
    async def RegisterAgent(self, request, context):
        """
        Register an agent with the server.
        This is a unary RPC that registers an agent and returns a success status.
        """
        agent_id = request.agent_id
        agent_name = request.agent_name
        
        # If no agent_id provided, generate one
        if not agent_id:
            agent_id = str(uuid.uuid4())
            logger.info(f"Generated new agent_id: {agent_id}")
        
        # Add or update agent in the status registry
        status = AgentStatus(
            agent_id=agent_id,
            agent_name=agent_name or f"Agent-{agent_id[:8]}",
            last_seen=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )
        
        logger.info(f"Registering agent: {agent_id} ({agent_name})")
        await state.update_agent_status(agent_id, status)
        
        # Store capabilities and metadata
        capabilities = dict(request.capabilities)
        hostname = request.hostname
        platform = request.platform
        version = request.version
        
        # Store additional agent information
        state.agent_metadata[agent_id] = {
            "capabilities": capabilities,
            "hostname": hostname,
            "platform": platform,
            "version": version
        }
        
        # Return successful response with the agent_id
        return AgentRegistrationResponse(
            success=True,
            message=f"Agent registered successfully",
            server_assigned_id=agent_id
        )
    
    async def UnregisterAgent(self, request, context):
        """
        Unregister an agent from the server.
        This is a unary RPC that unregisters an agent and returns a success status.
        """
        agent_id = request.agent_id
        
        if not agent_id:
            return AgentUnregistrationResponse(
                success=False,
                message="No agent_id provided"
            )
        
        logger.info(f"Unregistering agent: {agent_id}")
        
        # Remove agent from status registry and update status
        if agent_id in state.agent_statuses:
            status = state.agent_statuses[agent_id]
            status.status = "offline"
            status.last_seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            state.update_agent_status(agent_id, status)
        
        # Remove any active command stream
        async with command_stream_lock:
            if agent_id in agent_command_streams:
                logger.info(f"Closing command stream for agent: {agent_id}")
                agent_command_streams.pop(agent_id, None)
        
        return AgentUnregistrationResponse(
            success=True,
            message="Agent unregistered successfully"
        )
    
    async def ReceiveCommands(self, request, context):
        """
        Stream commands to an agent.
        This is a server-streaming RPC that sends commands to the agent when they become available.
        """
        agent_id = request.agent_id
        
        if not agent_id:
            logger.error("Agent tried to receive commands without providing an agent_id")
            return
        
        logger.info(f"Agent {agent_id} connected for command streaming")
        
        # Create a queue for this agent's commands
        command_queue = asyncio.Queue()
        
        # Register the command stream
        async with command_stream_lock:
            agent_command_streams[agent_id] = command_queue
        
        # Set up cancellation detection
        context.add_done_callback(
            lambda _: asyncio.create_task(self._handle_stream_closed(agent_id))
        )
        
        try:
            # Process commands until the client disconnects
            while True:
                try:
                    # Wait for commands with a timeout to check for cancellation
                    cmd_data = await asyncio.wait_for(command_queue.get(), timeout=60.0)
                    
                    # Check if the context is still valid
                    if context.cancelled():
                        logger.debug(f"Context cancelled for agent {agent_id}, stopping command stream")
                        break
                    
                    # Check if we received a Command object directly or a dict
                    if isinstance(cmd_data, dict) and "command" in cmd_data:
                        # Extract the actual command from the dictionary
                        command = cmd_data["command"]
                    else:
                        # The cmd_data is already a Command object
                        command = cmd_data
                    
                    # Send the command to the agent
                    yield command
                    command_queue.task_done()
                    
                except asyncio.TimeoutError:
                    # No commands received within timeout, check if context is still valid
                    if context.cancelled():
                        logger.debug(f"Context cancelled for agent {agent_id} during timeout")
                        break
                    # Otherwise continue waiting
                    continue
                
        except Exception as e:
            logger.error(f"Error in command stream for agent {agent_id}: {e}")
        finally:
            # Clean up when the stream ends
            await self._handle_stream_closed(agent_id)
            logger.info(f"Command stream closed for agent {agent_id}")
    
    async def SendCommandResult(self, request, context):
        """
        Receive the result of a command execution from an agent.
        This is a unary RPC that returns a confirmation response.
        """
        command_id = request.command_id
        agent_id = request.agent_id
        success = request.success
        output = request.output
        error_message = request.error_message
        exit_code = request.exit_code
        execution_time_ms = request.execution_time_ms
        
        logger.info(f"Received command result from agent {agent_id} for command {command_id}")
        
        # Store the command result
        result = {
            "command_id": command_id,
            "agent_id": agent_id,
            "success": success,
            "output": output,
            "error_message": error_message,
            "exit_code": exit_code,
            "execution_time_ms": execution_time_ms,
            "received_time": time.time()
        }
        
        # Store in the completed commands and remove from pending
        command_results[command_id] = result
        pending_commands.pop(command_id, None)
        
        # Check if this is a status update
        if command_id.startswith("status_update_"):
            # Parse the status from the output
            status_match = re.search(r"Status updated to (\w+)", output)
            if status_match:
                new_status = status_match.group(1).lower()
                logger.info(f"Processing status update for agent {agent_id}: {new_status}")
                
                # Update the agent's status
                if agent_id in state.agent_statuses:
                    status = state.agent_statuses[agent_id]
                    status.status = new_status
                    status.last_seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    await state.update_agent_status(agent_id, status)
                else:
                    logger.warning(f"Cannot update status for unknown agent: {agent_id}")
        
        return CommandResultResponse(
            received=True,
            message="Command result received successfully"
        )
    
    async def _handle_stream_closed(self, agent_id):
        """Handle cleanup when a command stream is closed"""
        async with command_stream_lock:
            if agent_id in agent_command_streams:
                logger.info(f"Removing command stream for agent: {agent_id}")
                agent_command_streams.pop(agent_id, None)

async def send_command_to_agent(agent_id: str, command_type: str, content: str = "", parameters: Dict[str, str] = None) -> bool:
    """Send a command to an agent via gRPC.
    
    Args:
        agent_id: The ID of the agent to send the command to
        command_type: The type of command to send
        content: Optional content string for the command
        parameters: Optional parameters for the command
        
    Returns:
        True if the command was sent successfully, False otherwise
    """
    # Validate agent exists
    if agent_id not in state.agent_statuses:
        logger.error(f"Cannot send command to non-existent agent: {agent_id}")
        return False
    
    # Generate a unique command ID
    command_id = f"{uuid.uuid4()}"
    
    # If parameters is None, use an empty dict
    if parameters is None:
        parameters = {}
    
    try:
        logger.info(f"Sending {command_type} command to agent {agent_id}")
        command = Command(
            command_id=command_id,
            type=command_type,
            content=content,
            parameters=parameters,
            is_cancellation=False
        )
        
        # Create command data with metadata
        command_data = {"command": command, "agent_id": agent_id}
        
        # Add to pending commands
        pending_commands[command_id] = command_data
        
        # Check if the agent has a command queue
        if agent_id not in agent_command_streams:
            command_queue = asyncio.Queue()
            agent_command_streams[agent_id] = command_queue
            logger.info(f"Created command queue for agent {agent_id}")
            
        # Add to agent's command queue - pass the command directly as we now handle both in ReceiveCommands
        command_queue = agent_command_streams[agent_id]
        await command_queue.put(command)  # Send just the command to be consistent with proto
        logger.info(f"Added {command_type} command {command_id} to agent {agent_id}'s queue")

        # Special handling for pause/resume commands - update agent status immediately
        if command_type == "pause":
            # Update the agent's status to reflect it's paused
            if agent_id in state.agent_statuses:
                state.agent_statuses[agent_id].status = "paused"
                logger.info(f"Updated agent {agent_id} status to 'paused'")
                # Broadcast the status update
                asyncio.create_task(state.broadcast_agent_status_update(is_full_update=True))
                
        elif command_type == "resume":
            # Update the agent's status to reflect it's active again
            if agent_id in state.agent_statuses:
                state.agent_statuses[agent_id].status = "online"
                logger.info(f"Updated agent {agent_id} status to 'online'")
                # Broadcast the status update
                asyncio.create_task(state.broadcast_agent_status_update(is_full_update=True))

        return True
    except Exception as e:
        logger.error(f"Error sending command to agent {agent_id}: {e}")
        return False

async def cancel_command(command_id: str) -> bool:
    """
    Cancel a pending command.
    
    Args:
        command_id: The ID of the command to cancel
        
    Returns:
        True if the command was canceled, False otherwise
    """
    if command_id not in pending_commands:
        logger.warning(f"Command {command_id} not found or already completed")
        return False
    
    # Get the agent_id from the pending commands map
    agent_id = pending_commands[command_id]["agent_id"]
    
    async with command_stream_lock:
        if agent_id not in agent_command_streams:
            logger.error(f"Agent {agent_id} is not connected for commands")
            return False
        
        # Create a cancellation command
        cancel_command = Command(
            command_id=command_id,
            type="cancellation",
            content="",
            parameters={},
            is_cancellation=True
        )
        
        # Send to the agent's command queue
        command_queue = agent_command_streams[agent_id]
        await command_queue.put(cancel_command)  # Send just the command to be consistent
        
        logger.info(f"Cancellation for command {command_id} sent to agent {agent_id}")
        return True

def start_registration_service(server):
    """Add the agent registration service to the given gRPC server"""
    servicer = AgentRegistrationServicer()
    add_AgentRegistrationServiceServicer_to_server(servicer, server)
    logger.info("Agent registration service added to gRPC server")