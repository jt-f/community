#!/usr/bin/env python3
"""
Example implementation of an agent using gRPC for registration and command handling
"""
import asyncio
import os
import sys
import signal
from typing import Dict, Any

# Add the parent directory to sys.path so we can import modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import the gRPC client
import grpc_client
from shared_models import setup_logging

# Configure logging
logger = setup_logging(__name__)

# Configuration (could be moved to a config file or env vars)
SERVER_HOST = os.environ.get("SERVER_HOST", "localhost")
SERVER_PORT = int(os.environ.get("GRPC_PORT", "50051"))
AGENT_NAME = os.environ.get("AGENT_NAME", None)

# Command handlers
async def handle_command(command: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a command received from the server
    
    Args:
        command: Dictionary containing command data
        
    Returns:
        Dictionary with the command result
    """
    command_id = command["command_id"]
    command_type = command["type"]
    content = command["content"]
    parameters = command["parameters"]
    
    logger.info(f"Handling command: {command_id} (type: {command_type})")
    
    # Handle different command types
    if command_type == "shell":
        return await handle_shell_command(content, parameters)
    elif command_type == "python":
        return await handle_python_command(content, parameters)
    else:
        return {
            "success": False,
            "output": "",
            "error_message": f"Unsupported command type: {command_type}",
            "exit_code": 1
        }

async def handle_shell_command(content: str, parameters: Dict[str, str]) -> Dict[str, Any]:
    """Execute a shell command"""
    try:
        # Execute the command
        logger.info(f"Executing shell command: {content}")
        
        # Set up process
        process = await asyncio.create_subprocess_shell(
            content,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Wait for the process to complete
        stdout, stderr = await process.communicate()
        
        # Get exit code
        exit_code = process.returncode
        
        # Decode output
        stdout_text = stdout.decode("utf-8")
        stderr_text = stderr.decode("utf-8")
        
        # Determine success
        success = exit_code == 0
        
        return {
            "success": success,
            "output": stdout_text,
            "error_message": stderr_text,
            "exit_code": exit_code
        }
        
    except Exception as e:
        logger.error(f"Error executing shell command: {e}")
        return {
            "success": False,
            "output": "",
            "error_message": str(e),
            "exit_code": 1
        }

async def handle_python_command(content: str, parameters: Dict[str, str]) -> Dict[str, Any]:
    """Execute a python command"""
    try:
        # Execute the command
        logger.info(f"Executing Python command")
        
        # Write content to a temporary file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w') as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(content)
        
        try:
            # Execute the Python script
            process = await asyncio.create_subprocess_exec(
                sys.executable, temp_file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for the process to complete
            stdout, stderr = await process.communicate()
            
            # Get exit code
            exit_code = process.returncode
            
            # Decode output
            stdout_text = stdout.decode("utf-8")
            stderr_text = stderr.decode("utf-8")
            
            # Determine success
            success = exit_code == 0
            
            return {
                "success": success,
                "output": stdout_text,
                "error_message": stderr_text,
                "exit_code": exit_code
            }
            
        finally:
            # Clean up the temporary file
            os.unlink(temp_file_path)
            
    except Exception as e:
        logger.error(f"Error executing Python command: {e}")
        return {
            "success": False,
            "output": "",
            "error_message": str(e),
            "exit_code": 1
        }

# Signal handling
def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown"""
    loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
        
    logger.info("Signal handlers set up")

async def shutdown(sig):
    """Handle graceful shutdown"""
    logger.info(f"Received exit signal {sig.name}...")
    
    # Unregister the agent
    logger.info("Unregistering agent from server...")
    await grpc_client.unregister_agent(SERVER_HOST, SERVER_PORT)
    
    # Stop the event loop
    logger.info("Stopping event loop...")
    loop = asyncio.get_event_loop()
    loop.stop()

async def main():
    """Main function"""
    # Set up signal handlers for graceful shutdown
    setup_signal_handlers()
    
    # Register command callback
    grpc_client.set_command_callback(handle_command)
    
    # Register the agent with the server
    logger.info(f"Registering agent with server at {SERVER_HOST}:{SERVER_PORT}")
    agent_id = await grpc_client.register_agent(
        server_host=SERVER_HOST,
        server_port=SERVER_PORT,
        name=AGENT_NAME,
        capabilities={
            "shell": "true",
            "python": "true"
        }
    )
    
    if agent_id:
        logger.info(f"Agent registered successfully with ID: {agent_id}")
        
        # Keep the agent running until terminated
        try:
            # Loop forever, or until a signal is received
            while True:
                await asyncio.sleep(60)
                logger.debug("Agent still running...")
        except asyncio.CancelledError:
            logger.info("Main task cancelled")
    else:
        logger.error("Failed to register agent with server")
        return 1
    
    return 0

if __name__ == "__main__":
    # Run the main function
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 