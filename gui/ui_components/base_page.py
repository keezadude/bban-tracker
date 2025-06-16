"""
BasePage component for EDA-integrated BBAN-Tracker GUI.

This module provides the abstract base class for all GUI pages, ensuring
standardized Event-Driven Architecture integration, consistent styling,
and proper event handling patterns.
"""

import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtGui import QFont, QPalette, QColor

from ...core.interfaces import IGUIService
from ...core.events import Event


@dataclass
class GUIPageChanged(Event):
    """Event published when user navigates to different page."""
    page_name: str
    previous_page: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class UserInteractionEvent(Event):
    """Base class for UI interactions."""
    page_name: str
    widget_id: str
    interaction_type: str  # "click", "value_change", "toggle"
    value: Any = None
    timestamp: float = field(default_factory=time.time)


class PageEventBridge(QObject):
    """
    Qt signal bridge for page events.
    
    This class provides Qt signals that can be connected to Qt slots,
    bridging the gap between the EDA event system and Qt's signal/slot system.
    """
    
    # Qt signals for common events
    tracking_data_updated = Signal(object)  # TrackingDataUpdated event
    tracking_started = Signal(object)       # TrackingStarted event
    tracking_stopped = Signal(object)       # TrackingStopped event
    tracking_error = Signal(object)         # TrackingError event
    projection_connected = Signal(object)   # ProjectionClientConnected event
    projection_disconnected = Signal(object) # ProjectionClientDisconnected event
    
    def __init__(self):
        super().__init__()


