"""
Enhanced UI Widgets for BBAN-Tracker Cyber-Kinetic Interface.

This module provides specialized widgets that implement the exact UI patterns
shown in the reference screenshots with pixel-perfect styling.
"""

from typing import Optional, List, Dict, Any, Callable
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QRect, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QBrush, QLinearGradient, QPainterPath, QPolygonF, QPointF
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QFrame, QSizePolicy, QProgressBar, QSlider, QComboBox,
    QSpinBox, QTextEdit, QScrollArea, QSplitter
)

from .theme_manager import theme


class CyberCard(QGroupBox):
    """Enhanced card widget with Cyber-Kinetic styling."""
    
    def __init__(self, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(title, parent)
        self._setup_styling()
    
    def _setup_styling(self):
        """Apply Cyber-Kinetic card styling."""
        self.setContentsMargins(16, 24, 16, 16)
        
        # Enhanced glow effect simulation
        custom_style = f"""
            QGroupBox {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                           stop:0 {theme.colors.BACKGROUND_MID.name()},
                           stop:1 {theme.colors.BACKGROUND_DEEP.name()});
                border: 2px solid {theme.colors.PRIMARY_INTERACTIVE.name()};
                border-radius: 12px;
                font-family: "Arial";
                font-size: 14px;
                font-weight: 600;
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                margin-top: 12px;
                padding-top: 8px;
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                border: none;
                background: {theme.colors.BACKGROUND_DEEP.name()};
            }}
        """
        self.setStyleSheet(custom_style)


class StatusIndicator(QWidget):
    """Status indicator with animated glow effects."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._status = "disconnected"
        self._animated = False
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._animate_pulse)
        self._pulse_state = 0
        
        self.setFixedSize(24, 24)
        self._setup_styling()
    
    def set_status(self, status: str, animated: bool = False):
        """Set the status (connected, disconnected, active, error)."""
        self._status = status
        self._animated = animated
        
        if animated:
            self._animation_timer.start(100)  # 10 FPS pulse
        else:
            self._animation_timer.stop()
        
        self.update()
    
    def _animate_pulse(self):
        """Animate pulsing effect."""
        self._pulse_state = (self._pulse_state + 1) % 20
        self.update()
    
    def paintEvent(self, event):
        """Custom paint for status indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Determine color based on status
        colors = {
            "connected": theme.colors.SUCCESS,
            "active": theme.colors.PRIMARY_INTERACTIVE,
            "disconnected": theme.colors.TEXT_TERTIARY,
            "error": theme.colors.ERROR,
            "warning": theme.colors.WARNING
        }
        
        base_color = colors.get(self._status, theme.colors.TEXT_TERTIARY)
        
        # Apply pulse animation
        if self._animated:
            pulse_factor = 0.7 + 0.3 * (self._pulse_state / 20.0)
            color = QColor(base_color)
            color.setAlphaF(pulse_factor)
        else:
            color = base_color
        
        # Draw indicator circle
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.lighter(150), 2))
        painter.drawEllipse(2, 2, 20, 20)
        
        # Draw inner highlight
        highlight_color = QColor(color.lighter(180))
        highlight_color.setAlphaF(0.6)
        painter.setBrush(QBrush(highlight_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(6, 6, 12, 12)
    
    def _setup_styling(self):
        """Set up basic styling."""
        self.setStyleSheet(f"""
            StatusIndicator {{
                background: transparent;
                border: none;
            }}
        """)


class MetricDisplay(QWidget):
    """Animated metric display widget."""
    
    def __init__(self, label: str, unit: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._label = label
        self._unit = unit
        self._value = 0.0
        self._target_value = 0.0
        
        self._setup_ui()
        self._setup_animation()
    
    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        
        # Label
        self._label_widget = QLabel(self._label)
        self._label_widget.setProperty("style", "caption")
        self._label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label_widget)
        
        # Value display
        self._value_widget = QLabel("0.0")
        self._value_widget.setProperty("style", "heading")
        self._value_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value_widget)
        
        # Unit label
        if self._unit:
            self._unit_widget = QLabel(self._unit)
            self._unit_widget.setProperty("style", "caption")
            self._unit_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._unit_widget)
    
    def _setup_animation(self):
        """Set up value animation."""
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._animate_value)
    
    def set_value(self, value: float, animated: bool = True):
        """Set the metric value with optional animation."""
        self._target_value = value
        
        if animated and abs(value - self._value) > 0.1:
            self._animation_timer.start(16)  # ~60 FPS
        else:
            self._value = value
            self._update_display()
    
    def _animate_value(self):
        """Animate value changes."""
        diff = self._target_value - self._value
        if abs(diff) < 0.01:
            self._value = self._target_value
            self._animation_timer.stop()
        else:
            self._value += diff * 0.1  # Smooth easing
        
        self._update_display()
    
    def _update_display(self):
        """Update the displayed value."""
        if self._value == int(self._value):
            display_value = f"{int(self._value)}"
        else:
            display_value = f"{self._value:.1f}"
        
        self._value_widget.setText(display_value)


