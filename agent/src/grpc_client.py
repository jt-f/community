"""
gRPC client implementation for the agent to register with the server
"""
import grpc
import asyncio
import time
import inspect
import socket
import platform
import os
import sys
from typing import Callable, Dict, Optional

# Add the parent directory to sys.path so we can import the generated modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import shared modules
from shared_models import setup_logging

logger = setup_logging(__name__)

# Import generated gRPC code
# Note: These imports will only work after running generate_grpc.py
try:
    from generated.agent_registration_service_pb2 import (
        AgentRegistrationRequest, AgentUnregistrationRequest, 
        HeartbeatRequest, CommandStreamRequest, CommandResult
    )
    from generated.agent_registration_service_pb2_grpc import AgentRegistrationServiceStub
    GRPC_IMPORTS_SUCCESSFUL = True
except ImportError as e:
    logger.warning(f"gRPC generated code not found. Please run generate_grpc.py first. Error: {e}")
    GRPC_IMPORTS_SUCCESSFUL = False

# Global variables
agent_id = None  # Will be set during registration
agent_name = None  # Will be set during registration
_command_callback = None  # Callback for handling commands
_heartbeat_interval = 30  # Default interval in seconds
_heartbeat_task = None  # Task for sending heartbeats
_command_stream_task = None  # Task for receiving commands

def set_command_callback(callback: Callable):
    """
    Set the callback function that will be called when commands are received.
    
    Args:
        callback: A function that will be called with the command data.
    """
    global _command_callback
    _command_callback = callback
    logger.info("Command callback set")

async def register_agent(
    server_host: str, 
    server_port: int, 
    name: str = None, 
    custom_id: str = None,
    capabilities: Dict[str, str] = None
) -> Optional[str]:
    """
    Register the agent with the server.
    
    Args:
        server_host: The gRPC server hostname or IP
        server_port: The gRPC server port
        name: The display name for this agent
        custom_id: Optional custom ID to use (if None, server will generate one)
        capabilities: Optional dictionary of agent capabilities
        
    Returns:
        The agent_id if registration was successful, None otherwise
    """
    global agent_id, agent_name
    
    if not GRPC_IMPORTS_SUCCESSFUL:
        logger.error("gRPC imports failed. Cannot register agent.")
        return None
    
    try:
        # Create a channel to the server
        logger.info(f"Connecting to gRPC server at {server_host}:{server_port}")
        channel = grpc.aio.insecure_channel(f"{server_host}:{server_port}")
        
        # Create the stub
        stub = AgentRegistrationServiceStub(channel)
        
        # Prepare registration request
        hostname = socket.gethostname()
        agent_capabilities = capabilities or {}
        
        # Add system information to capabilities if not provided
        if "platform" not in agent_capabilities:
            agent_capabilities["platform"] = platform.platform()
        if "python_version" not in agent_capabilities:
            agent_capabilities["python_version"] = platform.python_version()
        
        request = AgentRegistrationRequest(
            agent_id=custom_id or "",
            agent_name=name or f"Agent-{hostname}",
            version="1.0.0",  # You should set this to your actual agent version
            capabilities=agent_capabilities,
            hostname=hostname,
            platform=platform.platform()
        )
        
        # Register the agent
        logger.info(f"Registering agent: {name or 'unnamed'} (ID: {custom_id or 'to be assigned'})")
        response = await stub.RegisterAgent(request)
        
        if response.success:
            # Store the agent ID and name
            agent_id = response.server_assigned_id if not custom_id else custom_id
            agent_name = name or f"Agent-{hostname}"
            
            logger.info(f"Agent registered successfully with ID: {agent_id}")
            
            # Start heartbeat and command stream tasks
            start_heartbeat_task(server_host, server_port)
            start_command_stream_task(server_host, server_port)
            
            return agent_id
        else:
            logger.error(f"Failed to register agent: {response.message}")
            return None
            
    except Exception as e:
        logger.error(f"Error registering agent: {e}")
        return None

