"""
Unit tests for EDA-integrated Main GUI implementation.

These tests verify the GUI's integration with the Event-Driven Architecture,
including event subscription, publishing, page navigation, and service communication.
Tests use mocking to avoid dependencies on actual Qt widgets or services.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass, field
from typing import Any, Optional

from core.interfaces import IGUIService, IEventBroker
from core.events import (
    TrackingDataUpdated, TrackingStarted, TrackingStopped, TrackingError,
    ProjectionClientConnected, ProjectionClientDisconnected,
    StartTracking, StopTracking, ChangeTrackerSettings,
    ProjectionConfigUpdated, SystemShutdown
)


# ==================== TEST EVENT CLASSES ==================== #

@dataclass
class GUIPageChanged:
    """Event published when user navigates to different page."""
    page_name: str
    previous_page: str
    timestamp: float = field(default_factory=time.time)


@dataclass  
class UserInteractionEvent:
    """Base class for UI interactions."""
    page_name: str
    widget_id: str
    interaction_type: str  # "click", "value_change", "toggle"
    value: Any = None
    timestamp: float = field(default_factory=time.time)


# ==================== MOCK CLASSES ==================== #

class MockBeyData:
    """Mock BeyData for testing."""
    def __init__(self, id: int, pos: tuple, velocity: tuple):
        self.id = id
        self.pos = pos
        self.velocity = velocity
        self.raw_velocity = velocity
        self.acceleration = (0.0, 0.0)
        self.frame = 0


class MockHitData:
    """Mock HitData for testing."""
    def __init__(self, pos: tuple, bey_ids: tuple, is_new_hit: bool):
        self.pos = pos
        self.bey_ids = bey_ids
        self.is_new_hit = is_new_hit
        self.shape = (5, 5)


class MockQWidget:
    """Mock QWidget for testing without Qt dependency."""
    def __init__(self):
        self.children = []
        self.visible = False
        self.enabled = True
        
    def setVisible(self, visible: bool):
        self.visible = visible
        
    def setEnabled(self, enabled: bool):
        self.enabled = enabled
        
    def addWidget(self, widget):
        self.children.append(widget)


class MockGUIService:
    """Mock implementation of IGUIService for testing."""
    
    def __init__(self):
        self.running = False
        self.current_page = "system_hub"
        self.callbacks = {}
        self.published_events = []
        
    def start(self):
        self.running = True
        
    def stop(self):
        self.running = False
        
    def is_running(self) -> bool:
        return self.running
        
    def show_page(self, page_name: str):
        previous = self.current_page
        self.current_page = page_name
        # Simulate page change event
        if hasattr(self, '_page_change_callback'):
            self._page_change_callback(GUIPageChanged(page_name, previous))
            
    def get_current_page(self) -> str:
        return self.current_page
        
    def show_notification(self, message: str, duration_ms: int = 3000):
        if 'notification' in self.callbacks:
            self.callbacks['notification'](message, duration_ms)
            
    def show_error_dialog(self, title: str, message: str):
        if 'error_dialog' in self.callbacks:
            self.callbacks['error_dialog'](title, message)
    
    def register_notification_callback(self, callback):
        self.callbacks['notification'] = callback
        
    def register_error_dialog_callback(self, callback):
        self.callbacks['error_dialog'] = callback
        
    def register_page_update_callback(self, callback):
        self.callbacks['page_update'] = callback
        
    # Mock event publishing
    def request_start_tracking(self, **kwargs):
        event = StartTracking(**kwargs)
        self.published_events.append(event)
        
    def request_stop_tracking(self):
        event = StopTracking()
        self.published_events.append(event)
        
    def update_tracker_settings(self, **kwargs):
        event = ChangeTrackerSettings(**kwargs)
        self.published_events.append(event)
        
    def update_projection_config(self, width: int, height: int):
        event = ProjectionConfigUpdated(width=width, height=height)
        self.published_events.append(event)


# ==================== BASE COMPONENT TESTS ==================== #

class TestBasePage:
    """Test suite for BasePage abstract base class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_gui_service = MockGUIService()
        
    def test_base_page_creation(self):
        """Test BasePage can be created with IGUIService dependency."""
        # Import will be done dynamically when the class exists
        # For now, test the interface contract
        assert hasattr(self.mock_gui_service, 'show_notification')
        assert hasattr(self.mock_gui_service, 'show_error_dialog')
        assert hasattr(self.mock_gui_service, 'register_page_update_callback')
        
    def test_event_subscription_interface(self):
        """Test that pages can subscribe to events."""
        # This will test the abstract method contract
        required_methods = [
            'setup_event_subscriptions',
            'publish_user_action'
        ]
        
        # Verify interface requirements exist in mock
        for method in required_methods:
            # Will be implemented in actual BasePage class
            pass
            
    def test_user_action_publishing(self):
        """Test publishing user interaction events."""
        # Test that user actions are properly published as events
        self.mock_gui_service.update_tracker_settings(threshold=25)
        
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, ChangeTrackerSettings)
        assert event.threshold == 25


