"""Manages the internal state of the agent, providing thread-safe access and updates."""
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
import logging
import asyncio
from shared_models import setup_logging

# Configure logging
setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__) # Get logger for this module


class AgentState:
    """
    Manages the agent's state in a thread-safe manner.
    Provides methods to get and set various state attributes.
    Automatically updates 'last_updated' timestamp on any change.
    Handles internal state logic based on component statuses.
    Notifies registered listeners of state changes.
    """
    def __init__(self, agent_id: str, agent_name: str):
        self._state = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "internal_state": "initializing", # e.g., initializing, idle, busy, paused, shutting_down, error
            "registration_status": "unregistered", # e.g., unregistered, registering, registered, error
            "grpc_status": "disconnected", # e.g., disconnected, connecting, connected, registered, unavailable, error, shutdown
            "message_queue_status": "disconnected", # e.g., disconnected, connecting, connected, error
            "llm_client_status": "not_configured", # e.g., not_configured, configured, error
            "last_error": None,
            "last_updated": datetime.now().isoformat(),
            "metrics": {}
        }

        self._listeners: List[Callable[[Dict[str, Any]], None]] = [] # List to hold listener callbacks

    async def register_listener(self, listener: Callable[[Dict[str, Any]], None]):
        """Register a callback function to be notified of state changes."""

        if listener not in self._listeners:
            self._listeners.append(listener)
            logger.debug(f"Registered listener: {listener.__name__}")

    async def unregister_listener(self, listener: Callable[[Dict[str, Any]], None]):
        """Unregister a callback function."""

        try:
            self._listeners.remove(listener)
            logger.debug(f"Unregistered listener: {listener.__name__}")
        except ValueError:
            logger.warning(f"Attempted to unregister a non-existent listener: {listener.__name__}")

    async def _notify_listeners(self,state_snapshot: dict[str, Any]):
        """Notify all registered listeners about the state change."""
        # Get a snapshot of the state to pass to listeners
        logger.info(f"Notifying listeners of state change: {state_snapshot}")

        listeners_to_notify = self._listeners[:] 
        
        tasks = []
        for listener in listeners_to_notify:
            try:
                logger.info(f"Notifying listener: {listener.__name__}")
                # Check if the listener is a coroutine function
                if asyncio.iscoroutinefunction(listener):
                    # Schedule coroutine listeners
                    tasks.append(asyncio.create_task(listener(state_snapshot)))
                else:
                    # Call sync listeners directly (consider running in executor if they block)
                    listener(state_snapshot)
            except Exception as e:
                logger.error(f"Error scheduling/calling state listener {listener.__name__}: {e}", exc_info=True)

        # Wait for all scheduled async listeners to complete (optional, depends on requirements)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)



    async def _update_internal_state(self) -> bool:
        """Internal method to determine the overall agent state based on component statuses."""
        # State Priority (Highest to Lowest): shutting_down > paused > error > initializing > busy > idle

        current_internal = self._state.get("internal_state")
        new_internal = current_internal

        # 1. Preserve critical manual states
        if current_internal in ["shutting_down", "paused", "error"]:
            return False # These states are set explicitly and shouldn't be overridden by component status

        # 2. Check for error states in components
        has_error = any(status in ["error", "failed", "unavailable"] for status in [
            self._state.get("registration_status"),
            self._state.get("grpc_status"),
            self._state.get("message_queue_status"),
            self._state.get("llm_client_status")
        ]) or self._state.get("last_error")

        if has_error:
            if current_internal != "error":
                self._state["internal_state"] = "error"
                return True
            return False # Already in error state

        # 3. Check if initializing (based on registration)
        is_initializing = self._state.get("registration_status") in ["unregistered", "registering"]
        if is_initializing:
            if current_internal != "initializing":
                self._state["internal_state"] = "initializing"
                return True
            return False # Already initializing

        # 4. If registered and not busy, default to idle
        is_registered = self._state.get("registration_status") == "registered"
        if is_registered and current_internal != "busy": # Don't override busy state
            if current_internal != "idle":
                self._state["internal_state"] = "idle"
                return True

        return False # No state change based on this logic

    # This method modifies internal state
    async def _set_key_value(self, key: str, value: Any):
        """Set a specific state value"""
        logger.info(f"{key}={value}")
        self._state[key] = value
        self._state["last_updated"] = datetime.now().isoformat()

    async def get_state(self, key: Optional[str] = None) -> Any:
        """Get the entire state dictionary or a specific value by key."""
        if key:
            return self._state.get(key)
        return self._state

    async def set_state(self, key: str, value: Any) -> bool:
        """Set a specific state value. Returns True if the value was changed."""
        changed = False
        notify = False # Flag to track if listeners should be notified
        internal_changed = False


        current_value = self._state.get(key)
        needs_update = key not in self._state or current_value != value

        if needs_update:
            await self._set_key_value(key, value) # Use the async internal setter
            changed = True
            notify = True # Mark for notification

            # Update internal state if a component status changed
            if key in ["registration_status", "grpc_status", "message_queue_status", "llm_client_status", "last_error"]:
                internal_changed = await self._update_internal_state()
                # Notify even if only internal state changed
                if internal_changed:
                    notify = True
        logger.info(f"Notify={notify}")

        if notify:
            # Schedule the notification task
            state_snapshot = await self.get_full_status_for_update() # Use the method that prepares the update format

            asyncio.create_task(self._notify_listeners(state_snapshot))


        return changed or internal_changed # Return True if either the value or internal state changed

    # --- Specific State Setters (now async) --- 
    
    async def set_internal_state(self, state: str) -> bool:
        """Explicitly set the internal_state (e.g., busy, paused)."""
        return await self.set_state("internal_state", state)

    async def set_registration_status(self, status: str) -> bool:
        """Set the registration status."""
        return await self.set_state("registration_status", status)

    async def set_grpc_status(self, status: str) -> bool:
        """Set the gRPC connection status."""
        return await self.set_state("grpc_status", status)

    async def set_message_queue_status(self, status: str) -> bool:
        """Set the Message Queue connection status."""
        return await self.set_state("message_queue_status", status)

    async def set_llm_client_status(self, status: str) -> bool:
        """Set the LLM client status."""
        return await self.set_state("llm_client_status", status)

    async def set_last_error(self, error_message: Optional[str]) -> bool:
        """Set the last error message. Setting to None clears the error."""
        return await self.set_state("last_error", error_message)


    async def get_full_status_for_update(self) -> dict[str, Any]:
        """Return consolidated status dictionary for server updates."""

        # Combine core state and metrics
        status_update = self._state.copy()
        # Ensure metrics are included directly, not nested under 'metrics'
        metrics = status_update.pop('metrics', {})
        status_update.update(metrics)
        return status_update

    # These methods read internal states
    async def get_agent_id(self) -> str:
        """Get the agent ID."""

        return self._state.get("agent_id")

    async def get_agent_name(self) -> str:
        """Get the agent name."""
        return self._state.get("agent_name")

    async def update_internal_state_based_on_components(self) -> bool:
        """
        Public method to update the internal state based on component statuses.
        This is a wrapper around the internal _update_internal_state method.
        
        Returns:
            bool: True if the state was changed, False otherwise
        """
        notify = False
        changed = False

        changed = await self._update_internal_state()
        if changed:
            self._state["last_updated"] = datetime.now().isoformat()
            notify = True

        if notify:
            logger.debug("Internal state updated based on components. Notifying listeners.")
            state_snapshot = await self.get_full_status_for_update() # Use the method that prepares the update format
            asyncio.create_task(self._notify_listeners(state_snapshot))

        return changed
