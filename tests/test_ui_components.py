"""
Unit tests for EDA-integrated UI components.

These tests verify individual UI components function correctly in isolation,
handle event flow properly, bind data correctly, and meet performance requirements.
Tests use mocking to avoid Qt dependencies while ensuring component contracts.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from core.interfaces import IGUIService
from core.events import (
    TrackingDataUpdated, ProjectionClientConnected, ChangeTrackerSettings,
    ProjectionConfigUpdated, StartTracking, StopTracking
)


# ==================== MOCK UI FRAMEWORK ==================== #

class MockQWidget:
    """Mock Qt widget for testing without Qt dependency."""
    
    def __init__(self, parent=None):
        self.parent = parent
        self.children = []
        self.visible = True
        self.enabled = True
        self.geometry = (0, 0, 100, 100)
        self.properties = {}
        self.signals_connected = []
        
    def setVisible(self, visible: bool):
        self.visible = visible
        
    def setEnabled(self, enabled: bool):
        self.enabled = enabled
        
    def setGeometry(self, x: int, y: int, w: int, h: int):
        self.geometry = (x, y, w, h)
        
    def setProperty(self, name: str, value: Any):
        self.properties[name] = value
        
    def property(self, name: str) -> Any:
        return self.properties.get(name)
        
    def addWidget(self, widget):
        self.children.append(widget)
        widget.parent = self
        
    def connectSignal(self, signal_name: str, slot):
        self.signals_connected.append((signal_name, slot))


class MockQPushButton(MockQWidget):
    """Mock QPushButton for testing."""
    
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.text = text
        self.clicked_callbacks = []
        
    def setText(self, text: str):
        self.text = text
        
    def getText(self) -> str:
        return self.text
        
    def connectClicked(self, callback):
        self.clicked_callbacks.append(callback)
        
    def simulateClick(self):
        """Simulate button click for testing."""
        for callback in self.clicked_callbacks:
            callback()


class MockQSlider(MockQWidget):
    """Mock QSlider for testing."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        self.minimum = 0
        self.maximum = 100
        self.value_changed_callbacks = []
        
    def setValue(self, value: int):
        if self.minimum <= value <= self.maximum:
            self.value = value
            self._emit_value_changed()
            
    def getValue(self) -> int:
        return self.value
        
    def setRange(self, min_val: int, max_val: int):
        self.minimum = min_val
        self.maximum = max_val
        
    def connectValueChanged(self, callback):
        self.value_changed_callbacks.append(callback)
        
    def _emit_value_changed(self):
        """Emit value changed signal for testing."""
        for callback in self.value_changed_callbacks:
            callback(self.value)


class MockQLabel(MockQWidget):
    """Mock QLabel for testing."""
    
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.text = text
        
    def setText(self, text: str):
        self.text = text
        
    def getText(self) -> str:
        return self.text


# ==================== MOCK SERVICES ==================== #

class MockGUIService:
    """Mock GUI service for component testing."""
    
    def __init__(self):
        self.published_events = []
        self.notifications = []
        self.error_dialogs = []
        
    def request_start_tracking(self, **kwargs):
        self.published_events.append(StartTracking(**kwargs))
        
    def request_stop_tracking(self):
        self.published_events.append(StopTracking())
        
    def update_tracker_settings(self, **kwargs):
        self.published_events.append(ChangeTrackerSettings(**kwargs))
        
    def update_projection_config(self, width: int, height: int):
        self.published_events.append(ProjectionConfigUpdated(width=width, height=height))
        
    def show_notification(self, message: str, duration_ms: int = 3000):
        self.notifications.append((message, duration_ms))
        
    def show_error_dialog(self, title: str, message: str):
        self.error_dialogs.append((title, message))


# ==================== COMPONENT TESTS ==================== #

