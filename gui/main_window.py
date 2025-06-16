"""
MainWindow and ToastManager for BBAN-Tracker Event-Driven Architecture.

This module contains the main window and notification system extracted from the monolithic GUI.
It will be integrated with the GUIService to provide the main application window.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QPalette, QColor, QGraphicsOpacityEffect
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QStatusBar, QToolBar,
    QLabel, QPushButton, QApplication
)

from ..gui.calibration_wizard import CalibrationWizard, LAYOUT_FILE, _load_json, _save_json
from .ui_components.system_status_panel import SystemStatusPanel, ConnectionStatus


# Global config paths
_CONFIG_DIR = Path.home() / ".beytracker"
_CONFIG_DIR.mkdir(exist_ok=True)
GUI_PREFS_FILE = _CONFIG_DIR / "gui_prefs.json"


class _ToastManager(QWidget):
    """Manager for toast notifications in the main window."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(300, 60)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 40, 220);
                border: 1px solid #555;
                border-radius: 8px;
                color: white;
                font-size: 14px;
                padding: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        
        self.hide()

    def show(self, text: str, duration_ms: int = 3000):
        """Show a toast notification with the given text."""
        self.label.setText(text)
        
        # Position at bottom-right of parent
        parent = self.parent()
        if parent:
            parent_rect = parent.rect()
            x = parent_rect.width() - self.width() - 20
            y = parent_rect.height() - self.height() - 60
            self.move(x, y)
        
        # Show with fade-in animation
        self.setWindowOpacity(0.0)
        self.show()
        
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(300)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.start()
        
        # Auto-hide after duration
        QTimer.singleShot(duration_ms, self._fade_out)

    def _fade_out(self):
        """Fade out and hide the toast."""
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(300)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.finished.connect(self.hide)
        self.fade_out.start()