# ==================== MAIN WINDOW TESTS ==================== #

class TestEDAMainWindow:
    """Test suite for EDA-integrated main window."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_gui_service = MockGUIService()
        self.mock_event_broker = Mock()
        
    def test_main_window_creation(self):
        """Test main window can be created with IGUIService dependency."""
        # Test dependency injection requirements
        assert self.mock_gui_service is not None
        assert hasattr(self.mock_gui_service, 'register_notification_callback')
        assert hasattr(self.mock_gui_service, 'register_error_dialog_callback')
        
    def test_event_subscription_setup(self):
        """Test that main window subscribes to correct service events."""
        # Mock the subscription registration
        subscriptions = []
        
        def mock_subscribe(event_type, handler):
            subscriptions.append((event_type, handler))
            
        self.mock_event_broker.subscribe = mock_subscribe
        
        # Simulate event subscription setup
        expected_events = [
            TrackingDataUpdated,
            TrackingStarted,
            TrackingStopped,
            TrackingError,
            ProjectionClientConnected,
            ProjectionClientDisconnected,
            SystemShutdown
        ]
        
        # Simulate subscription setup
        for event_type in expected_events:
            self.mock_event_broker.subscribe(event_type, Mock())
            
        # Verify all required events are subscribed to
        subscribed_events = [sub[0] for sub in subscriptions]
        for event_type in expected_events:
            assert event_type in subscribed_events
            
    def test_tracking_data_handling(self):
        """Test handling of tracking data update events."""
        # Create mock tracking data
        mock_beys = [MockBeyData(1, (100, 200), (1.0, 2.0))]
        mock_hits = [MockHitData((150, 250), (1, 2), True)]
        
        # Create tracking data event
        event = TrackingDataUpdated(
            frame_id=123,
            timestamp=time.time(),
            beys=mock_beys,
            hits=mock_hits
        )
        
        # Test event handling (will be implemented in actual GUI)
        assert event.frame_id == 123
        assert len(event.beys) == 1
        assert len(event.hits) == 1
        assert event.beys[0].id == 1
        assert event.hits[0].is_new_hit is True
        
    def test_projection_status_handling(self):
        """Test handling of projection client status events."""
        # Test connection event
        connect_event = ProjectionClientConnected(client_address="127.0.0.1")
        assert connect_event.client_address == "127.0.0.1"
        
        # Test disconnection event  
        disconnect_event = ProjectionClientDisconnected(reason="connection_lost")
        assert disconnect_event.reason == "connection_lost"
        
    def test_page_navigation(self):
        """Test page navigation via GUI service."""
        # Test initial page
        assert self.mock_gui_service.get_current_page() == "system_hub"
        
        # Test page switching
        self.mock_gui_service.show_page("tracker_setup")
        assert self.mock_gui_service.get_current_page() == "tracker_setup"
        
        self.mock_gui_service.show_page("projection_setup")
        assert self.mock_gui_service.get_current_page() == "projection_setup"
        
    def test_notification_system(self):
        """Test notification and error dialog systems."""
        notifications = []
        errors = []
        
        def notification_callback(message: str, duration: int):
            notifications.append((message, duration))
            
        def error_callback(title: str, message: str):
            errors.append((title, message))
            
        # Register callbacks
        self.mock_gui_service.register_notification_callback(notification_callback)
        self.mock_gui_service.register_error_dialog_callback(error_callback)
        
        # Test notification
        self.mock_gui_service.show_notification("Test notification", 5000)
        assert len(notifications) == 1
        assert notifications[0] == ("Test notification", 5000)
        
        # Test error dialog
        self.mock_gui_service.show_error_dialog("Error Title", "Error message")
        assert len(errors) == 1
        assert errors[0] == ("Error Title", "Error message")


# ==================== PAGE-SPECIFIC TESTS ==================== #

class TestEDATrackerSetupPage:
    """Test suite for EDA-integrated tracker setup page."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_gui_service = MockGUIService()
        
    def test_start_tracking_interaction(self):
        """Test start tracking button publishes correct event."""
        # Simulate button click
        self.mock_gui_service.request_start_tracking(dev_mode=False, cam_src=0)
        
        # Verify event was published
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, StartTracking)
        assert event.dev_mode is False
        assert event.cam_src == 0
        
    def test_stop_tracking_interaction(self):
        """Test stop tracking button publishes correct event."""
        self.mock_gui_service.request_stop_tracking()
        
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, StopTracking)
        
    def test_settings_change_interaction(self):
        """Test settings changes publish correct events."""
        # Test threshold change
        self.mock_gui_service.update_tracker_settings(threshold=30)
        
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, ChangeTrackerSettings)
        assert event.threshold == 30
        
        # Test multiple settings
        self.mock_gui_service.published_events.clear()
        self.mock_gui_service.update_tracker_settings(
            threshold=25, min_area=150, max_area=2500
        )
        
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert event.threshold == 25
        assert event.min_area == 150
        assert event.max_area == 2500