class ProgressRing(QWidget):
    """Circular progress indicator."""
    
    def __init__(self, size: int = 80, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._progress = 0.0
        self._size = size
        self.setFixedSize(size, size)
    
    def set_progress(self, progress: float):
        """Set progress (0.0 to 1.0)."""
        self._progress = max(0.0, min(1.0, progress))
        self.update()
    
    def paintEvent(self, event):
        """Custom paint for progress ring."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background ring
        painter.setPen(QPen(theme.colors.BACKGROUND_MID, 6))
        painter.drawEllipse(6, 6, self._size - 12, self._size - 12)
        
        # Draw progress arc
        if self._progress > 0:
            painter.setPen(QPen(theme.colors.PRIMARY_INTERACTIVE, 6))
            start_angle = 90 * 16  # Start at top
            span_angle = -int(360 * 16 * self._progress)  # Clockwise
            painter.drawArc(6, 6, self._size - 12, self._size - 12, start_angle, span_angle)


class SystemStatusPanel(CyberCard):
    """System status panel showing service health."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("System Status", parent)
        self._service_indicators: Dict[str, StatusIndicator] = {}
        self._metric_displays: Dict[str, MetricDisplay] = {}
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the status panel UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Service status indicators
        services_layout = QGridLayout()
        
        services = [
            ("Tracking", "tracking"),
            ("Projection", "projection"),
            ("GUI", "gui"),
            ("Hardware", "hardware")
        ]
        
        for i, (name, key) in enumerate(services):
            label = QLabel(name)
            label.setProperty("style", "caption")
            
            indicator = StatusIndicator()
            self._service_indicators[key] = indicator
            
            services_layout.addWidget(label, i, 0)
            services_layout.addWidget(indicator, i, 1)
        
        services_group = QWidget()
        services_group.setLayout(services_layout)
        layout.addWidget(services_group)
        
        # Performance metrics
        metrics_layout = QHBoxLayout()
        
        fps_metric = MetricDisplay("FPS", "fps")
        self._metric_displays["fps"] = fps_metric
        metrics_layout.addWidget(fps_metric)
        
        latency_metric = MetricDisplay("Latency", "ms")
        self._metric_displays["latency"] = latency_metric
        metrics_layout.addWidget(latency_metric)
        
        memory_metric = MetricDisplay("Memory", "MB")
        self._metric_displays["memory"] = memory_metric
        metrics_layout.addWidget(memory_metric)
        
        metrics_group = QWidget()
        metrics_group.setLayout(metrics_layout)
        layout.addWidget(metrics_group)
    
    def update_service_status(self, service: str, status: str, animated: bool = False):
        """Update a service status indicator."""
        if service in self._service_indicators:
            self._service_indicators[service].set_status(status, animated)
    
    def update_metric(self, metric: str, value: float):
        """Update a performance metric."""
        if metric in self._metric_displays:
            self._metric_displays[metric].set_value(value)


class LogPanel(CyberCard):
    """Enhanced log display panel."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("System Log", parent)
        self._max_entries = 100
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the log panel UI."""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # Create scroll area for log entries
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Log content widget
        self._log_widget = QWidget()
        self._log_layout = QVBoxLayout(self._log_widget)
        self._log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_layout.setSpacing(2)
        self._log_layout.addStretch()
        
        self._scroll_area.setWidget(self._log_widget)
        layout.addWidget(self._scroll_area)
        
        # Style the scroll area
        self._scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {theme.colors.PRIMARY_DARKER.name()};
                border-radius: 6px;
                background: {theme.colors.BACKGROUND_DEEP.name()};
            }}
        """)
    
    def add_log_entry(self, message: str, level: str = "info", timestamp: str = ""):
        """Add a new log entry."""
        # Remove old entries if at limit
        if self._log_layout.count() > self._max_entries:
            item = self._log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Create log entry widget
        entry = LogEntry(message, level, timestamp)
        
        # Insert before the stretch
        self._log_layout.insertWidget(self._log_layout.count() - 1, entry)
        
        # Auto-scroll to bottom
        QTimer.singleShot(10, self._scroll_to_bottom)
    
    def _scroll_to_bottom(self):
        """Scroll to the bottom of the log."""
        scrollbar = self._scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class LogEntry(QWidget):
    """Individual log entry widget."""
    
    def __init__(self, message: str, level: str = "info", timestamp: str = ""):
        super().__init__()
        self._message = message
        self._level = level
        self._timestamp = timestamp
        
        self._setup_ui()
        self._setup_styling()
    
    def _setup_ui(self):
        """Set up the log entry UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        
        # Level indicator
        level_color = self._get_level_color()
        level_indicator = QLabel("●")
        level_indicator.setStyleSheet(f"color: {level_color.name()}; font-size: 14px;")
        layout.addWidget(level_indicator)
        
        # Timestamp
        if self._timestamp:
            timestamp_label = QLabel(self._timestamp)
            timestamp_label.setProperty("style", "caption")
            timestamp_label.setMinimumWidth(60)
            layout.addWidget(timestamp_label)
        
        # Message
        message_label = QLabel(self._message)
        message_label.setWordWrap(True)
        layout.addWidget(message_label, 1)
    
    def _get_level_color(self) -> QColor:
        """Get color for log level."""
        colors = {
            "error": theme.colors.ERROR,
            "warning": theme.colors.WARNING,
            "success": theme.colors.SUCCESS,
            "info": theme.colors.PRIMARY_INTERACTIVE,
            "debug": theme.colors.TEXT_TERTIARY
        }
        return colors.get(self._level, theme.colors.TEXT_PRIMARY)
    
    def _setup_styling(self):
        """Set up log entry styling."""
        self.setStyleSheet(f"""
            LogEntry {{
                background: {theme.colors.BACKGROUND_MID.name()};
                border-radius: 4px;
                margin: 1px 0;
            }}
            
            LogEntry:hover {{
                background: {theme.colors.BACKGROUND_MID.lighter(110).name()};
            }}
        """)


