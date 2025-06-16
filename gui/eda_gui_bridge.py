"""
EDA GUI Bridge for BBAN-Tracker.

This module provides a bridge between the monolithic GUI components 
and the Event-Driven Architecture, allowing the existing rich UI functionality
to work within the proper architectural pattern.
"""

from typing import Optional, Callable, Dict, Any

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QTimer, pyqtSignal, QObject

from ..core.interfaces import IGUIService
from .main_gui import MainWindow as MonolithicMainWindow


class EDAGUIBridge(QObject):
    """
    Bridge between the monolithic GUI and the EDA GUIService.
    
    This class wraps the monolithic MainWindow and forwards its actions
    to the EDA event system via the GUIService, while also handling
    updates from the event system back to the GUI.
    """
    
    # Qt signals for cross-thread communication
    notification_requested = pyqtSignal(str, int)  # message, duration_ms
    error_dialog_requested = pyqtSignal(str, str)  # title, message
    state_update_received = pyqtSignal(dict)       # state dict
    
    def __init__(self, gui_service: IGUIService):
        super().__init__()
        self._gui_service = gui_service
        self._main_window: Optional[MonolithicMainWindow] = None
        
        # Connect bridge signals to handlers
        self.notification_requested.connect(self._handle_notification_signal)
        self.error_dialog_requested.connect(self._handle_error_dialog_signal)
        self.state_update_received.connect(self._handle_state_update_signal)
        
        # Register callbacks with GUI service
        self._setup_gui_service_callbacks()
    
    def create_main_window(self, dev_mode: bool = False, cam_src: int = 0) -> MonolithicMainWindow:
        """Create and configure the monolithic main window."""
        # Create the monolithic main window
        self._main_window = MonolithicMainWindow(dev_mode=dev_mode, cam_src=cam_src)
        
        # Override the monolithic GUI's internal tracking worker with EDA events
        self._setup_eda_integration()
        
        return self._main_window
    
    def _setup_gui_service_callbacks(self):
        """Register callbacks with the GUI service for updates."""
        self._gui_service.register_notification_callback(self._gui_service_notification)
        self._gui_service.register_error_dialog_callback(self._gui_service_error_dialog)
        self._gui_service.register_page_update_callback(self._gui_service_state_update)
    
    def _setup_eda_integration(self):
        """Set up integration points between monolithic GUI and EDA services."""
        if not self._main_window:
            return
        
        # Override tracking actions to use EDA events instead of direct worker calls
        self._override_tracking_actions()
        
        # Override projection actions to use EDA events
        self._override_projection_actions()
        
        # Set up periodic state sync
        self._setup_periodic_sync()
    
    def _override_tracking_actions(self):
        """Override tracking-related actions to use EDA events."""
        if not self._main_window:
            return
        
        # Find the Free Play page and override its tracking methods
        free_play_page = getattr(self._main_window, '_free_play', None)
        if free_play_page:
            # Override start_tracking to use EDA events
            original_start = free_play_page.start_tracking
            def eda_start_tracking():
                self._gui_service.request_start_tracking(
                    dev_mode=getattr(free_play_page, '_dev_mode', True),
                    cam_src=getattr(free_play_page, '_cam_src', 0)
                )
                # Don't call original_start - let EDA handle it
            free_play_page.start_tracking = eda_start_tracking
            
            # Override stop_tracking to use EDA events
            original_stop = free_play_page.stop_tracking
            def eda_stop_tracking():
                self._gui_service.request_stop_tracking()
                # Don't call original_stop - let EDA handle it
            free_play_page.stop_tracking = eda_stop_tracking
        
        # Find the Tracker Setup page and override its calibration methods
        tracker_page = getattr(self._main_window, '_tracker_setup', None)
        if tracker_page:
            # Override calibration to use EDA events
            if hasattr(tracker_page, '_open_calibration_wizard'):
                original_calibrate = tracker_page._open_calibration_wizard
                def eda_calibration_wizard():
                    self._gui_service.request_calibration()
                    # Still open the wizard UI for user interaction
                    original_calibrate()
                tracker_page._open_calibration_wizard = eda_calibration_wizard
    
    def _override_projection_actions(self):
        """Override projection-related actions to use EDA events."""
        if not self._main_window:
            return
        
        # Find the Projection Setup page and override its actions
        projection_page = getattr(self._main_window, '_projection_setup', None)
        if projection_page:
            # Override projection config updates to use EDA events
            if hasattr(projection_page, '_apply_projection'):
                original_apply = projection_page._apply_projection
                def eda_apply_projection():
                    # Extract current width/height from the page
                    width = getattr(projection_page, '_current_width', 1920)
                    height = getattr(projection_page, '_current_height', 1080)
                    self._gui_service.update_projection_config(width, height)
                    # Still call original for UI updates
                    original_apply()
                projection_page._apply_projection = eda_apply_projection
    
    def _setup_periodic_sync(self):
        """Set up periodic synchronization between EDA state and GUI."""
        self._sync_timer = QTimer()
        self._sync_timer.timeout.connect(self._sync_eda_state)
        self._sync_timer.start(1000)  # Sync every second
    
    def _sync_eda_state(self):
        """Synchronize EDA service state with the monolithic GUI."""
        if not self._main_window:
            return
        
        # Get current state from GUI service
        state = self._gui_service.get_current_state()
        
        # Update GUI elements based on EDA state
        if state.get('tracking_active', False):
            # Update tracking indicators
            self._update_tracking_status(True)
        else:
            self._update_tracking_status(False)
        
        if state.get('projection_connected', False):
            # Update projection indicators
            self._update_projection_status(True)
        else:
            self._update_projection_status(False)
    
    def _update_tracking_status(self, active: bool):
        """Update GUI tracking status indicators."""
        # Update status in various pages
        if hasattr(self._main_window, '_status_message'):
            status = "Tracking Active" if active else "Tracking Stopped"
            self._main_window._status_message(status)
    
    def _update_projection_status(self, connected: bool):
        """Update GUI projection status indicators."""
        # Update projection status indicators
        if hasattr(self._main_window, '_status_message'):
            status = "Unity Connected" if connected else "Unity Disconnected"
            self._main_window._status_message(status)
    
    # ==================== GUI SERVICE CALLBACK HANDLERS ==================== #
    
    def _gui_service_notification(self, message: str, duration_ms: int):
        """Handle notification request from GUI service."""
        # Emit signal to handle in main thread
        self.notification_requested.emit(message, duration_ms)
    
    def _gui_service_error_dialog(self, title: str, message: str):
        """Handle error dialog request from GUI service."""
        # Emit signal to handle in main thread
        self.error_dialog_requested.emit(title, message)
    
    def _gui_service_state_update(self, state: Dict[str, Any]):
        """Handle state update from GUI service."""
        # Emit signal to handle in main thread
        self.state_update_received.emit(state)
    
    # ==================== SIGNAL HANDLERS (MAIN THREAD) ==================== #
    
    def _handle_notification_signal(self, message: str, duration_ms: int):
        """Handle notification signal in main thread."""
        if self._main_window and hasattr(self._main_window, '_toast_manager'):
            self._main_window._toast_manager.show(message, duration_ms)
    
    def _handle_error_dialog_signal(self, title: str, message: str):
        """Handle error dialog signal in main thread."""
        if self._main_window:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self._main_window, title, message)
    
    def _handle_state_update_signal(self, state: Dict[str, Any]):
        """Handle state update signal in main thread."""
        # Update GUI based on EDA service state
        tracking_active = state.get('tracking_active', False)
        projection_connected = state.get('projection_connected', False)
        
        self._update_tracking_status(tracking_active)
        self._update_projection_status(projection_connected)


def create_eda_gui_application(gui_service: IGUIService) -> QApplication:
    """
    Create a QApplication with the monolithic GUI integrated into EDA.
    
    This function creates the Qt application and sets up the bridge between
    the monolithic GUI and the EDA services.
    
    Args:
        gui_service: The EDA GUI service instance
        
    Returns:
        QApplication instance ready for exec()
    """
    # Create Qt application
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    # Apply dark theme
    app.setStyle("Fusion")
    
    # Create the bridge
    bridge = EDAGUIBridge(gui_service)
    
    # Create the main window via the bridge
    main_window = bridge.create_main_window(dev_mode=True, cam_src=0)
    
    # Configure the main window for EDA mode
    main_window.setWindowTitle("BBAN-Tracker - EDA Mode")
    
    # Show the main window
    main_window.show()
    
    # Store bridge reference to prevent garbage collection
    app._eda_bridge = bridge
    
    print("[EDAGUIBridge] ✅ Monolithic GUI integrated with EDA services")
    
    return app 