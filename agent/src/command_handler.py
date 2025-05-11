"""Handles commands received from the server for a specific agent."""
import asyncio
import json
import logging
from typing import Any, Callable, Dict, TYPE_CHECKING

from decorators import log_exceptions
from shared_models import setup_logging

# Conditional import for type checking to avoid circular dependency
if TYPE_CHECKING:
    from agent import Agent

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

class CommandHandler:
    """Processes commands directed at the agent from the central server."""

    def __init__(self, agent: 'Agent'):
        """Initialize the CommandHandler with a reference to the agent instance."""
        self.agent = agent

        # Map command type strings to their corresponding handler methods
        self.command_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            "pause": self._handle_pause_command,
            "resume": self._handle_resume_command,
            "shutdown": self._handle_shutdown_command,
            "status": self._handle_status_command,
            # Add more command handlers here as needed
        }
        logger.debug(f"CommandHandler initialized for agent '{self.agent.agent_name}' (ID: {self.agent.agent_id})")

    @log_exceptions
    async def handle_server_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Asynchronously process a command received from the server.

        Identifies the command type and delegates to the appropriate handler coroutine.
        Returns a result dictionary indicating success or failure.

        Args:
            command: The command dictionary received from the server.

        Returns:
            A dictionary containing the result of the command execution.
        """
        command_type = command.get("type", "unknown")
        command_id = command.get("command_id", "unknown")

        logger.info(f"Handling server command '{command_type}' (ID: {command_id})")

        # Default result structure
        result = {
            "success": False,
            "output": f"Command '{command_type}' not acknowledged.",
            "error_message": "",
            "exit_code": 1  # Default to error
        }

        handler = self.command_handlers.get(command_type)
        if handler:
            try:
                handler_result = await handler(command)
                result.update(handler_result)
                logger.info(f"Command '{command_type}' (ID: {command_id}) executed. Success: {result.get('success')}")
            except Exception as e:
                logger.error(f"Error executing command handler for '{command_type}' (ID: {command_id}): {e}", exc_info=True)
                result.update({
                    "success": False,
                    "output": f"Error executing command: {command_type}",
                    "error_message": str(e),
                    "exit_code": 1
                })
        else:
            logger.warning(f"Received unknown command type: '{command_type}' (ID: {command_id})")
            result.update({
                "success": False,
                "output": f"Unknown command type: {command_type}",
                "error_message": f"Command type '{command_type}' not supported by this agent.",
                "exit_code": 1
            })

        return result

    # --- Specific Command Handlers ---

    async def _handle_pause_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handles the 'pause' command asynchronously."""
        logger.info("Executing pause command.")
        try:
            await self.agent.pause()  # Agent.pause should be async
            return {"success": True, "output": "Agent paused successfully.", "exit_code": 0}
        except Exception as e:
            logger.error(f"Error pausing agent: {e}", exc_info=True)
            return {"success": False, "output": "Failed to pause agent.", "error_message": str(e), "exit_code": 1}

    async def _handle_resume_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handles the 'resume' command asynchronously."""
        logger.info("Executing resume command.")
        try:
            await self.agent.resume()  # Agent.resume should be async
            return {"success": True, "output": "Agent resumed successfully.", "exit_code": 0}
        except Exception as e:
            logger.error(f"Error resuming agent: {e}", exc_info=True)
            return {"success": False, "output": "Failed to resume agent.", "error_message": str(e), "exit_code": 1}

    async def _handle_shutdown_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handles the 'shutdown' command asynchronously."""
        logger.info("Executing shutdown command.")
        await self.agent.shutdown()
        return {"success": True, "output": "Agent shutdown initiated.", "exit_code": 0}

    async def _handle_status_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handles the 'status' command asynchronously."""
        logger.info("Executing status command.")
        try:
            status_info = await self.agent.get_status()  # Agent.get_status should be async
            return {"success": True, "output": json.dumps(status_info), "exit_code": 0}
        except Exception as e:
            logger.error(f"Error getting agent status: {e}", exc_info=True)
            return {"success": False, "output": "Failed to retrieve agent status.", "error_message": str(e), "exit_code": 1}