async def unregister_agent(server_host: str, server_port: int) -> bool:
    """
    Unregister the agent from the server.
    
    Args:
        server_host: The gRPC server hostname or IP
        server_port: The gRPC server port
        
    Returns:
        True if unregistration was successful, False otherwise
    """
    global agent_id, _heartbeat_task, _command_stream_task
    
    if not agent_id:
        logger.error("Cannot unregister: Agent is not registered")
        return False
    
    if not GRPC_IMPORTS_SUCCESSFUL:
        logger.error("gRPC imports failed. Cannot unregister agent.")
        return False
    
    # Stop heartbeat and command stream tasks
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
    
    if _command_stream_task and not _command_stream_task.done():
        _command_stream_task.cancel()
        try:
            await _command_stream_task
        except asyncio.CancelledError:
            pass
    
    try:
        # Create a channel to the server
        logger.info(f"Connecting to gRPC server at {server_host}:{server_port} for unregistration")
        channel = grpc.aio.insecure_channel(f"{server_host}:{server_port}")
        
        # Create the stub
        stub = AgentRegistrationServiceStub(channel)
        
        # Prepare unregistration request
        request = AgentUnregistrationRequest(agent_id=agent_id)
        
        # Unregister the agent
        logger.info(f"Unregistering agent: {agent_id}")
        response = await stub.UnregisterAgent(request)
        
        if response.success:
            logger.info(f"Agent unregistered successfully: {response.message}")
            return True
        else:
            logger.error(f"Failed to unregister agent: {response.message}")
            return False
            
    except Exception as e:
        logger.error(f"Error unregistering agent: {e}")
        return False

def start_heartbeat_task(server_host: str, server_port: int):
    """Start the heartbeat task"""
    global _heartbeat_task
    
    if _heartbeat_task and not _heartbeat_task.done():
        logger.info("Heartbeat task already running")
        return
    
    _heartbeat_task = asyncio.create_task(heartbeat_loop(server_host, server_port))
    logger.info("Heartbeat task started")

def start_command_stream_task(server_host: str, server_port: int):
    """Start the command stream task"""
    global _command_stream_task
    
    if _command_stream_task and not _command_stream_task.done():
        logger.info("Command stream task already running")
        return
    
    _command_stream_task = asyncio.create_task(command_stream_loop(server_host, server_port))
    logger.info("Command stream task started")

async def heartbeat_loop(server_host: str, server_port: int):
    """
    Send periodic heartbeats to the server.
    
    Args:
        server_host: The gRPC server hostname or IP
        server_port: The gRPC server port
    """
    global agent_id, _heartbeat_interval
    
    if not agent_id:
        logger.error("Cannot send heartbeat: Agent is not registered")
        return
    
    try:
        # Create a channel to the server
        channel = grpc.aio.insecure_channel(f"{server_host}:{server_port}")
        
        # Create the stub
        stub = AgentRegistrationServiceStub(channel)
        
        while True:
            try:
                # Prepare heartbeat request with metrics
                metrics = {
                    "memory_percent": str(round(get_memory_usage(), 2)),
                    "cpu_percent": str(round(get_cpu_usage(), 2))
                }
                
                request = HeartbeatRequest(
                    agent_id=agent_id,
                    status="IDLE",  # You can change this based on your agent's state
                    metrics=metrics
                )
                
                # Send heartbeat
                logger.debug(f"Sending heartbeat for agent: {agent_id}")
                response = await stub.SendHeartbeat(request)
                
                if response.success:
                    # Update heartbeat interval if server suggests a different value
                    if response.interval != _heartbeat_interval and response.interval > 0:
                        logger.info(f"Updating heartbeat interval from {_heartbeat_interval} to {response.interval} seconds")
                        _heartbeat_interval = response.interval
                else:
                    logger.warning("Heartbeat was not acknowledged by server")
                
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
            
            # Sleep until next heartbeat
            await asyncio.sleep(_heartbeat_interval)
            
    except asyncio.CancelledError:
        logger.info("Heartbeat task cancelled")
    except Exception as e:
        logger.error(f"Heartbeat loop terminated with error: {e}")