class MainWindow(QMainWindow):
    """Main application window for BBAN-Tracker."""

    def __init__(self, *, dev_mode: bool = False, cam_src: int = 0):
        super().__init__()
        self.setWindowTitle("BBAN-Tracker v2.1 - EDA Architecture")
        self.setMinimumSize(1200, 800)
        
        self._dev_mode = dev_mode
        self._cam_src = cam_src
        
        # Central widget with horizontal layout for main content and status panel
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # Main content area with stacked pages
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        
        main_layout.addWidget(content_widget, 1)  # Take most of the space
        
        # System status panel (always visible on the right)
        self.system_status_panel = SystemStatusPanel()
        main_layout.addWidget(self.system_status_panel)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._status_message("BBAN-Tracker initialized")
        
        # Toast notification manager
        self.toast_manager = _ToastManager(self)
        
        # Pages will be added by the GUIService
        self.pages = {}
        
        # Apply saved theme and layout
        self._apply_saved_theme()
        self.apply_saved_layout()

    def add_page(self, name: str, page_widget: QWidget):
        """Add a page to the stacked widget."""
        self.pages[name] = page_widget
        self.stacked_widget.addWidget(page_widget)

    def show_page(self, name: str):
        """Show the specified page."""
        if name in self.pages:
            self.stacked_widget.setCurrentWidget(self.pages[name])
            self._status_message(f"Showing {name}")

    def get_active_worker(self):
        """Get the active tracking worker from the current page."""
        current_page = self.stacked_widget.currentWidget()
        if hasattr(current_page, '_worker') and current_page._worker:
            return current_page._worker
        return None

    def _status_message(self, msg: str):
        """Display a status message."""
        self.status_bar.showMessage(msg)

    def show_toast(self, message: str, duration_ms: int = 3000):
        """Show a toast notification."""
        self.toast_manager.show(message, duration_ms)

    def update_camera_status(self, connected: bool, camera_type: str = "", fps: float = 0.0):
        """Update camera status in the system status panel."""
        status = ConnectionStatus.CONNECTED if connected else ConnectionStatus.DISCONNECTED
        self.system_status_panel.update_camera_status(status, camera_type, fps)

    def update_unity_status(self, connected: bool, client_info: str = ""):
        """Update Unity client status in the system status panel."""
        status = ConnectionStatus.CONNECTED if connected else ConnectionStatus.DISCONNECTED
        self.system_status_panel.update_unity_status(status, client_info)

    def update_tracking_status(self, active: bool, fps: float = 0.0):
        """Update tracking service status in the system status panel."""
        status = ConnectionStatus.CONNECTED if active else ConnectionStatus.DISCONNECTED
        self.system_status_panel.update_tracking_status(status, fps)

    def update_system_health(self, events_per_second: float, total_events: int):
        """Update system health metrics in the system status panel."""
        self.system_status_panel.update_system_health(events_per_second, total_events)

    def apply_saved_layout(self):
        """Apply saved layout profile for projection mapping."""
        try:
            cfg = _load_json(LAYOUT_FILE, {}).get("default", {})
            if cfg:
                # Layout information is available but not applied here
                # This would be used by projection setup page
                pass
        except Exception:
            pass

    def _apply_saved_theme(self):
        """Apply saved theme preference."""
        try:
            cfg, _ = _load_json(GUI_PREFS_FILE, {})
            theme = cfg.get("theme", "Dark")
            self.apply_theme(theme)
        except Exception:
            # Default to dark theme
            self.apply_theme("Dark")

    def apply_theme(self, theme_name: str = "Dark"):
        """Apply a visual theme to the application."""
        if theme_name == "Dark":
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QWidget {
                    background-color: #2b2b2b;
                    color: #ffffff;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    padding: 5px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #4c4c4c;
                }
                QPushButton:pressed {
                    background-color: #1e1e1e;
                }
                QGroupBox {
                    font-weight: bold;
                    border: 2px solid #555555;
                    border-radius: 5px;
                    margin-top: 1ex;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QLabel {
                    color: #ffffff;
                }
                QSlider::groove:horizontal {
                    border: 1px solid #999999;
                    height: 8px;
                    background: #555555;
                    margin: 2px 0;
                    border-radius: 4px;
                }
                QSlider::handle:horizontal {
                    background: #cccccc;
                    border: 1px solid #5c5c5c;
                    width: 18px;
                    margin: -2px 0;
                    border-radius: 9px;
                }
                QSlider::handle:horizontal:hover {
                    background: #ffffff;
                }
                QComboBox {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    padding: 3px;
                    border-radius: 3px;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 15px;
                    border-left-width: 1px;
                    border-left-color: #555555;
                    border-left-style: solid;
                }
                QSpinBox {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    padding: 3px;
                    border-radius: 3px;
                }
                QTableWidget {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                    gridline-color: #555555;
                }
                QTableWidget::item {
                    padding: 3px;
                }
                QTableWidget::item:selected {
                    background-color: #5c5c5c;
                }
                QCheckBox {
                    spacing: 5px;
                }
                QCheckBox::indicator {
                    width: 13px;
                    height: 13px;
                }
                QCheckBox::indicator:unchecked {
                    background-color: #3c3c3c;
                    border: 1px solid #555555;
                }
                QCheckBox::indicator:checked {
                    background-color: #5c5c5c;
                    border: 1px solid #777777;
                }
                QStatusBar {
                    background-color: #1e1e1e;
                    border-top: 1px solid #555555;
                }
            """)
        
        # Save theme preference
        try:
            cfg, _ = _load_json(GUI_PREFS_FILE, {})
            cfg["theme"] = theme_name
            _save_json(GUI_PREFS_FILE, cfg)
        except Exception:
            pass

    def open_calibration_wizard_global(self):
        """Open the calibration wizard with global worker resolution."""
        def _worker_resolver():
            """Resolve the active worker from any page."""
            # Check current page first
            current_page = self.stacked_widget.currentWidget()
            if hasattr(current_page, '_get_worker'):
                worker = current_page._get_worker()
                if worker:
                    return worker
            
            # Check all pages for an active worker
            for i in range(self.stacked_widget.count()):
                page = self.stacked_widget.widget(i)
                if hasattr(page, '_get_worker'):
                    worker = page._get_worker()
                    if worker:
                        return worker
            return None

        wizard = CalibrationWizard(_worker_resolver)
        wizard.exec()
        self.apply_saved_layout()

    def resizeEvent(self, event):
        """Handle window resize to reposition toast manager."""
        super().resizeEvent(event)
        # Toast manager will reposition itself when next shown

    def closeEvent(self, event):
        """Handle application close."""
        # Stop all workers in all pages
        for i in range(self.stacked_widget.count()):
            page = self.stacked_widget.widget(i)
            if hasattr(page, 'stop_tracking'):
                page.stop_tracking()
        
        super().closeEvent(event)


def create_main_window(dev_mode: bool = False, cam_src: int = 0) -> MainWindow:
    """Create and configure the main window."""
    window = MainWindow(dev_mode=dev_mode, cam_src=cam_src)
    return window 