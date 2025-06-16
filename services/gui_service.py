"""
GUIService implementation for BBAN-Tracker Event-Driven Architecture.

This service manages the GUI state and publishes events when users interact
with the interface. It acts as a bridge between the Qt GUI and the event-driven
backend services.
"""

import time
from typing import Optional, Dict, Any, Callable, TYPE_CHECKING

from PySide6.QtCore import QObject, pyqtSignal, QApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from ..core.interfaces import IGUIService, IEventBroker
from ..core.events import (
    TrackingDataUpdated, TrackingStarted, TrackingStopped, TrackingError,
    ProjectionClientConnected, ProjectionClientDisconnected,
    PerformanceMetric, SystemShutdown,
    StartTracking, StopTracking, ChangeTrackerSettings, ChangeRealSenseSettings,
    ChangeCropSettings, CalibrateTracker, ProjectionConfigUpdated
)

# Import our modular UI panels
from ..gui.main_window import MainWindow, create_main_window
from ..gui.tracking_panel import TrackerSetupPage
from ..gui.projection_panel import ProjectionSetupPage
from ..gui.system_hub_panel import SystemHubPage
from ..gui.free_play_panel import FreePlayPage

if TYPE_CHECKING:
    pass

class GUIEventBridge(QObject):
    """Qt signal bridge for GUI updates from the event system."""
    
    # Define Qt signals for cross-thread GUI updates
    tracking_started = pyqtSignal(str)  # camera_type
    tracking_stopped = pyqtSignal(str)  # reason
    tracking_error = pyqtSignal(str, str, bool)  # title, message, recoverable
    tracking_data_updated = pyqtSignal(dict)  # frame info
    projection_connected = pyqtSignal(str)  # client_address
    projection_disconnected = pyqtSignal(str)  # reason
    show_notification = pyqtSignal(str, int)  # message, duration_ms
    show_error_dialog = pyqtSignal(str, str)  # title, message
    page_state_updated = pyqtSignal(dict)  # state dict