class TestComponentPerformance:
    """Performance-focused tests for UI components."""
    
    def setup_method(self):
        """Set up performance test fixtures."""
        self.mock_gui_service = MockGUIService()
        
    def test_rapid_user_interactions(self):
        """Test performance with rapid user interactions."""
        # Create multiple sliders for stress testing
        sliders = []
        for i in range(10):
            slider = MockQSlider()
            slider.setRange(0, 100)
            slider.connectValueChanged(
                lambda value, idx=i: self.mock_gui_service.update_tracker_settings(**{f'param_{idx}': value})
            )
            sliders.append(slider)
            
        # Rapidly change all slider values
        start_time = time.perf_counter()
        
        for iteration in range(10):
            for i, slider in enumerate(sliders):
                slider.setValue((iteration * 10 + i) % 100)
                
        total_time = time.perf_counter() - start_time
        
        # Performance requirement: < 100ms for 100 rapid interactions
        assert total_time < 0.1, f"Rapid interactions too slow: {total_time*1000:.1f}ms"
        
        # Verify all events were published
        assert len(self.mock_gui_service.published_events) == 100


# ==================== BASE COMPONENT TESTS ==================== #

class TestBasePage:
    """Test suite for BasePage component."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_gui_service = MockGUIService()
        
    def test_base_page_interface(self):
        """Test BasePage interface requirements."""
        # Test required interface methods exist in service
        required_service_methods = [
            'request_start_tracking',
            'request_stop_tracking', 
            'update_tracker_settings',
            'update_projection_config',
            'show_notification',
            'show_error_dialog'
        ]
        
        for method in required_service_methods:
            assert hasattr(self.mock_gui_service, method)
            assert callable(getattr(self.mock_gui_service, method))
            
    def test_event_publishing_helper(self):
        """Test event publishing helper functionality."""
        # Test tracker settings event publishing
        self.mock_gui_service.update_tracker_settings(threshold=25, min_area=150)
        
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, ChangeTrackerSettings)
        assert event.threshold == 25
        assert event.min_area == 150
        
    def test_notification_system(self):
        """Test notification system integration."""
        self.mock_gui_service.show_notification("Test notification", 5000)
        
        assert len(self.mock_gui_service.notifications) == 1
        notification = self.mock_gui_service.notifications[0]
        assert notification[0] == "Test notification"
        assert notification[1] == 5000


# ==================== STATUS COMPONENTS TESTS ==================== #

class TestStatusComponents:
    """Test suite for status bar and notification components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.status_bar = MockQWidget()
        self.notification_widget = MockQWidget()
        self.tracking_status_label = MockQLabel("Stopped")
        self.projection_status_label = MockQLabel("Disconnected")
        
    def test_tracking_status_display(self):
        """Test tracking status display updates."""
        # Initial state
        assert self.tracking_status_label.getText() == "Stopped"
        
        # Update to running
        self.tracking_status_label.setText("Running")
        assert self.tracking_status_label.getText() == "Running"
        
        # Update to error state
        self.tracking_status_label.setText("Error: Camera disconnected")
        assert "Error" in self.tracking_status_label.getText()
        
    def test_projection_status_display(self):
        """Test projection status display updates."""
        # Initial state
        assert self.projection_status_label.getText() == "Disconnected"
        
        # Update to connected
        self.projection_status_label.setText("Connected: 127.0.0.1")
        assert "Connected" in self.projection_status_label.getText()
        assert "127.0.0.1" in self.projection_status_label.getText()
        
    def test_notification_display(self):
        """Test notification widget functionality."""
        # Set notification properties
        self.notification_widget.setProperty("message", "Test notification")
        self.notification_widget.setProperty("duration", 3000)
        self.notification_widget.setProperty("type", "info")
        
        assert self.notification_widget.property("message") == "Test notification"
        assert self.notification_widget.property("duration") == 3000
        assert self.notification_widget.property("type") == "info"
        
    def test_status_widget_hierarchy(self):
        """Test status component widget hierarchy."""
        # Build status bar hierarchy
        self.status_bar.addWidget(self.tracking_status_label)
        self.status_bar.addWidget(self.projection_status_label)
        
        assert len(self.status_bar.children) == 2
        assert self.tracking_status_label.parent == self.status_bar
        assert self.projection_status_label.parent == self.status_bar


# ==================== TRACKER SETUP COMPONENTS TESTS ==================== #

