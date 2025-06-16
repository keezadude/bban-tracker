"""
BBAN Kiosk Main GUI for BBAN-Tracker.

This module provides the pixel-perfect kiosk GUI implementation that matches
the reference screenshots exactly, with custom polygon-shaped shard buttons
and proper BBAN color scheme.
"""

import time
from typing import Dict, Any, Optional

from PySide6.QtCore import Qt, QTimer, QSize, pyqtSignal, QObject, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QPushButton, QGridLayout, QFrame, QSizePolicy,
    QSpinBox
)
from PySide6.QtGui import QFont, QKeySequence, QShortcut

from ..core.interfaces import IGUIService
from .ui_components.base_page import BasePage
from .ui_components.status_components import ToastManager
from .ui_components.theme_manager import theme
from .ui_components.enhanced_widgets import (
    CyberCard, StatusIndicator, ActionButton, SettingsGroup,
    ShardButton, KioskMainMenu, BackgroundWidget
)


class KioskMainWindow(QMainWindow):
    """Main window with pixel-perfect BBAN kiosk styling matching reference screenshots."""
    
    def __init__(self, gui_service: IGUIService):
        super().__init__()
        
        self._gui_service = gui_service
        self._current_view = "main_menu"
        self._views: Dict[str, QWidget] = {}
        self._developer_mode = False
        
        # Performance tracking timer
        self._performance_timer = QTimer()
        self._performance_timer.timeout.connect(self._update_performance_metrics)
        self._performance_timer.start(1000)  # Update every second
        
        self._setup_main_window()
        self._apply_theme()
        self._setup_kiosk_interface()
        self._create_views()
        self._setup_event_connections()
        self._setup_developer_shortcuts()
        
        print("[KioskMainWindow] BBAN Kiosk GUI initialized with pixel-perfect styling")
    
    def _setup_main_window(self) -> None:
        """Set up the main window properties for kiosk mode."""
        self.setWindowTitle("BeysionXR Kiosk - BBAN Edition")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)
        
        # Enable full-screen kiosk styling
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme.colors.BACKGROUND_DEEP.name()};
                border: none;
            }}
        """)
    
    def _apply_theme(self) -> None:
        """Apply the BBAN theme to the application."""
        app = QApplication.instance()
        if app:
            theme.apply_to_application(app)
    
    def _setup_kiosk_interface(self) -> None:
        """Create the kiosk interface with background and view stack."""
        # Create background widget with angular streaks
        self._background = BackgroundWidget()
        
        # Create central widget with stacked layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Use a layout that allows the background to show through
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create view stack for different screens
        self._view_stack = QStackedWidget()
        self._view_stack.setStyleSheet("QStackedWidget { background: transparent; }")
        main_layout.addWidget(self._view_stack)
        
        # Create toast manager for notifications
        self._toast_manager = ToastManager(self)
    
    def _create_views(self) -> None:
        """Create all kiosk views matching reference designs."""
        # Main Menu View (KioskMainMenu)
        main_menu = KioskMainMenu()
        main_menu.navigate_to_match.connect(lambda: self._navigate_to_view("match_settings"))
        main_menu.navigate_to_freeplay.connect(lambda: self._navigate_to_view("free_play"))
        main_menu.navigate_to_systemhub.connect(lambda: self._navigate_to_view("system_hub"))
        main_menu.exit_requested.connect(self._handle_exit_request)
        
        self._views["main_menu"] = main_menu
        self._view_stack.addWidget(main_menu)
        
        # System Hub View (with BBAN styled shards)
        system_hub = self._create_system_hub_view()
        self._views["system_hub"] = system_hub
        self._view_stack.addWidget(system_hub)
        
        # Enhanced pages for other views
        tracker_setup = KioskTrackerSetupPage(self._gui_service)
        self._views["tracker_setup"] = tracker_setup
        self._view_stack.addWidget(tracker_setup)
        
        projection_setup = KioskProjectionSetupPage(self._gui_service)
        self._views["projection_setup"] = projection_setup
        self._view_stack.addWidget(projection_setup)
        
        options_page = KioskOptionsPage(self._gui_service)
        self._views["options"] = options_page
        self._view_stack.addWidget(options_page)
        
        # Free Play view
        free_play = self._create_free_play_view()
        self._views["free_play"] = free_play
        self._view_stack.addWidget(free_play)
        
        # Match Settings view
        match_settings = self._create_match_settings_view()
        self._views["match_settings"] = match_settings
        self._view_stack.addWidget(match_settings)
        
        # Calibrate view
        calibrate = self._create_calibrate_view()
        self._views["calibrate"] = calibrate
        self._view_stack.addWidget(calibrate)
    
    def _create_system_hub_view(self) -> QWidget:
        """Create the System Hub view with BBAN shards matching SystemHubScreen.tsx."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(32)
        
        # Header with title and back button
        header_layout = QHBoxLayout()
        
        title = QLabel("BeysionXR Kiosk - System Hub")
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                font-family: "Arial";
                font-size: 36px;
                font-weight: 700;
                text-transform: uppercase;
                text-shadow: 0 0 8px {theme.colors.PRIMARY_INTERACTIVE.name()};
            }}
        """)
        
        back_btn = ActionButton("← Main Menu", "ghost")
        back_btn.clicked.connect(lambda: self._navigate_to_view("main_menu"))
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(back_btn)
        
        layout.addLayout(header_layout)
        
        # System Hub shards (2x2 grid) - matching SystemHubScreen.tsx layout
        shard_layout = QGridLayout()
        shard_layout.setSpacing(24)
        
        # Top-Left: Calibrate shard (using match shape for system-options-shard)
        calibrate_shard = ShardButton("Calibrate", "match")
        calibrate_shard.clicked.connect(lambda: self._navigate_to_view("calibrate"))
        shard_layout.addWidget(calibrate_shard, 0, 0)
        
        # Top-Right: Options shard (using freeplay shape for system-projection-shard)
        options_shard = ShardButton("Options", "freeplay")
        options_shard.clicked.connect(lambda: self._navigate_to_view("options"))
        shard_layout.addWidget(options_shard, 0, 1)
        
        # Bottom-Left: Projection shard (using systemhub shape for system-tracker-shard)
        projection_shard = ShardButton("Projection", "systemhub")
        projection_shard.clicked.connect(lambda: self._navigate_to_view("projection_setup"))
        shard_layout.addWidget(projection_shard, 1, 0)
        
        # Bottom-Right: Tracker shard (using match shape for system-calibration-shard)
        tracker_shard = ShardButton("Tracker", "match")
        tracker_shard.clicked.connect(lambda: self._navigate_to_view("tracker_setup"))
        shard_layout.addWidget(tracker_shard, 1, 1)
        
        layout.addStretch()
        layout.addLayout(shard_layout)
        layout.addStretch()
        
        # Footer
        footer = QLabel("BeysionXR Kiosk - Operational Hub")
        footer.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.TEXT_TERTIARY.name()};
                font-family: "Segoe UI";
                font-size: 14px;
                text-align: center;
            }}
        """)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)
        
        return widget
    
    def _create_free_play_view(self) -> QWidget:
        """Create the Free Play view with kiosk styling."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(32)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Free Play Mode")
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                font-family: "Arial";
                font-size: 36px;
                font-weight: 700;
                text-transform: uppercase;
                text-shadow: 0 0 8px {theme.colors.PRIMARY_INTERACTIVE.name()};
            }}
        """)
        
        back_btn = ActionButton("← Main Menu", "ghost")
        back_btn.clicked.connect(lambda: self._navigate_to_view("main_menu"))
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(back_btn)
        layout.addLayout(header_layout)
        
        # Content
        content_layout = QHBoxLayout()
        
        # Start button card
        start_card = CyberCard("Ready to Play")
        start_layout = QVBoxLayout(start_card)
        
        instruction_text = QLabel("Get ready for unlimited beyblade battles!")
        instruction_text.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.TEXT_PRIMARY.name()};
                font-family: "Segoe UI";
                font-size: 16px;
                text-align: center;
                margin: 20px;
            }}
        """)
        instruction_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        start_layout.addWidget(instruction_text)
        
        start_btn = ActionButton("Start Free Play", "success")
        start_btn.setMinimumSize(200, 60)
        start_btn.clicked.connect(self._start_free_play)
        start_layout.addWidget(start_btn)
        
        content_layout.addWidget(start_card)
        layout.addLayout(content_layout)
        layout.addStretch()
        
        return widget
    
    def _create_match_settings_view(self) -> QWidget:
        """Create the Match Settings view with kiosk styling."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(32)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Match Setup")
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                font-family: "Arial";
                font-size: 36px;
                font-weight: 700;
                text-transform: uppercase;
                text-shadow: 0 0 8px {theme.colors.PRIMARY_INTERACTIVE.name()};
            }}
        """)
        
        back_btn = ActionButton("← Main Menu", "ghost")
        back_btn.clicked.connect(lambda: self._navigate_to_view("main_menu"))
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(back_btn)
        layout.addLayout(header_layout)
        
        # Content
        content_layout = QHBoxLayout()
        
        # Settings card
        settings_card = CyberCard("Match Configuration")
        settings_layout = QVBoxLayout(settings_card)
        
        # Match type selection
        match_type_label = QLabel("Match Type:")
        match_type_label.setStyleSheet(f"color: {theme.colors.TEXT_PRIMARY.name()}; font-size: 14px; font-weight: 600;")
        settings_layout.addWidget(match_type_label)
        
        type_layout = QHBoxLayout()
        best_of_3_btn = ActionButton("Best of 3", "secondary")
        best_of_5_btn = ActionButton("Best of 5", "secondary")
        unlimited_btn = ActionButton("Unlimited", "ghost")
        
        type_layout.addWidget(best_of_3_btn)
        type_layout.addWidget(best_of_5_btn)
        type_layout.addWidget(unlimited_btn)
        settings_layout.addLayout(type_layout)
        
        settings_layout.addStretch()
        
        start_match_btn = ActionButton("Start Match", "success")
        start_match_btn.setMinimumSize(200, 60)
        start_match_btn.clicked.connect(self._start_match)
        settings_layout.addWidget(start_match_btn)
        
        content_layout.addWidget(settings_card)
        layout.addLayout(content_layout)
        layout.addStretch()
        
        return widget
    
    def _create_calibrate_view(self) -> QWidget:
        """Create the Calibrate view with kiosk styling."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(32)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Environment Calibration")
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                font-family: "Arial";
                font-size: 36px;
                font-weight: 700;
                text-transform: uppercase;
                text-shadow: 0 0 8px {theme.colors.PRIMARY_INTERACTIVE.name()};
            }}
        """)
        
        back_btn = ActionButton("← System Hub", "ghost")
        back_btn.clicked.connect(lambda: self._navigate_to_view("system_hub"))
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(back_btn)
        layout.addLayout(header_layout)
        
        # Content
        content_layout = QHBoxLayout()
        
        # Calibration card
        calibrate_card = CyberCard("Calibration Wizard")
        calibrate_layout = QVBoxLayout(calibrate_card)
        
        instruction_text = QLabel("Follow the on-screen instructions to calibrate the tracking system.")
        instruction_text.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.TEXT_PRIMARY.name()};
                font-family: "Segoe UI";
                font-size: 16px;
                text-align: center;
                margin: 20px;
            }}
        """)
        instruction_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        calibrate_layout.addWidget(instruction_text)
        
        start_calibration_btn = ActionButton("Start Calibration", "warning")
        start_calibration_btn.setMinimumSize(200, 60)
        start_calibration_btn.clicked.connect(self._start_calibration)
        calibrate_layout.addWidget(start_calibration_btn)
        
        content_layout.addWidget(calibrate_card)
        layout.addLayout(content_layout)
        layout.addStretch()
        
        return widget
    
    def _navigate_to_view(self, view_name: str):
        """Navigate to a specific view."""
        if view_name not in self._views:
            print(f"[KioskMainWindow] Warning: View '{view_name}' not found")
            return
        
        self._current_view = view_name
        view_widget = self._views[view_name]
        self._view_stack.setCurrentWidget(view_widget)
        
        # Notify GUI service
        self._gui_service.show_page(view_name)
        
        print(f"[KioskMainWindow] Navigated to view: {view_name}")
    
    def _setup_event_connections(self) -> None:
        """Set up connections to GUI service events."""
        if hasattr(self._gui_service, 'register_page_update_callback'):
            self._gui_service.register_page_update_callback(self._handle_state_update)
        
        if hasattr(self._gui_service, 'register_notification_callback'):
            self._gui_service.register_notification_callback(self._handle_notification)
    
    def _setup_developer_shortcuts(self):
        """Set up developer keyboard shortcuts."""
        # Ctrl+D to toggle developer mode
        dev_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        dev_shortcut.activated.connect(self._toggle_developer_mode)
        
        # Ctrl+E to go to EDA dashboard
        eda_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        eda_shortcut.activated.connect(self._open_eda_dashboard)
    
    def _toggle_developer_mode(self):
        """Toggle developer mode display."""
        self._developer_mode = not self._developer_mode
        if self._developer_mode:
            self._toast_manager.show_toast("Developer mode enabled", 2000)
        else:
            self._toast_manager.show_toast("Developer mode disabled", 2000)
    
    def _open_eda_dashboard(self):
        """Open the technical EDA dashboard in a new window."""
        self._toast_manager.show_toast("Opening technical dashboard...", 2000)
        # This could create a new EDAMainWindow instance
        print("[KioskMainWindow] EDA dashboard requested")
    
    def _handle_state_update(self, state: Dict[str, Any]) -> None:
        """Handle state updates from GUI service."""
        # Handle projection status updates for developer notifications
        if 'projection_connected' in state and self._developer_mode:
            connected = state['projection_connected']
            if connected:
                self._toast_manager.show_toast("Projection client connected", 2000)
            else:
                self._toast_manager.show_toast("Projection client disconnected", 2000)
    
    def _handle_notification(self, message: str, duration_ms: int) -> None:
        """Handle notifications from GUI service."""
        if self._toast_manager:
            self._toast_manager.show_toast(message, duration_ms)
    
    def _update_performance_metrics(self):
        """Update performance metrics (minimal for kiosk mode)."""
        # Only track essential metrics in kiosk mode
        pass
    
    def _start_free_play(self):
        """Start free play mode."""
        self._gui_service.request_start_tracking(dev_mode=True, cam_src=0)
        self._gui_service.show_notification("Free Play mode started")
    
    def _start_match(self):
        """Start match mode."""
        self._gui_service.request_start_tracking(dev_mode=True, cam_src=0)
        self._gui_service.show_notification("Match started")
    
    def _start_calibration(self):
        """Start calibration process."""
        self._gui_service.request_calibration()
        self._gui_service.show_notification("Calibration started")
    
    def _handle_exit_request(self):
        """Handle exit request from main menu."""
        # In a real kiosk, this might trigger system shutdown or return to launcher
        self._gui_service.show_notification("Exit requested - would close application in production")
        print("[KioskMainWindow] Exit requested")


