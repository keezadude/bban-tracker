"""
Status components for EDA-integrated BBAN-Tracker GUI.

This module provides status bar, notification, and toast components that
integrate with the Event-Driven Architecture to display system status,
notifications, and real-time updates.
"""

import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QStatusBar, 
    QFrame, QPushButton, QGraphicsOpacityEffect
)
from PySide6.QtGui import QFont, QPalette, QColor, QPainter, QPen


@dataclass
class NotificationData:
    """Data structure for notifications."""
    message: str
    duration_ms: int = 3000
    notification_type: str = "info"  # info, success, warning, error
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class StatusBar(QStatusBar):
    """
    Enhanced status bar for the EDA-integrated GUI.
    
    Displays system status including tracking state, projection state,
    performance metrics, and connection status.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._status_widgets = {}
        self._performance_metrics = {}
        
        self._setup_status_widgets()
        self._setup_styling()
        self._setup_update_timer()
    
    def _setup_status_widgets(self) -> None:
        """Create and add status widgets to the status bar."""
        # Tracking status
        self._tracking_status = QLabel("Tracking: Stopped")
        self._tracking_status.setObjectName("tracking_status")
        self.addWidget(self._tracking_status)
        self._status_widgets["tracking"] = self._tracking_status
        
        # Add separator
        separator1 = self._create_separator()
        self.addWidget(separator1)
        
        # Projection status
        self._projection_status = QLabel("Projection: Disconnected")
        self._projection_status.setObjectName("projection_status")
        self.addWidget(self._projection_status)
        self._status_widgets["projection"] = self._projection_status
        
        # Add separator
        separator2 = self._create_separator()
        self.addWidget(separator2)
        
        # Performance metrics
        self._performance_status = QLabel("FPS: --")
        self._performance_status.setObjectName("performance_status")
        self.addWidget(self._performance_status)
        self._status_widgets["performance"] = self._performance_status
        
        # Add stretch to push connection status to the right
        self.addWidget(QWidget(), 1)  # Stretch widget
        
        # Connection status
        self._connection_status = QLabel("System: Ready")
        self._connection_status.setObjectName("connection_status")
        self.addPermanentWidget(self._connection_status)
        self._status_widgets["connection"] = self._connection_status
    
    def _create_separator(self) -> QFrame:
        """Create a visual separator for the status bar."""
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setMaximumHeight(20)
        return separator
    
    def _setup_styling(self) -> None:
        """Set up styling for the status bar."""
        self.setStyleSheet("""
            QStatusBar {
                background-color: #1e1e1e;
                border-top: 1px solid #555;
                color: #ffffff;
                font-size: 12px;
                padding: 2px 5px;
            }
            
            QLabel#tracking_status {
                color: #ff5722;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 3px;
                background-color: rgba(255, 87, 34, 0.1);
            }
            
            QLabel#projection_status {
                color: #9e9e9e;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 3px;
                background-color: rgba(158, 158, 158, 0.1);
            }
            
            QLabel#performance_status {
                color: #2196f3;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 3px;
                background-color: rgba(33, 150, 243, 0.1);
            }
            
            QLabel#connection_status {
                color: #4caf50;
                font-weight: bold;
                padding: 2px 8px;
                border-radius: 3px;
                background-color: rgba(76, 175, 80, 0.1);
            }
            
            QFrame {
                color: #555;
            }
        """)
    
    def _setup_update_timer(self) -> None:
        """Set up timer for periodic status updates."""
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_display)
        self._update_timer.start(1000)  # Update every second
    
    def update_tracking_status(self, active: bool, camera_type: str = "") -> None:
        """
        Update tracking status display.
        
        Args:
            active: Whether tracking is active
            camera_type: Type of camera being used
        """
        if active:
            status_text = f"Tracking: Active ({camera_type})"
            color = "#4caf50"  # Green
        else:
            status_text = "Tracking: Stopped"
            color = "#ff5722"  # Red
            
        self._tracking_status.setText(status_text)
        self._update_widget_color(self._tracking_status, color)
    
    def update_projection_status(self, connected: bool, client_info: str = "") -> None:
        """
        Update projection status display.
        
        Args:
            connected: Whether Unity client is connected
            client_info: Additional client information
        """
        if connected:
            status_text = f"Projection: Connected ({client_info})"
            color = "#4caf50"  # Green
        else:
            status_text = "Projection: Disconnected"
            color = "#9e9e9e"  # Gray
            
        self._projection_status.setText(status_text)
        self._update_widget_color(self._projection_status, color)
    
    def update_performance_metrics(self, fps: float, latency_ms: float = 0.0) -> None:
        """
        Update performance metrics display.
        
        Args:
            fps: Current frames per second
            latency_ms: Current latency in milliseconds
        """
        if latency_ms > 0:
            status_text = f"FPS: {fps:.1f} | Latency: {latency_ms:.1f}ms"
        else:
            status_text = f"FPS: {fps:.1f}"
            
        self._performance_status.setText(status_text)
        
        # Color based on performance
        if fps >= 30:
            color = "#4caf50"  # Green - Good
        elif fps >= 15:
            color = "#ff9800"  # Orange - Warning
        else:
            color = "#f44336"  # Red - Poor
            
        self._update_widget_color(self._performance_status, color)
    
    def update_connection_status(self, status: str, color: str = "#4caf50") -> None:
        """
        Update connection status display.
        
        Args:
            status: Status message
            color: Color for the status
        """
        self._connection_status.setText(f"System: {status}")
        self._update_widget_color(self._connection_status, color)
    
    def _update_widget_color(self, widget: QLabel, color: str) -> None:
        """Update a widget's color dynamically."""
        current_style = widget.styleSheet()
        
        # Replace color in existing style or add it
        if "color:" in current_style:
            # Simple color replacement - would be more robust with CSS parser
            import re
            new_style = re.sub(r'color:\s*[^;]+;', f'color: {color};', current_style)
        else:
            new_style = current_style + f" color: {color};"
            
        widget.setStyleSheet(new_style)
    
    def _update_display(self) -> None:
        """Periodic update of the status display."""
        # This would be called periodically to refresh dynamic content
        current_time = time.strftime("%H:%M:%S")
        # Could update time-based information here
    
    def get_status_widget(self, name: str) -> Optional[QLabel]:
        """Get a status widget by name."""
        return self._status_widgets.get(name)


