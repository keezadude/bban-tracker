"""
System Status Dashboard for BBAN-Tracker Event-Driven Architecture.

Provides a comprehensive, always-visible status panel that displays real-time
system health including camera connections, Unity client status, tracking
service state, and performance metrics. Designed for production deployment
where operators need immediate visual feedback on system state.
"""

import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
    QPushButton, QProgressBar, QGroupBox, QGridLayout
)
from PySide6.QtGui import QFont, QPalette, QColor, QPainter, QPen, QBrush


class ConnectionStatus(Enum):
    """Enumeration for connection status types."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class SystemStatusData:
    """Data structure for system status information."""
    camera_status: ConnectionStatus = ConnectionStatus.UNKNOWN
    camera_type: str = ""
    camera_fps: float = 0.0
    
    unity_status: ConnectionStatus = ConnectionStatus.UNKNOWN
    unity_client_info: str = ""
    unity_latency_ms: float = 0.0
    
    tracking_service_status: ConnectionStatus = ConnectionStatus.UNKNOWN
    tracking_fps: float = 0.0
    
    system_uptime: float = 0.0
    events_per_second: float = 0.0
    total_events: int = 0


class StatusIndicator(QWidget):
    """
    Individual status indicator widget with color-coded visual feedback.
    """
    
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 60)
        
        self._label = label
        self._status = ConnectionStatus.UNKNOWN
        self._value = ""
        self._is_pulsing = False
        
        self._setup_ui()
        self._setup_styling()
    
    def _setup_ui(self) -> None:
        """Set up the indicator UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(2)
        
        # Label
        self._label_widget = QLabel(self._label)
        self._label_widget.setAlignment(Qt.AlignCenter)
        self._label_widget.setFont(QFont("Arial", 8, QFont.Bold))
        layout.addWidget(self._label_widget)
        
        # Status circle
        self._status_widget = QLabel("●")
        self._status_widget.setAlignment(Qt.AlignCenter)
        self._status_widget.setFont(QFont("Arial", 16))
        layout.addWidget(self._status_widget)
        
        # Value
        self._value_widget = QLabel(self._value)
        self._value_widget.setAlignment(Qt.AlignCenter)
        self._value_widget.setFont(QFont("Arial", 7))
        layout.addWidget(self._value_widget)
    
    def _setup_styling(self) -> None:
        """Set up styling for the indicator."""
        self.setStyleSheet("""
            StatusIndicator {
                background-color: #2b2b2b;
                border: 1px solid #555;
                border-radius: 8px;
                margin: 2px;
            }
            
            QLabel {
                color: #ffffff;
                background: transparent;
                border: none;
            }
        """)
    
    def update_status(self, status: ConnectionStatus, value: str = "") -> None:
        """
        Update the status indicator.
        
        Args:
            status: New connection status
            value: Additional value to display
        """
        self._status = status
        self._value = value
        
        # Update value text
        self._value_widget.setText(value)
        
        # Update status color
        color_map = {
            ConnectionStatus.CONNECTED: "#4caf50",      # Green
            ConnectionStatus.DISCONNECTED: "#757575",   # Gray
            ConnectionStatus.CONNECTING: "#ff9800",     # Orange
            ConnectionStatus.ERROR: "#f44336",          # Red
            ConnectionStatus.UNKNOWN: "#9e9e9e"         # Light gray
        }
        
        color = color_map[status]
        self._status_widget.setStyleSheet(f"color: {color};")
        
        # Add pulsing animation for connecting state
        if status == ConnectionStatus.CONNECTING and not self._is_pulsing:
            self._start_pulse_animation()
        elif status != ConnectionStatus.CONNECTING and self._is_pulsing:
            self._stop_pulse_animation()
    
    def _start_pulse_animation(self) -> None:
        """Start pulsing animation for connecting state."""
        self._is_pulsing = True
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_timer.start(500)  # Pulse every 500ms
    
    def _stop_pulse_animation(self) -> None:
        """Stop pulsing animation."""
        self._is_pulsing = False
        if hasattr(self, '_pulse_timer'):
            self._pulse_timer.stop()
    
    def _pulse_tick(self) -> None:
        """Handle pulse animation tick."""
        current_opacity = self._status_widget.windowOpacity()
        new_opacity = 0.3 if current_opacity > 0.5 else 1.0
        self._status_widget.setWindowOpacity(new_opacity)


