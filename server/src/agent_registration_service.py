"""
gRPC server implementation for agent registration service
"""
import asyncio
import time
import uuid
import sys
import os
from typing import Dict, Optional

# Add the parent directory to sys.path so we can import the generated modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import generated gRPC code
from generated.agent_registration_service_pb2 import (
    AgentRegistrationResponse, AgentUnregistrationResponse, 
    HeartbeatResponse, Command, CommandResultResponse
)
from generated.agent_registration_service_pb2_grpc import (
    AgentRegistrationServiceServicer, add_AgentRegistrationServiceServicer_to_server
)

# Import shared modules
from shared_models import setup_logging, AgentStatus
import state

logger = setup_logging(__name__)

# Global variables
# Map of agent_id to stream context
agent_command_streams = {}
# Map of agent_id to last heartbeat time
agent_heartbeats = {}
# Lock for accessing the command streams
command_stream_lock = asyncio.Lock()
# Map of command_id to pending commands
pending_commands = {}
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
            is_online=True,
            last_seen=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )
        
        logger.info(f"Registering agent: {agent_id} ({agent_name})")
        state.update_agent_status(agent_id, status)
        
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
        
        # Remove agent from status registry or mark as offline
        if agent_id in state.agent_statuses:
            status = state.agent_statuses[agent_id]
            status.is_online = False
            status.last_seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            state.update_agent_status(agent_id, status)
        
        # Remove any active command stream
        async with command_stream_lock:
            if agent_id in agent_command_streams:
                logger.info(f"Closing command stream for agent: {agent_id}")
                agent_command_streams.pop(agent_id, None)
        
        # Remove heartbeat record
        agent_heartbeats.pop(agent_id, None)
        
        return AgentUnregistrationResponse(
            success=True,
            message="Agent unregistered successfully"
        )
    
    async def SendHeartbeat(self, request, context):
        """
        Process a heartbeat from an agent.
        This is a unary RPC that updates the agent's status and returns a heartbeat response.
        """
        agent_id = request.agent_id
        status_text = request.status
        metrics = dict(request.metrics)
        
        if not agent_id:
            return HeartbeatResponse(
                success=False,
                interval=30  # Default interval
            )
        
        # Update the agent's last heartbeat time
        current_time = time.time()
        agent_heartbeats[agent_id] = current_time
        
        # Update agent status
        if agent_id in state.agent_statuses:
            status = state.agent_statuses[agent_id]
            status.is_online = True
            status.last_seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            state.update_agent_status(agent_id, status)
            
            # Also update metrics if needed
            if metrics and agent_id in state.agent_metadata:
                state.agent_metadata[agent_id]["metrics"] = metrics
        
        logger.debug(f"Received heartbeat from agent: {agent_id} (status: {status_text})")
        
        # Return the recommended heartbeat interval
        return HeartbeatResponse(
            success=True,
            interval=30  # Heartbeat interval in seconds
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
                    command = await asyncio.wait_for(command_queue.get(), timeout=60.0)
                    
                    # Check if the context is still valid
                    if context.cancelled():
                        logger.debug(f"Context cancelled for agent {agent_id}, stopping command stream")
                        break
                    
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

async def send_command_to_agent(agent_id: str, command_type: str, content: str, 
                               parameters: Optional[Dict[str, str]] = None) -> Optional[str]:
    """
    Send a command to a specific agent.
    
    Args:
        agent_id: The ID of the agent to send the command to
        command_type: The type of command (e.g., "shell", "python")
        content: The content of the command to execute
        parameters: Additional parameters for the command
        
    Returns:
        The command ID if the command was successfully queued, None otherwise
    """
    # Generate a unique command ID
    command_id = str(uuid.uuid4())
    
    async with command_stream_lock:
        if agent_id not in agent_command_streams:
            logger.error(f"Agent {agent_id} is not connected for commands")
            return None
        
        # Create the command
        command = Command(
            command_id=command_id,
            type=command_type,
            content=content,
            parameters=parameters or {},
            is_cancellation=False
        )
        
        # Add to pending commands
        pending_commands[command_id] = {
            "agent_id": agent_id,
            "command": command,
            "queued_time": time.time()
        }
        
        # Send to the agent's command queue
        command_queue = agent_command_streams[agent_id]
        await command_queue.put(command)
        
        logger.info(f"Command {command_id} sent to agent {agent_id}")
        return command_id

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
    
    command_info = pending_commands[command_id]
    agent_id = command_info["agent_id"]
    
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
        await command_queue.put(cancel_command)
        
        logger.info(f"Cancellation for command {command_id} sent to agent {agent_id}")
        return True

async def process_heartbeats():
    """
    Periodic task to check agent heartbeats and mark agents as offline if they haven't
    sent a heartbeat in the configured timeout period.
    """
    while True:
        try:
            current_time = time.time()
            timeout = 90  # 3x the heartbeat interval
            
            offline_agents = []
            
            for agent_id, last_heartbeat in agent_heartbeats.items():
                if current_time - last_heartbeat > timeout:
                    # Agent hasn't sent a heartbeat in the timeout period
                    offline_agents.append(agent_id)
            
            # Update the status of offline agents
            status_updated = False
            for agent_id in offline_agents:
                if agent_id in state.agent_statuses and state.agent_statuses[agent_id].is_online:
                    logger.info(f"Agent {agent_id} marked as offline due to missed heartbeats")
                    status = state.agent_statuses[agent_id]
                    status.is_online = False
                    status.last_seen = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    state.update_agent_status(agent_id, status)
                    status_updated = True
            
            # Sleep for a while before checking again
            await asyncio.sleep(30)
            
        except Exception as e:
            logger.error(f"Error in heartbeat processing: {e}")
            await asyncio.sleep(30)  # Sleep and retry

def start_registration_service(server):
    """Add the agent registration service to the given gRPC server"""
    servicer = AgentRegistrationServicer()
    add_AgentRegistrationServiceServicer_to_server(servicer, server)
    
    # Start the heartbeat processing task
    asyncio.create_task(process_heartbeats())
    
    logger.info("Agent registration service added to gRPC server") 