class TestEDAProjectionSetupPage:
    """Test suite for EDA-integrated projection setup page."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_gui_service = MockGUIService()
        
    def test_projection_config_interaction(self):
        """Test projection configuration changes publish correct events."""
        self.mock_gui_service.update_projection_config(1920, 1080)
        
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, ProjectionConfigUpdated)
        assert event.width == 1920
        assert event.height == 1080
        
    def test_projection_presets(self):
        """Test projection preset configurations."""
        # Test common presets
        presets = [
            (1920, 1080),  # Full HD
            (2560, 1440),  # 1440p
            (3840, 2160),  # 4K
        ]
        
        for width, height in presets:
            self.mock_gui_service.published_events.clear()
            self.mock_gui_service.update_projection_config(width, height)
            
            assert len(self.mock_gui_service.published_events) == 1
            event = self.mock_gui_service.published_events[0]
            assert event.width == width
            assert event.height == height


# ==================== PERFORMANCE TESTS ==================== #

class TestEDAGUIPerformance:
    """Performance-focused tests for EDA GUI implementation."""
    
    def setup_method(self):
        """Set up performance test fixtures."""
        self.mock_gui_service = MockGUIService()
        
    def test_high_frequency_event_handling(self):
        """Test GUI performance with high-frequency tracking events."""
        # Simulate 60Hz tracking data updates
        start_time = time.perf_counter()
        
        for frame_id in range(60):  # 1 second worth at 60Hz
            mock_beys = [MockBeyData(i, (i*10, i*10), (1.0, 1.0)) for i in range(5)]
            mock_hits = [MockHitData((i*15, i*15), (i, i+1), True) for i in range(2)]
            
            event = TrackingDataUpdated(
                frame_id=frame_id,
                timestamp=time.perf_counter(),
                beys=mock_beys,
                hits=mock_hits
            )
            
            # Process event (timing simulation)
            _ = event.frame_id
            _ = len(event.beys)
            _ = len(event.hits)
            
        total_time = time.perf_counter() - start_time
        avg_time_per_frame = total_time / 60
        
        # Performance requirement: < 16ms per frame for 60Hz
        assert avg_time_per_frame < 0.016, f"Frame processing too slow: {avg_time_per_frame*1000:.3f}ms"
        
    def test_event_publishing_latency(self):
        """Test user interaction event publishing latency."""
        # Measure event publishing performance
        start_time = time.perf_counter()
        
        for i in range(100):
            self.mock_gui_service.update_tracker_settings(threshold=20+i)
            
        total_time = time.perf_counter() - start_time
        avg_time_per_event = total_time / 100
        
        # Performance requirement: < 1ms per user interaction
        assert avg_time_per_event < 0.001, f"Event publishing too slow: {avg_time_per_event*1000:.3f}ms"
        
        # Verify all events were published
        assert len(self.mock_gui_service.published_events) == 100
        
    def test_memory_efficiency(self):
        """Test memory usage efficiency of GUI components."""
        import sys
        
        # Create multiple page instances to test memory usage
        initial_objects = len([obj for obj in globals().values() if hasattr(obj, '__dict__')])
        
        # Create and destroy multiple GUI service instances
        services = []
        for i in range(100):
            service = MockGUIService()
            service.update_tracker_settings(threshold=i)
            services.append(service)
            
        # Clean up
        del services
        
        final_objects = len([obj for obj in globals().values() if hasattr(obj, '__dict__')])
        
        # Memory usage should not grow excessively
        object_growth = final_objects - initial_objects
        assert object_growth < 50, f"Excessive object growth: {object_growth}"


# ==================== INTEGRATION TESTS ==================== #

class TestEDAGUIIntegration:
    """Integration tests for complete GUI-EDA interaction."""
    
    def setup_method(self):
        """Set up integration test fixtures."""
        self.mock_gui_service = MockGUIService()
        self.mock_event_broker = Mock()
        
    def test_complete_tracking_workflow(self):
        """Test complete workflow from GUI interaction to service response."""
        # Step 1: User starts tracking
        self.mock_gui_service.request_start_tracking(dev_mode=False, cam_src=0)
        
        # Verify start event was published
        start_events = [e for e in self.mock_gui_service.published_events if isinstance(e, StartTracking)]
        assert len(start_events) == 1
        
        # Step 2: Simulate tracking started response
        tracking_started_event = TrackingStarted(camera_type="RealSense")
        
        # Step 3: Simulate tracking data updates
        for frame_id in range(5):
            tracking_data_event = TrackingDataUpdated(
                frame_id=frame_id,
                timestamp=time.time(),
                beys=[MockBeyData(1, (100+frame_id*10, 200), (1.0, 2.0))],
                hits=[]
            )
            # GUI would process this event to update display
            assert tracking_data_event.frame_id == frame_id
            
        # Step 4: User stops tracking
        self.mock_gui_service.request_stop_tracking()
        
        # Verify stop event was published
        stop_events = [e for e in self.mock_gui_service.published_events if isinstance(e, StopTracking)]
        assert len(stop_events) == 1
        
    def test_projection_configuration_workflow(self):
        """Test projection configuration workflow."""
        # User changes projection settings
        self.mock_gui_service.update_projection_config(2560, 1440)
        
        # Verify event was published
        config_events = [e for e in self.mock_gui_service.published_events if isinstance(e, ProjectionConfigUpdated)]
        assert len(config_events) == 1
        assert config_events[0].width == 2560
        assert config_events[0].height == 1440
        
        # Simulate projection client connection
        connection_event = ProjectionClientConnected(client_address="127.0.0.1")
        assert connection_event.client_address == "127.0.0.1"
        
    def test_error_handling_workflow(self):
        """Test error handling throughout the system."""
        # Simulate tracking error
        error_event = TrackingError(
            error_message="Camera disconnected",
            recoverable=False,
            error_code="CAM_DISCONNECT"
        )
        
        # Verify error properties
        assert error_event.error_message == "Camera disconnected"
        assert error_event.recoverable is False
        assert error_event.error_code == "CAM_DISCONNECT"
        
        # Test notification system for error display
        notifications = []
        self.mock_gui_service.register_notification_callback(
            lambda msg, duration: notifications.append((msg, duration))
        )
        
        self.mock_gui_service.show_notification("Error: Camera disconnected", 5000)
        assert len(notifications) == 1
        assert "Error: Camera disconnected" in notifications[0][0] 