class KioskTrackerSetupPage(QWidget):
    """Kiosk-styled Tracker Setup page."""
    
    def __init__(self, gui_service: IGUIService):
        super().__init__()
        self._gui_service = gui_service
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the tracker setup UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(32)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Tracker Setup")
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                font-family: "Arial";
                font-size: 36px;
                font-weight: 700;
                text-transform: uppercase;
                text-shadow: 0 0 8px {theme.colors.PRIMARY_INTERACTIVE.name()};
            }}
        """)
        
        back_btn = ActionButton("← System Hub", "ghost")
        back_btn.clicked.connect(lambda: self.window()._navigate_to_view("system_hub"))
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(back_btn)
        layout.addLayout(header_layout)
        
        # Content
        content_card = CyberCard("Camera Configuration")
        content_layout = QVBoxLayout(content_card)
        
        # Simple camera controls
        start_preview_btn = ActionButton("Start Camera Preview", "primary")
        start_preview_btn.clicked.connect(self._start_preview)
        content_layout.addWidget(start_preview_btn)
        
        stop_preview_btn = ActionButton("Stop Preview", "error")
        stop_preview_btn.clicked.connect(self._stop_preview)
        content_layout.addWidget(stop_preview_btn)
        
        layout.addWidget(content_card)
        layout.addStretch()
    
    def _start_preview(self):
        """Start camera preview."""
        self._gui_service.request_start_tracking(dev_mode=True, cam_src=0)
        self._gui_service.show_notification("Camera preview started")
    
    def _stop_preview(self):
        """Stop camera preview."""
        self._gui_service.request_stop_tracking()
        self._gui_service.show_notification("Camera preview stopped")


class KioskProjectionSetupPage(QWidget):
    """Kiosk-styled Projection Setup page."""
    
    def __init__(self, gui_service: IGUIService):
        super().__init__()
        self._gui_service = gui_service
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the projection setup UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(32)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Projection Setup")
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                font-family: "Arial";
                font-size: 36px;
                font-weight: 700;
                text-transform: uppercase;
                text-shadow: 0 0 8px {theme.colors.PRIMARY_INTERACTIVE.name()};
            }}
        """)
        
        back_btn = ActionButton("← System Hub", "ghost")
        back_btn.clicked.connect(lambda: self.window()._navigate_to_view("system_hub"))
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(back_btn)
        layout.addLayout(header_layout)
        
        # Content
        content_card = CyberCard("Projector Configuration")
        content_layout = QVBoxLayout(content_card)
        
        # Simple projection controls
        test_projection_btn = ActionButton("Test Projection", "secondary")
        test_projection_btn.clicked.connect(self._test_projection)
        content_layout.addWidget(test_projection_btn)
        
        start_unity_btn = ActionButton("Start Unity Client", "success")
        start_unity_btn.clicked.connect(self._start_unity_client)
        content_layout.addWidget(start_unity_btn)
        
        layout.addWidget(content_card)
        layout.addStretch()
    
    def _test_projection(self):
        """Test projection connection."""
        self._gui_service.update_projection_config(1920, 1080)
        self._gui_service.show_notification("Testing projection connection...")
    
    def _start_unity_client(self):
        """Start Unity client."""
        self._gui_service.show_notification("Starting Unity client...")