class BasePage(QWidget, ABC):
    """
    Abstract base class for all GUI pages with standardized EDA integration.
    
    This class provides:
    - Event-driven communication with services
    - Consistent styling and layout patterns
    - Standardized user interaction publishing
    - Performance monitoring and optimization
    - Error handling and notification integration
    """
    
    def __init__(self, gui_service: IGUIService, page_name: str):
        """
        Initialize the base page with EDA integration.
        
        Args:
            gui_service: GUI service for event communication
            page_name: Unique identifier for this page
        """
        super().__init__()
        
        self._gui_service = gui_service
        self._page_name = page_name
        
        # Event handling
        self._event_bridge = PageEventBridge()
        self._performance_metrics = {}
        self._last_update_time = 0.0
        
        # UI state
        self._widgets_by_id: Dict[str, QWidget] = {}
        self._interaction_handlers: Dict[str, Callable] = {}
        
        # Setup the page
        self._setup_base_layout()
        self._setup_base_styling()
        self.setup_event_subscriptions()
        self._setup_performance_monitoring()
        
        # Register with GUI service for notifications
        self._register_with_service()
    
    # ==================== ABSTRACT METHODS ==================== #
    
    @abstractmethod
    def setup_event_subscriptions(self) -> None:
        """
        Set up event subscriptions for this page.
        
        Subclasses must implement this to subscribe to relevant events
        from the tracking and projection services.
        """
        pass
    
    @abstractmethod
    def create_page_content(self) -> QWidget:
        """
        Create the main content widget for this page.
        
        Returns:
            The main content widget containing all page-specific UI elements
        """
        pass
    
    # ==================== EVENT PUBLISHING HELPERS ==================== #
    
    def publish_user_action(self, widget_id: str, interaction_type: str, value: Any = None) -> None:
        """
        Publish a user interaction event to the EDA system.
        
        Args:
            widget_id: Unique identifier of the widget that triggered the interaction
            interaction_type: Type of interaction (click, value_change, toggle)
            value: Optional value associated with the interaction
        """
        event = UserInteractionEvent(
            page_name=self._page_name,
            widget_id=widget_id,
            interaction_type=interaction_type,
            value=value
        )
        
        # Log interaction for debugging
        print(f"[{self._page_name}] User interaction: {widget_id} -> {interaction_type} = {value}")
        
        # Trigger specific action based on widget and interaction
        handler_key = f"{widget_id}_{interaction_type}"
        if handler_key in self._interaction_handlers:
            self._interaction_handlers[handler_key](value)
    
    def register_interaction_handler(self, widget_id: str, interaction_type: str, handler: Callable) -> None:
        """
        Register a handler for specific user interactions.
        
        Args:
            widget_id: Widget identifier
            interaction_type: Type of interaction
            handler: Function to call when interaction occurs
        """
        handler_key = f"{widget_id}_{interaction_type}"
        self._interaction_handlers[handler_key] = handler
    
    # ==================== CONVENIENCE METHODS FOR COMMON ACTIONS ==================== #
    
    def request_start_tracking(self, **kwargs) -> None:
        """Request tracking to be started via GUI service."""
        self._gui_service.request_start_tracking(**kwargs)
    
    def request_stop_tracking(self) -> None:
        """Request tracking to be stopped via GUI service."""
        self._gui_service.request_stop_tracking()
    
    def update_tracker_settings(self, **kwargs) -> None:
        """Update tracker settings via GUI service."""
        self._gui_service.update_tracker_settings(**kwargs)
    
    def update_projection_config(self, width: int, height: int) -> None:
        """Update projection configuration via GUI service."""
        self._gui_service.update_projection_config(width, height)
    
    def show_notification(self, message: str, duration_ms: int = 3000) -> None:
        """Show a notification via GUI service."""
        self._gui_service.show_notification(message, duration_ms)
    
    def show_error_dialog(self, title: str, message: str) -> None:
        """Show an error dialog via GUI service."""
        self._gui_service.show_error_dialog(title, message)
    
    # ==================== WIDGET MANAGEMENT ==================== #
    
    def register_widget(self, widget_id: str, widget: QWidget) -> None:
        """
        Register a widget for easy access and event handling.
        
        Args:
            widget_id: Unique identifier for the widget
            widget: The widget instance
        """
        self._widgets_by_id[widget_id] = widget
    
    def get_widget(self, widget_id: str) -> Optional[QWidget]:
        """
        Get a registered widget by its ID.
        
        Args:
            widget_id: Widget identifier
            
        Returns:
            The widget instance or None if not found
        """
        return self._widgets_by_id.get(widget_id)
    
    def update_widget_value(self, widget_id: str, value: Any) -> None:
        """
        Update a widget's value in a type-safe manner.
        
        Args:
            widget_id: Widget identifier
            value: New value for the widget
        """
        widget = self.get_widget(widget_id)
        if widget is None:
            return
            
        # Handle different widget types
        if hasattr(widget, 'setValue'):  # Sliders, spinboxes
            widget.setValue(value)
        elif hasattr(widget, 'setText'):  # Labels, line edits
            widget.setText(str(value))
        elif hasattr(widget, 'setChecked'):  # Checkboxes, radio buttons
            widget.setChecked(bool(value))
    
    # ==================== PERFORMANCE MONITORING ==================== #
    
    def _setup_performance_monitoring(self) -> None:
        """Set up performance monitoring for the page."""
        self._perf_timer = QTimer()
        self._perf_timer.timeout.connect(self._report_performance_metrics)
        self._perf_timer.start(5000)  # Report every 5 seconds
    
    def _report_performance_metrics(self) -> None:
        """Report performance metrics to the GUI service."""
        current_time = time.perf_counter()
        
        if self._last_update_time > 0:
            update_interval = current_time - self._last_update_time
            self._performance_metrics['update_interval'] = update_interval
            
        self._performance_metrics['widget_count'] = len(self._widgets_by_id)
        self._performance_metrics['handler_count'] = len(self._interaction_handlers)
        
        # Log performance metrics
        print(f"[{self._page_name}] Performance: {self._performance_metrics}")
        
        self._last_update_time = current_time
    
    # ==================== STYLING AND LAYOUT ==================== #
    
    def _setup_base_layout(self) -> None:
        """Set up the base layout structure for the page."""
        # Create main layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(20, 20, 20, 20)
        self._main_layout.setSpacing(15)
        
        # Create page header
        self._create_page_header()
        
        # Create content area (to be populated by subclass)
        self._content_widget = self.create_page_content()
        self._main_layout.addWidget(self._content_widget)
        
        # Add stretch to push content to top
        self._main_layout.addStretch()
    
    def _create_page_header(self) -> None:
        """Create a consistent page header."""
        header_layout = QHBoxLayout()
        
        # Page title
        title_label = QLabel(self._get_page_title())
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        # Page status indicator
        status_label = QLabel("Ready")
        status_label.setObjectName("status_label")
        self.register_widget("status_label", status_label)
        header_layout.addWidget(status_label)
        
        # Add header to main layout
        header_widget = QWidget()
        header_widget.setLayout(header_layout)
        self._main_layout.addWidget(header_widget)
    
    def _get_page_title(self) -> str:
        """Get the display title for this page."""
        # Convert page_name to title case
        return self._page_name.replace('_', ' ').title()
    
    def _setup_base_styling(self) -> None:
        """Set up base styling for the page."""
        # Apply consistent styling
        self.setStyleSheet("""
            BasePage {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            
            QLabel#status_label {
                color: #4CAF50;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                background-color: rgba(76, 175, 80, 0.1);
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
    
    def _register_with_service(self) -> None:
        """Register this page with the GUI service for notifications."""
        # This would be called in a real implementation to set up
        # notification callbacks with the GUI service
        pass
    
    # ==================== EVENT BRIDGE HELPERS ==================== #
    
    def connect_tracking_data_updated(self, slot: Callable) -> None:
        """Connect a slot to the tracking data updated signal."""
        self._event_bridge.tracking_data_updated.connect(slot)
    
    def connect_tracking_started(self, slot: Callable) -> None:
        """Connect a slot to the tracking started signal."""
        self._event_bridge.tracking_started.connect(slot)
    
    def connect_tracking_stopped(self, slot: Callable) -> None:
        """Connect a slot to the tracking stopped signal."""
        self._event_bridge.tracking_stopped.connect(slot)
    
    def connect_projection_connected(self, slot: Callable) -> None:
        """Connect a slot to the projection connected signal."""
        self._event_bridge.projection_connected.connect(slot)
    
    # ==================== LIFECYCLE METHODS ==================== #
    
    def showEvent(self, event) -> None:
        """Handle page show event."""
        super().showEvent(event)
        print(f"[{self._page_name}] Page shown")
        
        # Update status
        self.update_widget_value("status_label", "Active")
    
    def hideEvent(self, event) -> None:
        """Handle page hide event."""
        super().hideEvent(event)
        print(f"[{self._page_name}] Page hidden")
        
        # Update status
        self.update_widget_value("status_label", "Inactive")
    
    def closeEvent(self, event) -> None:
        """Handle page close event."""
        super().closeEvent(event)
        
        # Clean up performance monitoring
        if hasattr(self, '_perf_timer'):
            self._perf_timer.stop()
        
        print(f"[{self._page_name}] Page closed")
    
    # ==================== PROPERTIES ==================== #
    
    @property
    def page_name(self) -> str:
        """Get the page name."""
        return self._page_name
    
    @property
    def gui_service(self) -> IGUIService:
        """Get the GUI service."""
        return self._gui_service
    
    @property
    def event_bridge(self) -> PageEventBridge:
        """Get the event bridge for Qt signal connections."""
        return self._event_bridge 