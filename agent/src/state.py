"""Manages the internal state of the agent, providing thread-safe access and updates."""
import threading
from datetime import datetime
from typing import Dict, Any, Optional

class AgentState:
    """
    Manages the agent's state in a thread-safe manner.
    Provides methods to get and set various state attributes.
    Automatically updates 'last_updated' timestamp on any change.
    Handles internal state logic based on component statuses.
    """
    def __init__(self, agent_id: str, agent_name: str):
        self._state = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "internal_state": "initializing", # e.g., initializing, idle, busy, paused, shutting_down, error
            "registration_status": "unregistered", # e.g., unregistered, registering, registered, error
            "grpc_status": "disconnected", # e.g., disconnected, connecting, connected, registered, unavailable, error, shutdown
            "mq_status": "disconnected", # e.g., disconnected, connecting, connected, error
            "llm_status": "not_configured", # e.g., not_configured, configured, error
            "last_error": None,
            "last_updated": datetime.now().isoformat(),
            "metrics": {}
        }
        self._lock = threading.Lock()

    def _update_timestamp(self):
        """Internal method to update the last_updated timestamp."""
        self._state["last_updated"] = datetime.now().isoformat()

    def _update_internal_state(self):
        """Internal method to determine the overall agent state based on component statuses."""
        # This logic determines the primary 'internal_state'
        # Priority: error > shutting_down > paused > initializing > busy > idle
        current_internal = self._state.get("internal_state")

        # Don't override critical states like shutting_down or paused unless explicitly changed
        if current_internal in ["shutting_down", "paused"]:
            return False # No change needed based on component status

        # Check for error states in components
        if any(status in ["error", "failed"] for status in [self._state.get("registration_status"), self._state.get("grpc_status"), self._state.get("mq_status"), self._state.get("llm_status")]) or self._state.get("last_error"):
            if current_internal != "error":
                self._state["internal_state"] = "error"
                return True
            return False # Already in error state

        # Check if still initializing (based on registration)
        if self._state.get("registration_status") in ["unregistered", "registering"]:
            if current_internal != "initializing":
                self._state["internal_state"] = "initializing"
                return True
            return False # Already initializing

        # If registered and components are okay, assume idle (busy state needs explicit setting)
        if self._state.get("registration_status") == "registered":
            if current_internal not in ["idle", "busy"]: # Don't override busy
                self._state["internal_state"] = "idle"
                return True

        return False # No change based on this logic

    def get_state(self, key: Optional[str] = None) -> Any:
        """Get the entire state dictionary or a specific value by key."""
        with self._lock:
            if key:
                return self._state.get(key)
            return self._state.copy() # Return a copy to prevent external modification

    def set_state(self, key: str, value: Any) -> bool:
        """Set a specific state value. Returns True if the value was changed."""
        changed = False
        with self._lock:
            if key in self._state and self._state[key] != value:
                self._state[key] = value
                self._update_timestamp()
                changed = True
                # Update internal state if a component status changed
                if key in ["registration_status", "grpc_status", "mq_status", "llm_status", "last_error"]:
                    internal_changed = self._update_internal_state()
                    changed = changed or internal_changed # Report change if either value or internal state changed
            elif key not in self._state:
                 # Allow adding new keys, maybe log a warning?
                 self._state[key] = value
                 self._update_timestamp()
                 changed = True
        return changed

    # --- Specific State Setters --- 
    # These provide clearer intent and potentially encapsulate logic

    def set_internal_state(self, state: str) -> bool:
        """Explicitly set the internal_state (e.g., busy, paused)."""
        return self.set_state("internal_state", state)

    def set_registration_status(self, status: str) -> bool:
        """Set the registration status."""
        return self.set_state("registration_status", status)

    def set_grpc_status(self, status: str) -> bool:
        """Set the gRPC connection status."""
        return self.set_state("grpc_status", status)

    def set_mq_status(self, status: str) -> bool:
        """Set the Message Queue connection status."""
        return self.set_state("mq_status", status)

    def set_llm_status(self, status: str) -> bool:
        """Set the LLM client status."""
        return self.set_state("llm_status", status)

    def set_last_error(self, error_message: Optional[str]) -> bool:
        """Set the last error message. Setting to None clears the error."""
        return self.set_state("last_error", error_message)

    def update_metrics(self, new_metrics: Dict[str, Any]) -> bool:
        """Update the metrics dictionary with new values."""
        changed = False
        with self._lock:
            # Simple merge, new_metrics overwrite existing keys
            for k, v in new_metrics.items():
                if self._state["metrics"].get(k) != v:
                    self._state["metrics"][k] = v
                    changed = True
            if changed:
                self._update_timestamp()
        return changed

    def get_metrics(self) -> Dict[str, Any]:
        """Get a copy of the current metrics."""
        with self._lock:
            return self._state["metrics"].copy()

    def get_full_status_for_update(self) -> Dict[str, Any]:
        """Get a consolidated status dictionary suitable for sending updates."""
        with self._lock:
            # Combine core state and metrics
            status_update = self._state.copy()
            # Ensure metrics are included directly, not nested under 'metrics'
            metrics = status_update.pop('metrics', {})
            status_update.update(metrics)
            return status_update