async def command_stream_loop(server_host: str, server_port: int):
    """
    Connect to the server's command stream and process commands.
    
    Args:
        server_host: The gRPC server hostname or IP
        server_port: The gRPC server port
    """
    global agent_id, _command_callback
    
    if not agent_id:
        logger.error("Cannot receive commands: Agent is not registered")
        return
    
    attempt = 0
    max_backoff = 60  # Maximum backoff in seconds
    initial_attempts = 5  # Number of attempts before switching to max backoff
    
    while True:  # Infinite retry loop
        try:
            # Implement exponential backoff for reconnection
            if attempt > 0:
                if attempt <= initial_attempts:
                    # Use exponential backoff for initial attempts
                    backoff = min(5 * (2 ** (attempt - 1)), max_backoff)
                    logger.info(f"Attempting to reconnect to command stream in {backoff} seconds (attempt {attempt})")
                else:
                    # After initial attempts, use maximum backoff
                    backoff = max_backoff
                    logger.info(f"Attempting to reconnect to command stream in {backoff} seconds (attempt {attempt}, using max backoff)")
                await asyncio.sleep(backoff)
            
            attempt += 1
            
            # Create a channel to the server
            channel = grpc.aio.insecure_channel(f"{server_host}:{server_port}")
            
            # Create the stub
            stub = AgentRegistrationServiceStub(channel)
            
            # Prepare command stream request
            request = CommandStreamRequest(agent_id=agent_id)
            
            # Connect to command stream
            logger.info(f"Connecting to command stream for agent: {agent_id}")
            
            # Reset attempt counter on successful connection
            attempt = 0
            
            # Process commands from the stream
            async for command in stub.ReceiveCommands(request):
                try:
                    command_id = command.command_id
                    command_type = command.type
                    content = command.content
                    parameters = dict(command.parameters)
                    is_cancellation = command.is_cancellation
                    
                    logger.info(f"Received command: {command_id} (type: {command_type})")
                    
                    if is_cancellation:
                        logger.info(f"Command {command_id} was cancelled")
                        continue
                    
                    # Process the command using the callback if set
                    if _command_callback:
                        # Create the command object
                        command_obj = {
                            "command_id": command_id,
                            "type": command_type,
                            "content": content,
                            "parameters": parameters
                        }
                        
                        # Call the callback with the command
                        try:
                            if inspect.iscoroutinefunction(_command_callback):
                                # Execute the callback asynchronously and don't block the stream
                                asyncio.create_task(
                                    process_command(command_obj, server_host, server_port)
                                )
                            else:
                                # For non-async callbacks, still run in a task to avoid blocking
                                asyncio.create_task(
                                    run_sync_command_callback(command_obj, server_host, server_port)
                                )
                        except Exception as callback_err:
                            logger.error(f"Error in command callback: {callback_err}")
                            # Send error result
                            await send_command_result(
                                server_host, server_port, command_id, 
                                success=False, output="", 
                                error_message=f"Error in command callback: {callback_err}",
                                exit_code=1
                            )
                    else:
                        logger.warning(f"Received command but no callback is registered")
                        # Send unsupported result
                        await send_command_result(
                            server_host, server_port, command_id, 
                            success=False, output="", 
                            error_message="No command handler is registered",
                            exit_code=1
                        )
                        
                except Exception as process_err:
                    logger.error(f"Error processing command: {process_err}")
                    continue
            
            # If we get here, the stream has ended normally
            logger.info("Command stream closed normally. Reconnecting...")
            
        except grpc.RpcError as e:
            handle_grpc_error(e)
        except asyncio.CancelledError:
            logger.info("Command stream task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in command stream: {e}")

async def process_command(command: Dict, server_host: str, server_port: int):
    """
    Process a command using the callback and send the result.
    
    Args:
        command: The command to process
        server_host: The gRPC server hostname or IP
        server_port: The gRPC server port
    """
    global _command_callback
    
    command_id = command["command_id"]
    
    try:
        # Start timing
        start_time = time.time()
        
        # Execute the command
        if inspect.iscoroutinefunction(_command_callback):
            result = await _command_callback(command)
        else:
            result = _command_callback(command)
        
        # End timing
        end_time = time.time()
        execution_time_ms = int((end_time - start_time) * 1000)
        
        # Parse the result
        success = result.get("success", False)
        output = result.get("output", "")
        error_message = result.get("error_message", "")
        exit_code = result.get("exit_code", 0 if success else 1)
        
        # Send the result
        await send_command_result(
            server_host, server_port, command_id,
            success=success, output=output, 
            error_message=error_message, exit_code=exit_code,
            execution_time_ms=execution_time_ms
        )
        
    except Exception as e:
        logger.error(f"Error processing command {command_id}: {e}")
        # Send error result
        await send_command_result(
            server_host, server_port, command_id,
            success=False, output="", 
            error_message=f"Error processing command: {e}",
            exit_code=1
        )