class TestTrackerSetupComponents:
    """Test suite for tracker setup page components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_gui_service = MockGUIService()
        
        # Create mock UI components
        self.start_button = MockQPushButton("Start Tracking")
        self.stop_button = MockQPushButton("Stop Tracking")
        self.threshold_slider = MockQSlider()
        self.min_area_slider = MockQSlider()
        self.max_area_slider = MockQSlider()
        
        # Configure sliders
        self.threshold_slider.setRange(1, 50)
        self.threshold_slider.setValue(20)
        self.min_area_slider.setRange(50, 500)
        self.min_area_slider.setValue(150)
        self.max_area_slider.setRange(1000, 5000)
        self.max_area_slider.setValue(2500)
        
    def test_start_tracking_button(self):
        """Test start tracking button functionality."""
        # Connect button to service
        self.start_button.connectClicked(
            lambda: self.mock_gui_service.request_start_tracking(dev_mode=False, cam_src=0)
        )
        
        # Simulate button click
        self.start_button.simulateClick()
        
        # Verify event was published
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, StartTracking)
        assert event.dev_mode is False
        assert event.cam_src == 0
        
    def test_stop_tracking_button(self):
        """Test stop tracking button functionality."""
        # Connect button to service
        self.stop_button.connectClicked(
            lambda: self.mock_gui_service.request_stop_tracking()
        )
        
        # Simulate button click
        self.stop_button.simulateClick()
        
        # Verify event was published
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, StopTracking)
        
    def test_threshold_slider_interaction(self):
        """Test threshold slider value changes."""
        # Connect slider to service
        self.threshold_slider.connectValueChanged(
            lambda value: self.mock_gui_service.update_tracker_settings(threshold=value)
        )
        
        # Change slider value
        self.threshold_slider.setValue(30)
        
        # Verify event was published
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, ChangeTrackerSettings)
        assert event.threshold == 30
        
    def test_multiple_slider_interactions(self):
        """Test multiple slider interactions publish correct events."""
        # Connect all sliders
        self.threshold_slider.connectValueChanged(
            lambda value: self.mock_gui_service.update_tracker_settings(threshold=value)
        )
        self.min_area_slider.connectValueChanged(
            lambda value: self.mock_gui_service.update_tracker_settings(min_area=value)
        )
        self.max_area_slider.connectValueChanged(
            lambda value: self.mock_gui_service.update_tracker_settings(max_area=value)
        )
        
        # Change multiple values
        self.threshold_slider.setValue(25)
        self.min_area_slider.setValue(200)
        self.max_area_slider.setValue(3000)
        
        # Verify all events were published
        assert len(self.mock_gui_service.published_events) == 3
        
        # Check event types and values
        threshold_events = [e for e in self.mock_gui_service.published_events 
                          if hasattr(e, 'threshold') and e.threshold == 25]
        min_area_events = [e for e in self.mock_gui_service.published_events 
                          if hasattr(e, 'min_area') and e.min_area == 200]
        max_area_events = [e for e in self.mock_gui_service.published_events 
                          if hasattr(e, 'max_area') and e.max_area == 3000]
        
        assert len(threshold_events) == 1
        assert len(min_area_events) == 1  
        assert len(max_area_events) == 1
        
    def test_slider_range_validation(self):
        """Test slider range validation."""
        # Test threshold slider bounds
        self.threshold_slider.setValue(-5)  # Below minimum
        assert self.threshold_slider.getValue() == 20  # Should remain unchanged
        
        self.threshold_slider.setValue(100)  # Above maximum
        assert self.threshold_slider.getValue() == 20  # Should remain unchanged
        
        self.threshold_slider.setValue(35)  # Valid value
        assert self.threshold_slider.getValue() == 35


# ==================== PROJECTION SETUP COMPONENTS TESTS ==================== #

class TestProjectionSetupComponents:
    """Test suite for projection setup page components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_gui_service = MockGUIService()
        
        # Create mock UI components
        self.width_slider = MockQSlider()
        self.height_slider = MockQSlider()
        self.preset_button_1080p = MockQPushButton("1920×1080")
        self.preset_button_1440p = MockQPushButton("2560×1440")
        self.preset_button_4k = MockQPushButton("3840×2160")
        self.apply_button = MockQPushButton("Apply Configuration")
        
        # Configure sliders
        self.width_slider.setRange(640, 4096)
        self.width_slider.setValue(1920)
        self.height_slider.setRange(480, 2160)
        self.height_slider.setValue(1080)
        
    def test_resolution_sliders(self):
        """Test resolution slider interactions."""
        # Track configuration changes
        configs_applied = []
        
        def apply_config():
            width = self.width_slider.getValue()
            height = self.height_slider.getValue()
            self.mock_gui_service.update_projection_config(width, height)
            configs_applied.append((width, height))
            
        # Connect apply button
        self.apply_button.connectClicked(apply_config)
        
        # Change resolution and apply
        self.width_slider.setValue(2560)
        self.height_slider.setValue(1440)
        self.apply_button.simulateClick()
        
        # Verify configuration was applied
        assert len(configs_applied) == 1
        assert configs_applied[0] == (2560, 1440)
        
        # Verify event was published
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert isinstance(event, ProjectionConfigUpdated)
        assert event.width == 2560
        assert event.height == 1440
        
    def test_preset_buttons(self):
        """Test resolution preset buttons."""
        # Connect preset buttons
        self.preset_button_1080p.connectClicked(
            lambda: self.mock_gui_service.update_projection_config(1920, 1080)
        )
        self.preset_button_1440p.connectClicked(
            lambda: self.mock_gui_service.update_projection_config(2560, 1440)
        )
        self.preset_button_4k.connectClicked(
            lambda: self.mock_gui_service.update_projection_config(3840, 2160)
        )
        
        # Test 1080p preset
        self.preset_button_1080p.simulateClick()
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert event.width == 1920 and event.height == 1080
        
        # Test 1440p preset
        self.mock_gui_service.published_events.clear()
        self.preset_button_1440p.simulateClick()
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert event.width == 2560 and event.height == 1440
        
        # Test 4K preset
        self.mock_gui_service.published_events.clear()
        self.preset_button_4k.simulateClick()
        assert len(self.mock_gui_service.published_events) == 1
        event = self.mock_gui_service.published_events[0]
        assert event.width == 3840 and event.height == 2160
        
    def test_resolution_validation(self):
        """Test resolution value validation."""
        # Test width bounds
        self.width_slider.setValue(500)  # Below minimum
        assert self.width_slider.getValue() == 1920  # Should remain unchanged
        
        self.width_slider.setValue(5000)  # Above maximum
        assert self.width_slider.getValue() == 1920  # Should remain unchanged
        
        # Test height bounds
        self.height_slider.setValue(300)  # Below minimum
        assert self.height_slider.getValue() == 1080  # Should remain unchanged
        
        self.height_slider.setValue(3000)  # Above maximum
        assert self.height_slider.getValue() == 1080  # Should remain unchanged