class SystemStatusPanel(QWidget):
    """
    Comprehensive system status dashboard that provides real-time visibility
    into all critical system components. Designed for production deployment
    where operators need immediate visual feedback.
    """
    
    # Signals for status updates
    status_changed = Signal(str, str)  # component, status
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        
        self._start_time = time.time()
        self._system_status = SystemStatusData()
        
        self._setup_ui()
        self._setup_styling()
        self._setup_update_timer()
    
    def _setup_ui(self) -> None:
        """Set up the system status panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        
        # Title
        title = QLabel("System Status")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(title)
        
        # Status indicators grid
        indicators_frame = QFrame()
        indicators_layout = QGridLayout(indicators_frame)
        indicators_layout.setSpacing(5)
        
        # Camera status
        self._camera_indicator = StatusIndicator("Camera")
        indicators_layout.addWidget(self._camera_indicator, 0, 0)
        
        # Unity status
        self._unity_indicator = StatusIndicator("Unity Client")
        indicators_layout.addWidget(self._unity_indicator, 0, 1)
        
        # Tracking service status
        self._tracking_indicator = StatusIndicator("Tracking")
        indicators_layout.addWidget(self._tracking_indicator, 1, 0)
        
        # System health status
        self._system_indicator = StatusIndicator("System")
        indicators_layout.addWidget(self._system_indicator, 1, 1)
        
        layout.addWidget(indicators_frame)
        
        # FPS Display
        fps_group = QGroupBox("Performance")
        fps_layout = QVBoxLayout(fps_group)
        
        self._fps_label = QLabel("FPS: --")
        self._fps_label.setAlignment(Qt.AlignCenter)
        self._fps_label.setFont(QFont("Arial", 12, QFont.Bold))
        fps_layout.addWidget(self._fps_label)
        
        self._events_label = QLabel("Events/sec: --")
        self._events_label.setAlignment(Qt.AlignCenter)
        self._events_label.setFont(QFont("Arial", 10))
        fps_layout.addWidget(self._events_label)
        
        layout.addWidget(fps_group)
        
        # Stretch to fill remaining space
        layout.addStretch()
    
    def _setup_styling(self) -> None:
        """Set up styling for the status panel."""
        self.setStyleSheet("""
            SystemStatusPanel {
                background-color: #2b2b2b;
                border: 1px solid #555;
                border-radius: 8px;
            }
            
            QLabel {
                color: #ffffff;
                background: transparent;
                border: none;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 5px;
                color: #ffffff;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
                color: #cccccc;
                font-size: 10px;
            }
        """)
    
    def _setup_update_timer(self) -> None:
        """Set up timer for periodic status updates."""
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_display)
        self._update_timer.start(1000)  # Update every second
    
    def update_camera_status(self, status: ConnectionStatus, camera_type: str = "", fps: float = 0.0) -> None:
        """Update camera connection status."""
        self._system_status.camera_status = status
        self._system_status.camera_type = camera_type
        self._system_status.camera_fps = fps
        
        value_text = ""
        if status == ConnectionStatus.CONNECTED and camera_type:
            value_text = f"{camera_type}"
            if fps > 0:
                value_text += f"\n{fps:.1f} FPS"
        
        self._camera_indicator.update_status(status, value_text)
        self.status_changed.emit("camera", status.value)
    
    def update_unity_status(self, status: ConnectionStatus, client_info: str = "") -> None:
        """Update Unity client connection status."""
        self._system_status.unity_status = status
        self._system_status.unity_client_info = client_info
        
        value_text = client_info if status == ConnectionStatus.CONNECTED else ""
        self._unity_indicator.update_status(status, value_text)
        self.status_changed.emit("unity", status.value)
    
    def update_tracking_status(self, status: ConnectionStatus, fps: float = 0.0) -> None:
        """Update tracking service status."""
        self._system_status.tracking_service_status = status
        self._system_status.tracking_fps = fps
        
        value_text = f"{fps:.1f} FPS" if status == ConnectionStatus.CONNECTED and fps > 0 else ""
        self._tracking_indicator.update_status(status, value_text)
        self.status_changed.emit("tracking", status.value)
    
    def update_system_health(self, events_per_second: float, total_events: int) -> None:
        """Update overall system health metrics."""
        self._system_status.events_per_second = events_per_second
        self._system_status.total_events = total_events
        
        status = ConnectionStatus.CONNECTED if events_per_second > 0 else ConnectionStatus.DISCONNECTED
        value_text = f"{total_events} events" if events_per_second > 0 else "Idle"
        
        self._system_indicator.update_status(status, value_text)
        self.status_changed.emit("system", status.value)
    
    def _update_display(self) -> None:
        """Periodic update of the display."""
        # Update FPS display
        max_fps = max(self._system_status.camera_fps, self._system_status.tracking_fps)
        self._fps_label.setText(f"FPS: {max_fps:.1f}")
        
        # Update events display
        self._events_label.setText(f"Events/sec: {self._system_status.events_per_second:.1f}")
    
    def get_system_status(self) -> SystemStatusData:
        """Get current system status data."""
        return self._system_status


def create_system_status_panel(parent=None) -> SystemStatusPanel:
    """
    Factory function to create a system status panel.
    
    Args:
        parent: Parent widget
        
    Returns:
        Configured SystemStatusPanel instance
    """
    panel = SystemStatusPanel(parent)
    
    # Initialize with default "unknown" states
    panel.update_camera_status(ConnectionStatus.UNKNOWN)
    panel.update_unity_status(ConnectionStatus.UNKNOWN)
    panel.update_tracking_status(ConnectionStatus.UNKNOWN)
    panel.update_system_health(0.0, 0)
    
    return panel 