class KioskOptionsPage(QWidget):
    """Kiosk-styled Options page."""
    
    def __init__(self, gui_service: IGUIService):
        super().__init__()
        self._gui_service = gui_service
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the options UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(32)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("System Options")
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                font-family: "Arial";
                font-size: 36px;
                font-weight: 700;
                text-transform: uppercase;
                text-shadow: 0 0 8px {theme.colors.PRIMARY_INTERACTIVE.name()};
            }}
        """)
        
        back_btn = ActionButton("← System Hub", "ghost")
        back_btn.clicked.connect(lambda: self.window()._navigate_to_view("system_hub"))
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(back_btn)
        layout.addLayout(header_layout)
        
        # Content
        content_card = CyberCard("Application Settings")
        content_layout = QVBoxLayout(content_card)
        
        # Simple options
        settings_text = QLabel("• Audio Volume: 75%\n• Screen Brightness: 100%\n• Auto-start: Enabled")
        settings_text.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.TEXT_PRIMARY.name()};
                font-family: "Segoe UI";
                font-size: 16px;
                line-height: 1.5;
            }}
        """)
        content_layout.addWidget(settings_text)
        
        # Control buttons
        controls_layout = QHBoxLayout()
        
        reset_btn = ActionButton("Reset to Defaults", "warning")
        reset_btn.clicked.connect(self._reset_settings)
        controls_layout.addWidget(reset_btn)
        
        apply_btn = ActionButton("Apply Changes", "primary")
        apply_btn.clicked.connect(self._apply_settings)
        controls_layout.addWidget(apply_btn)
        
        content_layout.addLayout(controls_layout)
        
        layout.addWidget(content_card)
        layout.addStretch()
    
    def _reset_settings(self):
        """Reset settings to defaults."""
        self._gui_service.show_notification("Settings reset to defaults")
    
    def _apply_settings(self):
        """Apply current settings."""
        self._gui_service.show_notification("Settings applied")


def create_kiosk_gui_application(gui_service: IGUIService) -> QApplication:
    """Create the Kiosk GUI application with BBAN styling."""
    import sys
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Create the main kiosk window
    main_window = KioskMainWindow(gui_service)
    main_window.show()
    
    return app 