async def run_sync_command_callback(command: Dict, server_host: str, server_port: int):
    """Wrapper to run a synchronous callback in a separate thread"""
    global _command_callback
    
    def run_callback():
        return _command_callback(command)
    
    # Run the callback in a thread pool to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, run_callback)
    
    # Process the result and send it
    command_id = command["command_id"]
    
    try:
        # Parse the result
        success = result.get("success", False)
        output = result.get("output", "")
        error_message = result.get("error_message", "")
        exit_code = result.get("exit_code", 0 if success else 1)
        
        # Send the result
        await send_command_result(
            server_host, server_port, command_id,
            success=success, output=output, 
            error_message=error_message, exit_code=exit_code
        )
        
    except Exception as e:
        logger.error(f"Error processing command result {command_id}: {e}")
        # Send error result
        await send_command_result(
            server_host, server_port, command_id,
            success=False, output="", 
            error_message=f"Error processing command result: {e}",
            exit_code=1
        )

async def send_command_result(
    server_host: str, 
    server_port: int, 
    command_id: str, 
    success: bool, 
    output: str, 
    error_message: str = "", 
    exit_code: int = 0,
    execution_time_ms: int = 0
) -> bool:
    """
    Send the result of a command back to the server.
    
    Args:
        server_host: The gRPC server hostname or IP
        server_port: The gRPC server port
        command_id: The ID of the command
        success: Whether the command was successful
        output: The command output
        error_message: Any error message if the command failed
        exit_code: The command exit code
        execution_time_ms: The command execution time in milliseconds
        
    Returns:
        True if the result was sent successfully, False otherwise
    """
    global agent_id
    
    if not agent_id:
        logger.error("Cannot send command result: Agent is not registered")
        return False
    
    try:
        # Create a channel to the server
        channel = grpc.aio.insecure_channel(f"{server_host}:{server_port}")
        
        # Create the stub
        stub = AgentRegistrationServiceStub(channel)
        
        # Prepare result request
        request = CommandResult(
            command_id=command_id,
            agent_id=agent_id,
            success=success,
            output=output,
            error_message=error_message,
            exit_code=exit_code,
            execution_time_ms=execution_time_ms or int(time.time() * 1000)  # Use current time if not provided
        )
        
        # Send the result
        logger.info(f"Sending result for command {command_id}: success={success}, exit_code={exit_code}")
        response = await stub.SendCommandResult(request)
        
        return response.received
        
    except Exception as e:
        logger.error(f"Error sending command result: {e}")
        return False

def handle_grpc_error(e: grpc.RpcError):
    """Handle gRPC errors with appropriate logging"""
    if hasattr(e, 'code'):
        code = e.code()
        details = e.details() if hasattr(e, 'details') else "Unknown details"
        
        # Handle specific gRPC status codes
        if code == grpc.StatusCode.UNAVAILABLE:
            logger.error(f"gRPC server unavailable: {details}")
        elif code == grpc.StatusCode.CANCELLED:
            logger.warning(f"gRPC stream cancelled: {details}")
        elif code == grpc.StatusCode.DEADLINE_EXCEEDED:
            logger.error(f"gRPC deadline exceeded: {details}")
        elif code == grpc.StatusCode.UNIMPLEMENTED:
            logger.error(f"gRPC method not implemented: {details}")
        elif code == grpc.StatusCode.INTERNAL:
            logger.error(f"gRPC internal server error: {details}")
        else:
            logger.error(f"gRPC error with code {code}: {details}")
    else:
        logger.error(f"gRPC error: {e}")

def get_memory_usage() -> float:
    """Get the current memory usage as a percentage"""
    try:
        import psutil
        return psutil.virtual_memory().percent
    except ImportError:
        return 0.0

def get_cpu_usage() -> float:
    """Get the current CPU usage as a percentage"""
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        return 0.0 