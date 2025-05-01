"""Handles commands received from the server for a specific agent."""
import logging
import json
import asyncio
from typing import Dict, Any, TYPE_CHECKING

from shared_models import setup_logging
from decorators import log_exceptions

if TYPE_CHECKING:
    from agent import Agent  # Import Agent type hint for circular dependency

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module


class CommandHandler:
    """Handles commands received from the server for a specific agent."""

    def __init__(self, agent: 'Agent'):
        """Initialize the CommandHandler with a reference to the agent."""
        self.agent = agent
        # Map command types to handler methods
        self.command_handlers = {
            "pause": self._handle_pause_command,
            "resume": self._handle_resume_command,
            "shutdown": self._handle_shutdown_command,
            "status": self._handle_status_command
        }
        logger.info(f"CommandHandler initialized for agent {self.agent.agent_id}")

    @log_exceptions
    def handle_server_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Process commands received from the server."""
        logger.info(f"Handling server command {command}")

        command_type = command.get("type", "")
        command_id = command.get("command_id", "unknown")

        result = {
            "success": True,
            "output": "Command acknowledged",
            "error_message": "",
            "exit_code": 0
        }

        handler = self.command_handlers.get(command_type)
        if handler:
            try:
                # Pass the command dictionary to the handler
                handler_result = handler(command)
                result.update(handler_result)
            except Exception as e:
                logger.error(f"Error executing command handler for {command_type}: {e}", exc_info=True)
                result.update({
                    "success": False,
                    "output": f"Error executing command: {command_type}",
                    "error_message": str(e),
                    "exit_code": 1
                })
        else:
            logger.warning(f"Received unknown command type: {command_type}")
            result.update({
                "success": False,
                "output": f"Unknown command type: {command_type}",
                "error_message": f"Command type {command_type} not supported",
                "exit_code": 1
            })

        logger.debug(f"Command result for {command_id}: {result}")
        return result

    def _handle_pause_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle pause command from server."""
        logger.info(f"Executing pause command")
        self.agent.mq_handler.set_consuming(False)
        self.agent.set_agent_state('internal_state', 'paused')
        return {"output": f"Agent {self.agent.agent_name} paused."}

    def _handle_resume_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resume command from server."""
        logger.info(f"Executing resume command")

        self.agent.mq_handler.set_consuming(True)
        if self.agent.agent_state.get_state('internal_state') == 'paused':
            self.agent.set_agent_state('internal_state', 'idle')
        else:
            logger.warning(f"Agent asked to resume, but is not paused")
        return {"output": "Agent resumed if not already running"}

    def _handle_shutdown_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle shutdown command from server."""
        logger.info(f"Executing shutdown command")
        self.agent._shutdown_requested = True
        self.agent.set_agent_state('internal_state', 'shutting_down')
        logger.info("Shutdown requested flag set. Agent loop will handle cleanup.")
        return {"output": f"Shutdown initiated."}

    def _handle_status_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status command from server."""
        logger.info(f"Handling status command")
        status = self.agent.state.get_state()
        return {"output": f"Agent status: {json.dumps(status)}"}