class NotificationWidget(QWidget):
    """
    Individual notification widget with auto-hide functionality.
    """
    
    closed = Signal()  # Emitted when notification is closed
    
    def __init__(self, notification: NotificationData, parent=None):
        super().__init__(parent)
        
        self._notification = notification
        self._close_timer = QTimer()
        self._fade_animation = None
        
        self._setup_ui()
        self._setup_styling()
        self._setup_auto_close()
    
    def _setup_ui(self) -> None:
        """Set up the notification UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        # Notification icon (based on type)
        self._icon_label = QLabel(self._get_icon_text())
        self._icon_label.setFixedSize(20, 20)
        self._icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._icon_label)
        
        # Notification message
        self._message_label = QLabel(self._notification.message)
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label, 1)
        
        # Close button
        self._close_button = QPushButton("×")
        self._close_button.setFixedSize(20, 20)
        self._close_button.clicked.connect(self.close_notification)
        layout.addWidget(self._close_button)
    
    def _get_icon_text(self) -> str:
        """Get icon text based on notification type."""
        icons = {
            "info": "ℹ",
            "success": "✓",
            "warning": "⚠",
            "error": "✗"
        }
        return icons.get(self._notification.notification_type, "ℹ")
    
    def _setup_styling(self) -> None:
        """Set up styling based on notification type."""
        colors = {
            "info": {"bg": "#2196f3", "border": "#1976d2"},
            "success": {"bg": "#4caf50", "border": "#388e3c"},
            "warning": {"bg": "#ff9800", "border": "#f57c00"},
            "error": {"bg": "#f44336", "border": "#d32f2f"}
        }
        
        color_scheme = colors.get(self._notification.notification_type, colors["info"])
        
        self.setStyleSheet(f"""
            NotificationWidget {{
                background-color: {color_scheme['bg']};
                border: 2px solid {color_scheme['border']};
                border-radius: 8px;
                color: white;
                font-weight: bold;
            }}
            
            QLabel {{
                color: white;
                background: transparent;
                border: none;
            }}
            
            QPushButton {{
                background-color: transparent;
                border: none;
                color: white;
                font-size: 16px;
                font-weight: bold;
            }}
            
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.2);
                border-radius: 10px;
            }}
        """)
    
    def _setup_auto_close(self) -> None:
        """Set up auto-close timer."""
        if self._notification.duration_ms > 0:
            self._close_timer.timeout.connect(self.close_notification)
            self._close_timer.setSingleShot(True)
            self._close_timer.start(self._notification.duration_ms)
    
    def close_notification(self) -> None:
        """Close the notification with fade animation."""
        # Stop auto-close timer
        self._close_timer.stop()
        
        # Create fade-out animation
        self._opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self._opacity_effect)
        
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_animation.setDuration(300)
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_animation.finished.connect(self._on_fade_finished)
        self._fade_animation.start()
    
    def _on_fade_finished(self) -> None:
        """Handle fade animation completion."""
        self.closed.emit()
        self.hide()
        self.deleteLater()


class ToastManager(QWidget):
    """
    Manages multiple notification toasts with proper stacking and positioning.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._notifications: List[NotificationWidget] = []
        self._max_notifications = 5
        self._notification_spacing = 10
        
        self._setup_ui()
        self._setup_positioning()
    
    def _setup_ui(self) -> None:
        """Set up the toast manager UI."""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self._notification_spacing)
        self._layout.addStretch()  # Push notifications to bottom
        
        # Make widget transparent
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: transparent;")
    
    def _setup_positioning(self) -> None:
        """Set up positioning relative to parent."""
        if self.parent():
            # Position in bottom-right corner of parent
            self.move(self.parent().width() - 350, 50)
            self.resize(320, self.parent().height() - 100)
    
    def show_notification(self, message: str, duration_ms: int = 3000, 
                         notification_type: str = "info") -> None:
        """
        Show a new notification.
        
        Args:
            message: Notification message
            duration_ms: Duration in milliseconds (0 for persistent)
            notification_type: Type of notification (info, success, warning, error)
        """
        # Remove oldest notification if at limit
        if len(self._notifications) >= self._max_notifications:
            oldest = self._notifications[0]
            oldest.close_notification()
        
        # Create new notification
        notification_data = NotificationData(
            message=message,
            duration_ms=duration_ms,
            notification_type=notification_type
        )
        
        notification_widget = NotificationWidget(notification_data, self)
        notification_widget.closed.connect(lambda: self._remove_notification(notification_widget))
        
        # Add to layout and list
        self._layout.insertWidget(self._layout.count() - 1, notification_widget)
        self._notifications.append(notification_widget)
        
        # Animate in
        self._animate_notification_in(notification_widget)
    
    def _animate_notification_in(self, notification: NotificationWidget) -> None:
        """Animate notification sliding in."""
        notification.setFixedSize(300, 0)  # Start with 0 height
        
        # Animate height expansion
        self._expand_animation = QPropertyAnimation(notification, b"maximumHeight")
        self._expand_animation.setDuration(300)
        self._expand_animation.setStartValue(0)
        self._expand_animation.setEndValue(60)
        self._expand_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._expand_animation.start()
    
    def _remove_notification(self, notification: NotificationWidget) -> None:
        """Remove a notification from the manager."""
        if notification in self._notifications:
            self._notifications.remove(notification)
    
    def clear_all_notifications(self) -> None:
        """Clear all notifications."""
        for notification in self._notifications[:]:  # Copy list to avoid modification during iteration
            notification.close_notification()
    
    def resizeEvent(self, event) -> None:
        """Handle resize events to maintain positioning."""
        super().resizeEvent(event)
        self._setup_positioning()