class GUIService(IGUIService):
    """
    Service that manages GUI state and user interactions.
    
    This service:
    - Creates and manages the MainWindow and UI panels
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
        
        # Qt Application and Windows
        self._qt_app: Optional[QApplication] = None
        self._main_window: Optional[MainWindow] = None
        self._gui_bridge: Optional[GUIEventBridge] = None
        
        # UI Panel references
        self._panels = {}
        
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
        """Start the GUI service and create the main window."""
        if self._running:
            return
            
        self._running = True
        print("[GUIService] Starting GUI service...")
        
        # Create or get Qt application
        self._qt_app = QApplication.instance()
        if self._qt_app is None:
            self._qt_app = QApplication([])
        
        # Create GUI event bridge for cross-thread updates
        self._gui_bridge = GUIEventBridge()
        self._setup_gui_bridge_connections()
        
        # Create main window and panels
        self._create_main_window()
        self._create_ui_panels()
        self._wire_panel_events()
        
        # Show the main window
        self._main_window.show()
        print("[GUIService] GUI service started - main window shown")
    
    def stop(self) -> None:
        """Stop the GUI service."""
        if not self._running:
            return
            
        self._running = False
        
        # Close main window
        if self._main_window:
            self._main_window.close()
            
        print("[GUIService] GUI service stopped")
    
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
            'last_frame_info': self._last_frame_info,
            'qt_app_available': self._qt_app is not None,
            'main_window_visible': self._main_window.isVisible() if self._main_window else False
        }
    
    def get_qt_app(self) -> Optional[QApplication]:
        """Return the Qt application instance."""
        return self._qt_app
    
    def get_main_window(self) -> Optional[MainWindow]:
        """Return the main window instance."""
        return self._main_window
    
    # ==================== PAGE MANAGEMENT ==================== #
    
    def show_page(self, page_name: str) -> None:
        """Switch to the specified page/screen."""
        if self._main_window and page_name in self._panels:
            self._current_page = page_name
            self._main_window.show_page(page_name)
            self._notify_page_update()
            print(f"[GUIService] Switched to page: {page_name}")
    
    def get_current_page(self) -> str:
        """Return the name of the currently active page."""
        return self._current_page
    
    def show_notification(self, message: str, duration_ms: int = 3000) -> None:
        """Display a transient notification to the user."""
        if self._gui_bridge:
            self._gui_bridge.show_notification.emit(message, duration_ms)
        else:
            print(f"[GUIService] Notification: {message}")
    
    def show_error_dialog(self, title: str, message: str) -> None:
        """Display a modal error dialog."""
        if self._gui_bridge:
            self._gui_bridge.show_error_dialog.emit(title, message)
        else:
            print(f"[GUIService] Error Dialog - {title}: {message}")
    
    # ==================== GUI SETUP ==================== #
    
    def _create_main_window(self):
        """Create the main application window."""
        self._main_window = create_main_window(dev_mode=False, cam_src=0)
        self._main_window.setWindowTitle("BBAN-Tracker v2.1 - Event-Driven Architecture")
    
    def _create_ui_panels(self):
        """Create and add UI panels to the main window."""
        # Create System Hub panel
        system_hub = SystemHubPage()
        self._panels['system_hub'] = system_hub
        self._main_window.add_page('system_hub', system_hub)
        
        # Create Tracker Setup panel
        tracker_panel = TrackerSetupPage(self._status_callback, dev_mode=False, cam_src=0)
        self._panels['tracker_setup'] = tracker_panel
        self._main_window.add_page('tracker_setup', tracker_panel)
        
        # Create Projection Setup panel
        projection_panel = ProjectionSetupPage(self._status_callback)
        self._panels['projection_setup'] = projection_panel
        self._main_window.add_page('projection_setup', projection_panel)
        
        # Create Free Play panel
        free_play_panel = FreePlayPage(self._status_callback)
        self._panels['free_play'] = free_play_panel
        self._main_window.add_page('free_play', free_play_panel)
        
        # Start with system hub
        self.show_page('system_hub')
    
    def _wire_panel_events(self):
        """Wire up panel events to publish EDA events."""
        # Wire System Hub navigation
        system_hub = self._panels['system_hub']
        system_hub.set_tracker_callback(lambda: self.show_page('tracker_setup'))
        system_hub.set_projection_callback(lambda: self.show_page('projection_setup'))
        system_hub.set_calibration_callback(self._open_calibration_wizard)
        system_hub.set_free_play_callback(lambda: self.show_page('free_play'))
        
        # Wire Tracker Setup events to EDA events
        tracker_panel = self._panels['tracker_setup']
        self._wire_tracker_panel_events(tracker_panel)
        
        # Wire Projection Setup events
        projection_panel = self._panels['projection_setup']
        self._wire_projection_panel_events(projection_panel)
        
        # Wire Free Play panel events
        free_play_panel = self._panels['free_play']
        self._wire_free_play_panel_events(free_play_panel)
        
        # Wire Free Play navigation
        free_play_panel.set_system_hub_callback(lambda: self.show_page('system_hub'))
        free_play_panel.set_tracker_callback(lambda: self.show_page('tracker_setup'))
        free_play_panel.set_projection_callback(lambda: self.show_page('projection_setup'))
        free_play_panel.set_calibration_callback(self._open_calibration_wizard)
    
    def _wire_tracker_panel_events(self, panel):
        """Wire tracker panel events to publish EDA events."""
        # PHOENIX FINALIS: Set up EDA integration instead of overriding methods
        
        # Configure EDA integration for the panel
        panel.set_eda_integration(
            event_broker=self._event_broker,
            eda_callback=self._create_tracker_eda_callback()
        )
        
        print("[GUIService] Tracker panel EDA integration complete")
    
    def _create_tracker_eda_callback(self):
        """Create EDA callback for tracker panel integration."""
        def tracker_eda_callback(action: str, **kwargs):
            if action == 'update_tracker_settings':
                self.update_tracker_settings(**kwargs)
            elif action == 'update_realsense_settings':
                self.update_realsense_settings(**kwargs)
            elif action == 'update_crop_settings':
                self.update_crop_settings(**kwargs)
            elif action == 'request_start_tracking':
                self.request_start_tracking(**kwargs)
            elif action == 'request_stop_tracking':
                self.request_stop_tracking()
            elif action == 'request_calibration':
                self.request_calibration()
            else:
                print(f"[GUIService] Unknown tracker EDA action: {action}")
        
        return tracker_eda_callback
    
    def _wire_projection_panel_events(self, panel):
        """Wire projection panel events to publish EDA events."""
        # PHOENIX FINALIS: Set up EDA integration instead of overriding methods
        
        # Configure EDA integration for the panel
        panel.set_eda_integration(
            event_broker=self._event_broker,
            eda_callback=self._create_projection_eda_callback()
        )
        
        print("[GUIService] Projection panel EDA integration complete")
    
    def _create_projection_eda_callback(self):
        """Create EDA callback for projection panel integration."""
        def projection_eda_callback(action: str, **kwargs):
            if action == 'update_projection_config':
                self.update_projection_config(**kwargs)
            else:
                print(f"[GUIService] Unknown projection EDA action: {action}")
        
        return projection_eda_callback
    
    def _wire_free_play_panel_events(self, panel):
        """Wire free play panel events to publish EDA events."""
        # PHOENIX FINALIS: Set up EDA integration instead of overriding methods
        
        # Configure EDA integration for the panel
        panel.set_eda_integration(
            event_broker=self._event_broker,
            eda_callback=self._create_free_play_eda_callback()
        )
        
        print("[GUIService] Free Play panel EDA integration complete")
    
    def _create_free_play_eda_callback(self):
        """Create EDA callback for free play panel integration."""
        def free_play_eda_callback(action: str, **kwargs):
            if action == 'request_start_tracking':
                self.request_start_tracking(**kwargs)
            elif action == 'request_stop_tracking':
                self.request_stop_tracking()
            elif action == 'request_calibration':
                self.request_calibration()
            else:
                print(f"[GUIService] Unknown free play EDA action: {action}")
        
        return free_play_eda_callback
    
    def _setup_gui_bridge_connections(self):
        """Set up connections from the GUI bridge to actual GUI updates."""
        if not self._gui_bridge:
            return
        
        # Connect signals to GUI update methods
        self._gui_bridge.show_notification.connect(self._show_notification_impl)
        self._gui_bridge.show_error_dialog.connect(self._show_error_dialog_impl)
        self._gui_bridge.tracking_started.connect(self._on_tracking_started_gui)
        self._gui_bridge.tracking_stopped.connect(self._on_tracking_stopped_gui)
        self._gui_bridge.tracking_error.connect(self._on_tracking_error_gui)
        self._gui_bridge.projection_connected.connect(self._on_projection_connected_gui)
        self._gui_bridge.projection_disconnected.connect(self._on_projection_disconnected_gui)
    
    # ==================== GUI UPDATE IMPLEMENTATIONS ==================== #
    
    def _show_notification_impl(self, message: str, duration_ms: int):
        """Implementation of showing notification in GUI."""
        if self._main_window:
            self._main_window.show_toast(message, duration_ms)
    
    def _show_error_dialog_impl(self, title: str, message: str):
        """Implementation of showing error dialog in GUI."""
        if self._main_window:
            QMessageBox.critical(self._main_window, title, message)
    
    def _on_tracking_started_gui(self, camera_type: str):
        """Handle tracking started in GUI."""
        if 'tracker_setup' in self._panels:
            # Update tracker panel to show tracking is active
            pass
        self.show_notification(f"Tracking started with {camera_type}")
    
    def _on_tracking_stopped_gui(self, reason: str):
        """Handle tracking stopped in GUI."""
        if 'tracker_setup' in self._panels:
            # Update tracker panel to show tracking is stopped
            pass
        self.show_notification(f"Tracking stopped: {reason}")
    
    def _on_tracking_error_gui(self, title: str, message: str, recoverable: bool):
        """Handle tracking error in GUI."""
        if not recoverable:
            self._tracking_active = False
        self._show_error_dialog_impl(title, message)
    
    def _on_projection_connected_gui(self, client_address: str):
        """Handle projection connected in GUI."""
        if 'projection_setup' in self._panels:
            panel = self._panels['projection_setup']
            panel.connection_status.setText("Status: Unity Connected")
            panel.connection_status.setStyleSheet("font-size:14px;color:#88FF88;")
        self.show_notification(f"Unity client connected: {client_address}")
    
    def _on_projection_disconnected_gui(self, reason: str):
        """Handle projection disconnected in GUI."""
        if 'projection_setup' in self._panels:
            panel = self._panels['projection_setup']
            panel.connection_status.setText("Status: Not Connected")
            panel.connection_status.setStyleSheet("font-size:14px;color:#FF8888;")
        self.show_notification(f"Unity client disconnected: {reason}")
    
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
        if self._gui_bridge:
            self._gui_bridge.tracking_started.emit(event.camera_type)
        
        # PHOENIX FINALIS: Update panel status via EDA integration
        if 'tracker_setup' in self._panels:
            self._panels['tracker_setup'].update_tracking_status(True)
        
        # Update system status panel
        if self._main_window:
            self._main_window.update_tracking_status(True, 0.0)
            self._main_window.update_camera_status(True, event.camera_type, 0.0)
        
        self._notify_page_update()
    
    def _handle_tracking_stopped(self, event: TrackingStopped) -> None:
        """Handle tracking stopped event."""
        self._tracking_active = False
        self._last_frame_info = None
        if self._gui_bridge:
            self._gui_bridge.tracking_stopped.emit(event.reason)
        
        # PHOENIX FINALIS: Update panel status via EDA integration
        if 'tracker_setup' in self._panels:
            self._panels['tracker_setup'].update_tracking_status(False)
        
        # Update system status panel
        if self._main_window:
            self._main_window.update_tracking_status(False, 0.0)
            self._main_window.update_camera_status(False)
        
        self._notify_page_update()
    
    def _handle_tracking_error(self, event: TrackingError) -> None:
        """Handle tracking error event."""
        if not event.recoverable:
            self._tracking_active = False
            self._notify_page_update()
        
        if self._gui_bridge:
            self._gui_bridge.tracking_error.emit("Tracking Error", event.error_message, event.recoverable)
    
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
        if self._gui_bridge:
            self._gui_bridge.projection_connected.emit(event.client_address)
        
        # PHOENIX FINALIS: Update panel status via EDA integration
        if 'projection_setup' in self._panels:
            self._panels['projection_setup'].update_projection_status(True)
        
        # Update system status panel
        if self._main_window:
            self._main_window.update_unity_status(True, event.client_address)
        
        self._notify_page_update()
    
    def _handle_projection_disconnected(self, event: ProjectionClientDisconnected) -> None:
        """Handle projection client disconnected event."""
        self._projection_connected = False
        if self._gui_bridge:
            self._gui_bridge.projection_disconnected.emit(event.reason)
        
        # PHOENIX FINALIS: Update panel status via EDA integration
        if 'projection_setup' in self._panels:
            self._panels['projection_setup'].update_projection_status(False)
        
        # Update system status panel
        if self._main_window:
            self._main_window.update_unity_status(False, event.reason)
        
        self._notify_page_update()
    
    def _handle_performance_metric(self, event: PerformanceMetric) -> None:
        """Handle performance metric updates."""
        self._performance_metrics[f"{event.source_service}_{event.metric_name}"] = {
            'value': event.value,
            'unit': event.unit,
            'timestamp': event.timestamp
        }
        
        # Update system status panel with performance metrics
        if self._main_window:
            # Calculate events per second from broker statistics
            events_per_second = 0.0
            total_events = 0
            
            if hasattr(self._event_broker, 'get_event_statistics'):
                stats = self._event_broker.get_event_statistics()
                events_per_second = stats.get('events_per_second', 0.0)
                total_events = stats.get('total_events_published', 0)
            
            self._main_window.update_system_health(events_per_second, total_events)
    
    def _handle_shutdown(self, event: SystemShutdown) -> None:
        """Handle system shutdown event."""
        self.stop()
    
    # ==================== HELPER METHODS ==================== #
    
    def _status_callback(self, message: str):
        """Status callback for panels."""
        if self._main_window:
            self._main_window._status_message(message)
    
    def _open_calibration_wizard(self):
        """Open the calibration wizard."""
        if self._main_window:
            self._main_window.open_calibration_wizard_global()
    
    def _notify_page_update(self) -> None:
        """Notify about page state changes."""
        state = {
            'current_page': self._current_page,
            'tracking_active': self._tracking_active,
            'projection_connected': self._projection_connected,
            'last_frame_info': self._last_frame_info,
            'performance_metrics': self._performance_metrics.copy()
        }
        
        if self._gui_bridge:
            self._gui_bridge.page_state_updated.emit(state)
    
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