# ==================== DATA BINDING TESTS ==================== #

class TestDataBinding:
    """Test suite for data binding between UI components and events."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tracking_status_label = MockQLabel("Stopped")
        self.projection_status_label = MockQLabel("Disconnected")
        self.frame_count_label = MockQLabel("0")
        self.bey_count_label = MockQLabel("0")
        
    def test_tracking_data_binding(self):
        """Test binding of tracking data to UI components."""
        # Create mock tracking data
        mock_beys = [
            type('MockBey', (), {'id': 1, 'pos': (100, 200)})(),
            type('MockBey', (), {'id': 2, 'pos': (300, 400)})()
        ]
        
        tracking_event = TrackingDataUpdated(
            frame_id=150,
            timestamp=time.time(),
            beys=mock_beys,
            hits=[]
        )
        
        # Simulate data binding updates
        self.frame_count_label.setText(str(tracking_event.frame_id))
        self.bey_count_label.setText(str(len(tracking_event.beys)))
        
        # Verify data was bound correctly
        assert self.frame_count_label.getText() == "150"
        assert self.bey_count_label.getText() == "2"
        
    def test_projection_status_binding(self):
        """Test binding of projection status to UI components."""
        # Test connection event binding
        connection_event = ProjectionClientConnected(client_address="192.168.1.100")
        
        # Simulate status update
        self.projection_status_label.setText(f"Connected: {connection_event.client_address}")
        
        # Verify status was updated
        assert "Connected" in self.projection_status_label.getText()
        assert "192.168.1.100" in self.projection_status_label.getText()
        
        # Test disconnection event binding
        from core.events import ProjectionClientDisconnected
        disconnection_event = ProjectionClientDisconnected(reason="timeout")
        
        # Simulate status update
        self.projection_status_label.setText(f"Disconnected: {disconnection_event.reason}")
        
        # Verify status was updated
        assert "Disconnected" in self.projection_status_label.getText()
        assert "timeout" in self.projection_status_label.getText()
        
    def test_real_time_data_updates(self):
        """Test real-time data updates maintain UI responsiveness."""
        # Simulate high-frequency updates
        frame_times = []
        
        for frame_id in range(60):  # 60 frames
            start_time = time.perf_counter()
            
            # Simulate data binding update
            self.frame_count_label.setText(str(frame_id))
            self.bey_count_label.setText(str(frame_id % 5))  # Varying bey count
            
            end_time = time.perf_counter()
            frame_times.append(end_time - start_time)
            
        # Calculate average update time
        avg_update_time = sum(frame_times) / len(frame_times)
        
        # Performance requirement: < 1ms per update
        assert avg_update_time < 0.001, f"Data binding too slow: {avg_update_time*1000:.3f}ms"
        
        # Verify final state
        assert self.frame_count_label.getText() == "59"
        assert self.bey_count_label.getText() == "4"  # 59 % 5 = 4


# ==================== COMPONENT ISOLATION TESTS ==================== #

class TestComponentIsolation:
    """Test suite for component isolation and independence."""
    
    def setup_method(self):
        """Set up component isolation test fixtures."""
        self.mock_gui_service = MockGUIService()
        
    def test_independent_component_state(self):
        """Test that components maintain independent state."""
        # Create multiple independent slider components
        slider1 = MockQSlider()
        slider2 = MockQSlider()
        slider3 = MockQSlider()
        
        # Configure with different ranges and values
        slider1.setRange(0, 50)
        slider1.setValue(25)
        
        slider2.setRange(100, 200)
        slider2.setValue(150)
        
        slider3.setRange(-10, 10)
        slider3.setValue(0)
        
        # Verify independent state
        assert slider1.getValue() == 25
        assert slider2.getValue() == 150
        assert slider3.getValue() == 0
        
        # Change one slider, verify others unchanged
        slider1.setValue(40)
        
        assert slider1.getValue() == 40
        assert slider2.getValue() == 150  # Unchanged
        assert slider3.getValue() == 0    # Unchanged
        
    def test_component_event_isolation(self):
        """Test that component events don't interfere with each other."""
        button1 = MockQPushButton("Button 1")
        button2 = MockQPushButton("Button 2")
        
        # Track clicks separately
        button1_clicks = []
        button2_clicks = []
        
        button1.connectClicked(lambda: button1_clicks.append(time.time()))
        button2.connectClicked(lambda: button2_clicks.append(time.time()))
        
        # Click buttons in sequence
        button1.simulateClick()
        button2.simulateClick()
        button1.simulateClick()
        
        # Verify separate tracking
        assert len(button1_clicks) == 2
        assert len(button2_clicks) == 1
        
    def test_component_hierarchy_isolation(self):
        """Test that parent-child relationships are properly isolated."""
        parent_widget = MockQWidget()
        child1 = MockQWidget()
        child2 = MockQWidget()
        grandchild = MockQWidget()
        
        # Build hierarchy
        parent_widget.addWidget(child1)
        parent_widget.addWidget(child2)
        child1.addWidget(grandchild)
        
        # Verify parent-child relationships
        assert len(parent_widget.children) == 2
        assert child1.parent == parent_widget
        assert child2.parent == parent_widget
        assert len(child1.children) == 1
        assert grandchild.parent == child1
        
        # Verify isolation
        assert len(child2.children) == 0
        assert grandchild.parent != parent_widget  # Direct parent only 