class ActionButton(QPushButton):
    """Enhanced action button with Cyber-Kinetic styling."""
    
    def __init__(self, text: str, style: str = "primary", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._button_style = style
        self._setup_styling()
    
    def _setup_styling(self):
        """Apply enhanced button styling."""
        # Set style property for CSS selector
        self.setProperty("style", self._button_style)
        
        # Enhanced styling
        if self._button_style == "secondary":
            custom_style = f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                               stop:0 {theme.colors.SECONDARY_DARKER.name()},
                               stop:1 {theme.colors.SECONDARY_INTERACTIVE.name()});
                    border: 2px solid {theme.colors.SECONDARY_INTERACTIVE.name()};
                    border-radius: 8px;
                    color: {theme.colors.TEXT_PRIMARY.name()};
                    font-family: "Segoe UI";
                    font-size: 12px;
                    font-weight: 600;
                    padding: 10px 20px;
                    margin: 2px;
                }}
                
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                               stop:0 {theme.colors.SECONDARY_INTERACTIVE.name()},
                               stop:1 {theme.colors.SECONDARY_INTERACTIVE.lighter(120).name()});
                    border: 2px solid {theme.colors.SECONDARY_INTERACTIVE.lighter(130).name()};
                }}
            """
            self.setStyleSheet(custom_style)
        elif self._button_style == "ghost":
            custom_style = f"""
                QPushButton {{
                    background: transparent;
                    border: 2px solid {theme.colors.PRIMARY_INTERACTIVE.name()};
                    border-radius: 8px;
                    color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                    font-family: "Segoe UI";
                    font-size: 12px;
                    font-weight: 600;
                    padding: 10px 20px;
                    margin: 2px;
                }}
                
                QPushButton:hover {{
                    background: {theme.colors.PRIMARY_INTERACTIVE.name()};
                    color: {theme.colors.BACKGROUND_DEEP.name()};
                }}
            """
            self.setStyleSheet(custom_style)


class SettingsGroup(CyberCard):
    """Settings group with enhanced controls."""
    
    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(title, parent)
        self._controls: Dict[str, QWidget] = {}
        self._layout = QGridLayout()
        self.setLayout(self._layout)
        self._row_count = 0
    
    def add_slider(self, name: str, label: str, min_val: int, max_val: int, default: int, callback: Optional[Callable] = None):
        """Add a slider control."""
        # Label
        label_widget = QLabel(label)
        self._layout.addWidget(label_widget, self._row_count, 0)
        
        # Slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        
        if callback:
            slider.valueChanged.connect(callback)
        
        self._layout.addWidget(slider, self._row_count, 1)
        
        # Value display
        value_label = QLabel(str(default))
        value_label.setMinimumWidth(40)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider.valueChanged.connect(lambda v: value_label.setText(str(v)))
        
        self._layout.addWidget(value_label, self._row_count, 2)
        
        self._controls[name] = slider
        self._row_count += 1
    
    def add_combo(self, name: str, label: str, options: List[str], default: int = 0, callback: Optional[Callable] = None):
        """Add a combo box control."""
        # Label
        label_widget = QLabel(label)
        self._layout.addWidget(label_widget, self._row_count, 0)
        
        # Combo box
        combo = QComboBox()
        combo.addItems(options)
        combo.setCurrentIndex(default)
        
        if callback:
            combo.currentIndexChanged.connect(callback)
        
        self._layout.addWidget(combo, self._row_count, 1, 1, 2)
        
        self._controls[name] = combo
        self._row_count += 1
    
    def add_spinbox(self, name: str, label: str, min_val: int, max_val: int, default: int, callback: Optional[Callable] = None):
        """Add a spin box control."""
        # Label
        label_widget = QLabel(label)
        self._layout.addWidget(label_widget, self._row_count, 0)
        
        # Spin box
        spinbox = QSpinBox()
        spinbox.setRange(min_val, max_val)
        spinbox.setValue(default)
        
        if callback:
            spinbox.valueChanged.connect(callback)
        
        self._layout.addWidget(spinbox, self._row_count, 1, 1, 2)
        
        self._controls[name] = spinbox
        self._row_count += 1
    
    def get_value(self, name: str) -> Any:
        """Get the current value of a control."""
        if name not in self._controls:
            return None
        
        control = self._controls[name]
        if isinstance(control, QSlider) or isinstance(control, QSpinBox):
            return control.value()
        elif isinstance(control, QComboBox):
            return control.currentIndex()
        
        return None 


class ShardButton(QPushButton):
    """Custom polygon-shaped button matching reference screenshot shard designs."""
    
    def __init__(self, text: str, shard_type: str, icon_path: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._shard_type = shard_type
        self._icon_path = icon_path
        self._hovered = False
        self._pressed = False
        self._hover_scale = 1.0
        
        # Set up the button properties
        self.setMinimumSize(200, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Create hover animation
        self._hover_animation = QPropertyAnimation(self, b"hover_scale")
        self._hover_animation.setDuration(300)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Apply shard-specific styling
        self._apply_shard_style()
        
        # Enable hover events
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    
    def _apply_shard_style(self):
        """Apply shard-specific colors and styling."""
        style = theme.get_shard_button_style(self._shard_type)
        base_style = f"""
            ShardButton {{
                {style}
                font-family: "Arial";
                font-size: 28px;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
            ShardButton:hover {{
                filter: brightness(1.1);
            }}
        """
        self.setStyleSheet(base_style)
    
    def _get_shard_polygon(self) -> QPolygonF:
        """Get the polygon shape for this shard type."""
        w, h = self.width(), self.height()
        
        if self._shard_type == "match":
            # Match shard: polygon(0% 15%, 20% 0%, 100% 30%, 100% 85%, 80% 100%, 0% 70%)
            return QPolygonF([
                QPointF(0, h * 0.15),          # 0% 15%
                QPointF(w * 0.20, 0),          # 20% 0%
                QPointF(w, h * 0.30),          # 100% 30%
                QPointF(w, h * 0.85),          # 100% 85%
                QPointF(w * 0.80, h),          # 80% 100%
                QPointF(0, h * 0.70)           # 0% 70%
            ])
        elif self._shard_type == "freeplay":
            # Free play shard: polygon(20% 0%, 100% 15%, 100% 70%, 80% 100%, 0% 85%, 0% 30%)
            return QPolygonF([
                QPointF(w * 0.20, 0),          # 20% 0%
                QPointF(w, h * 0.15),          # 100% 15%
                QPointF(w, h * 0.70),          # 100% 70%
                QPointF(w * 0.80, h),          # 80% 100%
                QPointF(0, h * 0.85),          # 0% 85%
                QPointF(0, h * 0.30)           # 0% 30%
            ])
        elif self._shard_type == "systemhub":
            # System hub shard: polygon(10% 0%, 90% 0%, 100% 50%, 90% 100%, 10% 100%, 0% 50%)
            return QPolygonF([
                QPointF(w * 0.10, 0),          # 10% 0%
                QPointF(w * 0.90, 0),          # 90% 0%
                QPointF(w, h * 0.50),          # 100% 50%
                QPointF(w * 0.90, h),          # 90% 100%
                QPointF(w * 0.10, h),          # 10% 100%
                QPointF(0, h * 0.50)           # 0% 50%
            ])
        else:
            # Default rectangular shape
            return QPolygonF([
                QPointF(0, 0),
                QPointF(w, 0),
                QPointF(w, h),
                QPointF(0, h)
            ])
    
    def _get_shard_colors(self) -> tuple:
        """Get background and text colors for this shard type."""
        if self._shard_type == "match":
            return theme.colors.MENU_SHARD_MATCH_BG, theme.colors.MENU_SHARD_MATCH_TEXT
        elif self._shard_type == "freeplay":
            return theme.colors.MENU_SHARD_FREEPLAY_BG, theme.colors.MENU_SHARD_FREEPLAY_TEXT
        elif self._shard_type == "systemhub":
            return theme.colors.MENU_SHARD_SYSTEMHUB_BG, theme.colors.MENU_SHARD_SYSTEMHUB_TEXT
        else:
            return theme.colors.PRIMARY_INTERACTIVE, theme.colors.TEXT_PRIMARY
    
    def paintEvent(self, event):
        """Custom paint event to draw the polygon shape."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get shard polygon and colors
        polygon = self._get_shard_polygon()
        bg_color, text_color = self._get_shard_colors()
        
        # Apply hover scaling
        if self._hovered:
            painter.scale(self._hover_scale, self._hover_scale)
            # Center the scaled shape
            scale_offset = (1.0 - self._hover_scale) / 2.0
            painter.translate(self.width() * scale_offset, self.height() * scale_offset)
        
        # Create painter path for the shard shape
        path = QPainterPath()
        path.addPolygon(polygon)
        
        # Draw the shard background
        if self._hovered:
            # Brighten color on hover
            hover_color = QColor(bg_color)
            hover_color = hover_color.lighter(120)
            painter.fillPath(path, QBrush(hover_color))
            
            # Add glow effect
            glow_pen = QPen(bg_color.lighter(150), 3)
            painter.setPen(glow_pen)
            painter.drawPath(path)
        else:
            painter.fillPath(path, QBrush(bg_color))
        
        # Draw the shard content (icon and text)
        painter.setClipPath(path)  # Clip content to shard shape
        self._draw_shard_content(painter, text_color)
    
    def _draw_shard_content(self, painter: QPainter, text_color: QColor):
        """Draw the icon and text content inside the shard."""
        rect = self.rect()
        
        # Set text properties
        font = theme.fonts.get_shard_label_font(22)  # Smaller for button size
        painter.setFont(font)
        painter.setPen(QPen(text_color))
        
        # Draw text centered in the shard
        text_rect = QRectF(rect.adjusted(20, 20, -20, -20))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.text())
        
        # TODO: Draw icon above text if icon_path is provided
        # This would require loading and drawing an icon image
    
    def enterEvent(self, event):
        """Handle mouse enter event."""
        self._hovered = True
        self._start_hover_animation(1.05)  # Scale to 105%
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave event."""
        self._hovered = False
        self._start_hover_animation(1.0)   # Scale back to 100%
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press event."""
        self._pressed = True
        self.update()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release event."""
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)
    
    def _start_hover_animation(self, target_scale: float):
        """Start hover scale animation."""
        self._hover_animation.setStartValue(self._hover_scale)
        self._hover_animation.setEndValue(target_scale)
        self._hover_animation.start()
    
    def get_hover_scale(self) -> float:
        """Get current hover scale."""
        return self._hover_scale
    
    def set_hover_scale(self, scale: float):
        """Set hover scale and trigger repaint."""
        self._hover_scale = scale
        self.update()
    
    # Property for animation
    hover_scale = Qt.Property(float, get_hover_scale, set_hover_scale)


class KioskMainMenu(QWidget):
    """Main menu widget matching the reference MainMenu.tsx design."""
    
    # Signals for navigation
    navigate_to_match = Signal()
    navigate_to_freeplay = Signal()
    navigate_to_systemhub = Signal()
    exit_requested = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_styling()
        self._setup_animations()
    
    def _setup_ui(self):
        """Set up the main menu UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(32)
        
        # Create header with title and exit button
        self._create_header(layout)
        
        # Create main shard buttons area
        self._create_shard_area(layout)
        
        # Create footer
        self._create_footer(layout)
    
    def _create_header(self, layout: QVBoxLayout):
        """Create the header with title and exit button."""
        header_layout = QHBoxLayout()
        
        # Main title
        title = QLabel("BeysionXR Kiosk")
        title.setProperty("style", "kiosk-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Apply title glow effect
        title.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.PRIMARY_INTERACTIVE.name()};
                font-family: "Arial";
                font-size: 48px;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 4px;
            }}
        """)
        
        header_layout.addStretch()
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        # Exit button (top-right)
        exit_btn = ActionButton("EXIT", "error")
        exit_btn.clicked.connect(self.exit_requested.emit)
        exit_btn.setMaximumSize(100, 40)
        
        # Position exit button
        exit_layout = QHBoxLayout()
        exit_layout.addStretch()
        exit_layout.addWidget(exit_btn)
        
        # Combine header elements
        header_widget = QWidget()
        header_widget.setLayout(header_layout)
        
        exit_widget = QWidget()
        exit_widget.setLayout(exit_layout)
        
        layout.addWidget(exit_widget)
        layout.addWidget(header_widget)
    
    def _create_shard_area(self, layout: QVBoxLayout):
        """Create the main shard buttons area."""
        shard_layout = QHBoxLayout()
        shard_layout.setSpacing(32)
        
        # Match shard
        match_shard = ShardButton("Match", "match")
        match_shard.clicked.connect(self.navigate_to_match.emit)
        shard_layout.addWidget(match_shard)
        
        # Free Play shard
        freeplay_shard = ShardButton("Free Play", "freeplay")
        freeplay_shard.clicked.connect(self.navigate_to_freeplay.emit)
        shard_layout.addWidget(freeplay_shard)
        
        # System Hub shard
        systemhub_shard = ShardButton("System Hub", "systemhub")
        systemhub_shard.clicked.connect(self.navigate_to_systemhub.emit)
        shard_layout.addWidget(systemhub_shard)
        
        # Add the shard area to main layout with stretch
        layout.addStretch()
        shard_widget = QWidget()
        shard_widget.setLayout(shard_layout)
        layout.addWidget(shard_widget)
        layout.addStretch()
    
    def _create_footer(self, layout: QVBoxLayout):
        """Create the footer text."""
        footer = QLabel("BeysionXR Kiosk Interface - BBAN Edition")
        footer.setProperty("style", "caption")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"""
            QLabel {{
                color: {theme.colors.TEXT_TERTIARY.name()};
                font-family: "Inter", "Segoe UI";
                font-size: 12px;
                opacity: 0.75;
            }}
        """)
        
        layout.addWidget(footer)
    
    def _setup_styling(self):
        """Set up the main menu styling."""
        self.setStyleSheet(f"""
            KioskMainMenu {{
                background-color: {theme.colors.BACKGROUND_DEEP.name()};
                background-image: none;
            }}
        """)
    
    def _setup_animations(self):
        """Set up any entrance animations."""
        # Could add fade-in animation here
        pass


class BackgroundWidget(QWidget):
    """Background widget with BBAN angular streaks."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    
    def paintEvent(self, event):
        """Paint the background with angular streaks."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Fill with base background color
        painter.fillRect(self.rect(), theme.colors.BACKGROUND_DEEP)
        
        # Draw green streak (top-left)
        green_polygon = QPolygonF([
            QPointF(0, 0),                                    # 0% 0%
            QPointF(self.width() * 0.65, 0),                 # 65% 0%
            QPointF(self.width() * 0.25, self.height() * 0.75),  # 25% 75%
            QPointF(0, self.height() * 0.55)                 # 0% 55%
        ])
        
        green_color = QColor(theme.colors.BBAN_GREEN)
        green_color.setAlphaF(0.4)  # 40% opacity
        painter.fillPath(QPainterPath().addPolygon(green_polygon), QBrush(green_color))
        
        # Draw yellow streak (bottom-right)
        yellow_polygon = QPolygonF([
            QPointF(self.width(), self.height()),             # 100% 100%
            QPointF(self.width() * 0.35, self.height()),     # 35% 100%
            QPointF(self.width() * 0.75, self.height() * 0.25),  # 75% 25%
            QPointF(self.width(), self.height() * 0.45)      # 100% 45%
        ])
        
        yellow_color = QColor(theme.colors.BBAN_YELLOW)
        yellow_color.setAlphaF(0.4)  # 40% opacity
        painter.fillPath(QPainterPath().addPolygon(yellow_polygon), QBrush(yellow_color)) 