class PerformanceIndicator(QWidget):
    """
    Real-time performance indicator widget.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._fps_history = []
        self._max_history = 60  # Keep 60 samples for 1-second average at 60fps
        
        self.setFixedSize(100, 30)
        self._setup_styling()
    
    def _setup_styling(self) -> None:
        """Set up styling for the performance indicator."""
        self.setStyleSheet("""
            PerformanceIndicator {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)
    
    def update_fps(self, fps: float) -> None:
        """
        Update FPS measurement.
        
        Args:
            fps: Current frames per second
        """
        self._fps_history.append(fps)
        
        # Maintain rolling window
        if len(self._fps_history) > self._max_history:
            self._fps_history.pop(0)
        
        self.update()  # Trigger repaint
    
    def paintEvent(self, event) -> None:
        """Custom paint event for the performance graph."""
        super().paintEvent(event)
        
        if not self._fps_history:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate dimensions
        width = self.width() - 10
        height = self.height() - 10
        x_offset = 5
        y_offset = 5
        
        # Draw background grid
        painter.setPen(QPen(QColor("#333"), 1))
        for i in range(0, width, 20):
            painter.drawLine(x_offset + i, y_offset, x_offset + i, y_offset + height)
        
        # Draw FPS line
        if len(self._fps_history) > 1:
            painter.setPen(QPen(QColor("#4caf50"), 2))
            
            step_x = width / max(1, len(self._fps_history) - 1)
            max_fps = 60.0  # Assume 60fps max for scaling
            
            for i in range(len(self._fps_history) - 1):
                x1 = x_offset + i * step_x
                y1 = y_offset + height - (self._fps_history[i] / max_fps) * height
                x2 = x_offset + (i + 1) * step_x
                y2 = y_offset + height - (self._fps_history[i + 1] / max_fps) * height
                
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        
        # Draw current FPS text
        if self._fps_history:
            current_fps = self._fps_history[-1]
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawText(5, 15, f"{current_fps:.1f}")
        
        painter.end() 