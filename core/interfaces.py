"""
Service interface definitions for the BBAN-Tracker Event-Driven Architecture.

This module defines the abstract interfaces that all services must implement.
These interfaces establish clear contracts for service lifecycle management,
dependency injection, and inter-service communication patterns.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Any, Callable


class IService(ABC):
    """Base interface for all services in the EDA system."""
    
    @abstractmethod
    def start(self) -> None:
        """Start the service and any background workers."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Gracefully stop the service and clean up resources."""
        pass
    
    @abstractmethod
    def is_running(self) -> bool:
        """Return True if the service is currently active."""
        pass
    
    @abstractmethod
    def get_health_status(self) -> dict:
        """Return health/status information for monitoring."""
        pass


class ITrackingService(IService):
    """Interface for the tracking service that manages hardware and detection."""
    
    @abstractmethod
    def get_camera_info(self) -> dict:
        """Return information about the active camera."""
        pass
    
    @abstractmethod
    def get_current_settings(self) -> dict:
        """Return current tracking and camera settings."""
        pass
    
    @abstractmethod
    def get_latest_frame_info(self) -> Optional[dict]:
        """Return metadata about the most recent processed frame."""
        pass


class IGUIService(IService):
    """Interface for the GUI service that manages user interface."""
    
    @abstractmethod
    def show_page(self, page_name: str) -> None:
        """Switch to the specified page/screen."""
        pass
    
    @abstractmethod
    def get_current_page(self) -> str:
        """Return the name of the currently active page."""
        pass
    
    @abstractmethod
    def show_notification(self, message: str, duration_ms: int = 3000) -> None:
        """Display a transient notification to the user."""
        pass
    
    @abstractmethod
    def show_error_dialog(self, title: str, message: str) -> None:
        """Display a modal error dialog."""
        pass


class IProjectionService(IService):
    """Interface for the projection service that manages Unity client communication."""
    
    @abstractmethod
    def get_connection_status(self) -> bool:
        """Return True if Unity client is connected."""
        pass
    
    @abstractmethod
    def get_connected_client_info(self) -> Optional[dict]:
        """Return information about the connected Unity client."""
        pass
    
    @abstractmethod
    def send_projection_command(self, command: str, data: Any = None) -> bool:
        """Send a command to the Unity client. Returns True if successful."""
        pass


# ==================== HARDWARE ABSTRACTION INTERFACES ==================== #

class ITrackerHardware(ABC):
    """Generic interface for tracking camera hardware."""
    
    @abstractmethod
    def initialize(self, config: dict) -> bool:
        """Initialize the hardware with the given configuration."""
        pass
    
    @abstractmethod
    def start_stream(self) -> bool:
        """Start the camera stream."""
        pass
    
    @abstractmethod
    def stop_stream(self) -> None:
        """Stop the camera stream."""
        pass
    
    @abstractmethod
    def get_latest_frame(self) -> Optional[Any]:
        """Get the most recent frame data."""
        pass
    
    @abstractmethod
    def read_next_frame(self) -> Optional[Any]:
        """Block until a new frame is available and return it."""
        pass
    
    @abstractmethod
    def set_option(self, option_name: str, value: Any) -> bool:
        """Set a hardware-specific option. Returns True if successful."""
        pass
    
    @abstractmethod
    def get_option(self, option_name: str) -> Any:
        """Get the current value of a hardware option."""
        pass
    
    @abstractmethod
    def get_supported_options(self) -> dict:
        """Return a dict of supported options and their valid ranges."""
        pass
    
    @abstractmethod
    def get_hardware_info(self) -> dict:
        """Return information about the hardware (model, serial, etc.)."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if hardware is connected and responsive."""
        pass


class IProjectionAdapter(ABC):
    """Generic interface for communicating with projection clients."""
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the projection client."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the projection client."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if connected to the projection client."""
        pass
    
    @abstractmethod
    def send_tracking_data(self, frame_id: int, beys: list, hits: list) -> bool:
        """Send tracking data to the projection client."""
        pass
    
    @abstractmethod
    def send_projection_config(self, width: int, height: int) -> bool:
        """Send projection configuration to the client."""
        pass
    
    @abstractmethod
    def receive_commands(self) -> list:
        """Check for and return any commands from the projection client."""
        pass
    
    @abstractmethod
    def get_client_info(self) -> Optional[dict]:
        """Return information about the connected client."""
        pass


# ==================== EVENT BROKER INTERFACE ==================== #

class IEventBroker(ABC):
    """Interface for the central event broker that manages pub/sub communication."""
    
    @abstractmethod
    def publish(self, event: Any) -> None:
        """Publish an event to all interested subscribers."""
        pass
    
    @abstractmethod
    def subscribe(self, event_type: type, handler: Callable[[Any], None]) -> str:
        """Subscribe to events of a specific type. Returns subscription ID."""
        pass
    
    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from events. Returns True if successful."""
        pass
    
    @abstractmethod
    def get_subscriber_count(self, event_type: type) -> int:
        """Return the number of active subscribers for an event type."""
        pass
    
    @abstractmethod
    def get_event_statistics(self) -> dict:
        """Return statistics about event processing (throughput, errors, etc.)."""
        pass
    
    @abstractmethod
    def clear_all_subscriptions(self) -> None:
        """Remove all subscriptions (used for shutdown)."""
        pass


# ==================== DEPENDENCY INJECTION CONTAINER ==================== #

class IDependencyContainer(ABC):
    """Interface for dependency injection container."""
    
    @abstractmethod
    def register_singleton(self, interface_type: type, implementation: Any) -> None:
        """Register a singleton instance for an interface type."""
        pass
    
    @abstractmethod
    def register_transient(self, interface_type: type, factory: Callable) -> None:
        """Register a factory function for creating transient instances."""
        pass
    
    @abstractmethod
    def resolve(self, interface_type: type) -> Any:
        """Resolve an instance of the requested interface type."""
        pass
    
    @abstractmethod
    def is_registered(self, interface_type: type) -> bool:
        """Return True if the interface type is registered."""
        pass 