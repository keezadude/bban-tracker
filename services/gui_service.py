"""
GUIService implementation for BBAN-Tracker Event-Driven Architecture.

This service manages the GUI state and publishes events when users interact
with the interface. It acts as a bridge between the Qt GUI and the event-driven
backend services.
"""

import time
from typing import Optional, Dict, Any, Callable

from ..core.interfaces import IGUIService, IEventBroker
from ..core.events import (
    TrackingDataUpdated, TrackingStarted, TrackingStopped, TrackingError,
    ProjectionClientConnected, ProjectionClientDisconnected,
    PerformanceMetric, SystemShutdown,
    StartTracking, StopTracking, ChangeTrackerSettings, ChangeRealSenseSettings,
    ChangeCropSettings, CalibrateTracker, ProjectionConfigUpdated
)


class GUIService(IGUIService):
    """
    Service that manages GUI state and user interactions.
    
    This service:
    - Manages the current page/screen state
    - Publishes events when users interact with controls
    - Subscribes to status updates from other services
    - Provides notification and dialog capabilities
    - Bridges Qt GUI to the event-driven architecture
    """
    
    def __init__(self, event_broker: IEventBroker):
        """
        Initialize the GUI service with dependency injection.
        
        Args:
            event_broker: Central event broker for communication
        """
        self._event_broker = event_broker
        
        # Service state
        self._running = False
        self._current_page = "system_hub"
        
        # GUI state tracking
        self._tracking_active = False
        self._projection_connected = False
        self._last_frame_info = None
        self._performance_metrics = {}
        
        # Callback registrations for GUI updates
        self._notification_callback: Optional[Callable[[str, int], None]] = None
        self._error_dialog_callback: Optional[Callable[[str, str], None]] = None
        self._page_update_callback: Optional[Callable[[dict], None]] = None
        
        # Subscribe to relevant events
        self._setup_event_subscriptions()
    
    def _setup_event_subscriptions(self):
        """Set up subscriptions to events this service handles."""
        # Tracking service events
        self._event_broker.subscribe(TrackingStarted, self._handle_tracking_started)
        self._event_broker.subscribe(TrackingStopped, self._handle_tracking_stopped)
        self._event_broker.subscribe(TrackingError, self._handle_tracking_error)
        self._event_broker.subscribe(TrackingDataUpdated, self._handle_tracking_data)
        
        # Projection service events
        self._event_broker.subscribe(ProjectionClientConnected, self._handle_projection_connected)
        self._event_broker.subscribe(ProjectionClientDisconnected, self._handle_projection_disconnected)
        
        # Performance monitoring
        self._event_broker.subscribe(PerformanceMetric, self._handle_performance_metric)
        
        # System events
        self._event_broker.subscribe(SystemShutdown, self._handle_shutdown)
    
    # ==================== SERVICE INTERFACE ==================== #
    
    def start(self) -> None:
        """Start the GUI service."""
        if self._running:
            return
            
        self._running = True
        print("[GUIService] Service started")
    
    def stop(self) -> None:
        """Stop the GUI service."""
        if not self._running:
            return
            
        self._running = False
        print("[GUIService] Service stopped")
    
    def is_running(self) -> bool:
        """Return True if the service is active."""
        return self._running
    
    def get_health_status(self) -> dict:
        """Return health and status information."""
        return {
            'service_running': self._running,
            'current_page': self._current_page,
            'tracking_active': self._tracking_active,
            'projection_connected': self._projection_connected,
            'last_frame_info': self._last_frame_info
        }
    
    def show_page(self, page_name: str) -> None:
        """Switch to the specified page/screen."""
        self._current_page = page_name
        self._notify_page_update()
        print(f"[GUIService] Switched to page: {page_name}")
    
    def get_current_page(self) -> str:
        """Return the name of the currently active page."""
        return self._current_page
    
    def show_notification(self, message: str, duration_ms: int = 3000) -> None:
        """Display a transient notification to the user."""
        if self._notification_callback:
            self._notification_callback(message, duration_ms)
        else:
            print(f"[GUIService] Notification: {message}")
    
    def show_error_dialog(self, title: str, message: str) -> None:
        """Display a modal error dialog."""
        if self._error_dialog_callback:
            self._error_dialog_callback(title, message)
        else:
            print(f"[GUIService] Error Dialog - {title}: {message}")
    
    # ==================== GUI CALLBACK REGISTRATION ==================== #
    
    def register_notification_callback(self, callback: Callable[[str, int], None]) -> None:
        """Register callback for showing notifications."""
        self._notification_callback = callback
    
    def register_error_dialog_callback(self, callback: Callable[[str, str], None]) -> None:
        """Register callback for showing error dialogs."""
        self._error_dialog_callback = callback
    
    def register_page_update_callback(self, callback: Callable[[dict], None]) -> None:
        """Register callback for page state updates."""
        self._page_update_callback = callback
    
    # ==================== USER ACTION PUBLISHERS ==================== #
    
    def request_start_tracking(self, dev_mode: bool = False, cam_src: int = 0, video_path: Optional[str] = None) -> None:
        """Publish event to start tracking."""
        self._event_broker.publish(StartTracking(
            dev_mode=dev_mode,
            cam_src=cam_src,
            video_path=video_path
        ))
    
    def request_stop_tracking(self) -> None:
        """Publish event to stop tracking."""
        self._event_broker.publish(StopTracking())
    
    def request_calibration(self) -> None:
        """Publish event to calibrate tracker."""
        self._event_broker.publish(CalibrateTracker())
    
    def update_tracker_settings(self, **kwargs) -> None:
        """Publish event to update tracker detection settings."""
        self._event_broker.publish(ChangeTrackerSettings(**kwargs))
    
    def update_realsense_settings(self, **kwargs) -> None:
        """Publish event to update RealSense camera settings."""
        self._event_broker.publish(ChangeRealSenseSettings(**kwargs))
    
    def update_crop_settings(self, enabled: bool, x1: int, y1: int, x2: int, y2: int) -> None:
        """Publish event to update crop settings."""
        self._event_broker.publish(ChangeCropSettings(
            enabled=enabled, x1=x1, y1=y1, x2=x2, y2=y2
        ))
    
    def update_projection_config(self, width: int, height: int) -> None:
        """Publish event to update projection configuration."""
        self._event_broker.publish(ProjectionConfigUpdated(
            width=width, height=height
        ))
    
    def request_system_shutdown(self) -> None:
        """Publish event to shutdown the entire system."""
        self._event_broker.publish(SystemShutdown())
    
    # ==================== EVENT HANDLERS ==================== #
    
    def _handle_tracking_started(self, event: TrackingStarted) -> None:
        """Handle tracking started event."""
        self._tracking_active = True
        self._notify_page_update()
        self.show_notification(f"Tracking started with {event.camera_type}")
    
    def _handle_tracking_stopped(self, event: TrackingStopped) -> None:
        """Handle tracking stopped event."""
        self._tracking_active = False
        self._last_frame_info = None
        self._notify_page_update()
        self.show_notification(f"Tracking stopped: {event.reason}")
    
    def _handle_tracking_error(self, event: TrackingError) -> None:
        """Handle tracking error event."""
        if not event.recoverable:
            self._tracking_active = False
            self._notify_page_update()
        
        self.show_error_dialog("Tracking Error", event.error_message)
    
    def _handle_tracking_data(self, event: TrackingDataUpdated) -> None:
        """Handle new tracking data (used for live updates)."""
        self._last_frame_info = {
            'frame_id': event.frame_id,
            'timestamp': event.timestamp,
            'bey_count': len(event.beys),
            'hit_count': len([h for h in event.hits if h.is_new_hit])
        }
        # Don't notify page update for every frame - too frequent
    
    def _handle_projection_connected(self, event: ProjectionClientConnected) -> None:
        """Handle projection client connected event."""
        self._projection_connected = True
        self._notify_page_update()
        self.show_notification(f"Unity client connected: {event.client_address}")
    
    def _handle_projection_disconnected(self, event: ProjectionClientDisconnected) -> None:
        """Handle projection client disconnected event."""
        self._projection_connected = False
        self._notify_page_update()
        self.show_notification(f"Unity client disconnected: {event.reason}")
    
    def _handle_performance_metric(self, event: PerformanceMetric) -> None:
        """Handle performance metric updates."""
        self._performance_metrics[f"{event.source_service}_{event.metric_name}"] = {
            'value': event.value,
            'unit': event.unit,
            'timestamp': event.timestamp
        }
        # Performance metrics could be used to update status displays
    
    def _handle_shutdown(self, event: SystemShutdown) -> None:
        """Handle system shutdown event."""
        self.stop()
    
    # ==================== INTERNAL HELPERS ==================== #
    
    def _notify_page_update(self) -> None:
        """Notify registered callback about page state changes."""
        if self._page_update_callback:
            state = {
                'current_page': self._current_page,
                'tracking_active': self._tracking_active,
                'projection_connected': self._projection_connected,
                'last_frame_info': self._last_frame_info,
                'performance_metrics': self._performance_metrics.copy()
            }
            self._page_update_callback(state)
    
    # ==================== STATE ACCESSORS FOR GUI ==================== #
    
    def get_current_state(self) -> dict:
        """Get current state for GUI updates."""
        return {
            'current_page': self._current_page,
            'tracking_active': self._tracking_active,
            'projection_connected': self._projection_connected,
            'last_frame_info': self._last_frame_info,
            'performance_metrics': self._performance_metrics.copy()
        }
    
    def get_performance_metric(self, service: str, metric: str) -> Optional[dict]:
        """Get a specific performance metric."""
        key = f"{service}_{metric}"
        return self._performance_metrics.get(key)
    
    def get_tracking_fps(self) -> float:
        """Get current tracking FPS if available."""
        metric = self.get_performance_metric("TrackingService", "tracking_fps")
        return metric['value'] if metric else 0.0
    
    def get_projection_status(self) -> dict:
        """Get projection service status."""
        return {
            'connected': self._projection_connected,
            'packets_per_second': self.get_performance_metric("ProjectionService", "projection_packets_per_second"),
            'send_latency': self.get_performance_metric("ProjectionService", "projection_send_time")
        } 