"""
Integration tests for HMI-01: Tracker Setup View.

This test suite verifies that the Tracker Setup View properly conforms to 
trackersetup1.PNG reference design and integrates correctly with the 
Event-Driven Architecture.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QSlider, QPushButton
from PySide6.QtTest import QTest

from core.event_broker import EventBroker
from core.events import (
    TrackingDataUpdated, TrackingStarted, TrackingStopped, TrackingError,
    ChangeTrackerSettings, StartTracking, StopTracking, BeyData, HitData
)
from services.gui_service import GUIService
from gui.eda_main_gui import PixelPerfectTrackerSetupPage


class TestHMI01Integration:
    """Test suite for HMI-01 implementation."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.app = QApplication.instance() or QApplication([])
        self.event_broker = EventBroker(max_workers=2, max_queue_size=100)
        self.gui_service = GUIService(self.event_broker)
        self.gui_service.start()
        
        # Create the tracker setup page
        self.tracker_page = PixelPerfectTrackerSetupPage(self.gui_service)
        
        # Mock event tracking
        self.published_events = []
        self.original_publish = self.event_broker.publish
        self.event_broker.publish = lambda event: self.published_events.append(event)
    
    def teardown_method(self):
        """Clean up after each test."""
        self.event_broker.publish = self.original_publish
        self.gui_service.stop()
        self.event_broker.shutdown()
        self.tracker_page.deleteLater()
    
    def test_reference_layout_conformance(self):
        """Test layout matches trackersetup1.PNG reference."""
        # Verify main layout structure
        assert self.tracker_page.layout() is not None
        
        # Test required UI sections exist
        camera_preview = self.tracker_page.findChild(QWidget, "camera_preview_area")
        assert camera_preview is not None, "Camera preview area must exist"
        
        detection_panel = self.tracker_page.findChild(QWidget, "detection_controls")
        assert detection_panel is not None, "Detection controls panel must exist"
        
        camera_panel = self.tracker_page.findChild(QWidget, "camera_controls")
        assert camera_panel is not None, "Camera controls panel must exist"
        
        status_panel = self.tracker_page.findChild(QWidget, "performance_status")
        assert status_panel is not None, "Performance status panel must exist"
    
    def test_detection_controls_functionality(self):
        """Test detection control sliders publish correct events."""
        # Find threshold slider
        threshold_slider = self.tracker_page.findChild(QSlider, "threshold_slider")
        assert threshold_slider is not None
        
        # Change threshold value
        threshold_slider.setValue(30)
        QTest.qWait(50)  # Allow signal processing
        
        # Verify ChangeTrackerSettings event was published
        tracking_events = [e for e in self.published_events if isinstance(e, ChangeTrackerSettings)]
        assert len(tracking_events) > 0, "Threshold change should publish ChangeTrackerSettings event"
        
        last_event = tracking_events[-1]
        assert last_event.threshold == 30
    
    def test_camera_controls_functionality(self):
        """Test camera control buttons publish correct events."""
        # Find start tracking button
        start_button = self.tracker_page.findChild(QPushButton, "start_tracking_btn")
        assert start_button is not None
        
        # Click start button
        QTest.mouseClick(start_button, Qt.LeftButton)
        QTest.qWait(50)
        
        # Verify StartTracking event was published
        start_events = [e for e in self.published_events if isinstance(e, StartTracking)]
        assert len(start_events) > 0, "Start button should publish StartTracking event"
    
    def test_tracking_data_updates_ui(self):
        """Test UI updates correctly when receiving TrackingDataUpdated events."""
        # Create mock tracking data
        mock_beys = [
            BeyData(id=1, pos=(100, 200), velocity=(1.0, 2.0), raw_velocity=(1.0, 2.0), 
                    acceleration=(0.1, 0.2), shape=(20, 20), frame=123),
            BeyData(id=2, pos=(300, 400), velocity=(0.5, -1.0), raw_velocity=(0.5, -1.0),
                    acceleration=(0.0, 0.1), shape=(22, 22), frame=123)
        ]
        mock_hits = [
            HitData(pos=(150, 250), shape=(30, 30), bey_ids=(1, 2), is_new_hit=True)
        ]
        
        # Publish tracking data event
        tracking_event = TrackingDataUpdated(
            frame_id=123,
            timestamp=time.time(),
            beys=mock_beys,
            hits=mock_hits
        )
        
        # Simulate event processing
        self.tracker_page.handle_tracking_data_updated(tracking_event)
        QTest.qWait(50)
        
        # Verify UI updated with tracking info
        frame_counter = self.tracker_page.findChild(QLabel, "frame_counter_label")
        assert frame_counter is not None
        assert "123" in frame_counter.text()
    
    def test_tracking_started_event_handling(self):
        """Test UI responds correctly to TrackingStarted events."""
        # Create tracking started event
        started_event = TrackingStarted(
            camera_type="RealSense D435",
            resolution=(640, 360)
        )
        
        # Process event
        self.tracker_page.handle_tracking_started(started_event)
        QTest.qWait(50)
        
        # Verify UI shows tracking active state
        status_label = self.tracker_page.findChild(QLabel, "tracking_status_label")
        assert status_label is not None
        assert "Active" in status_label.text() or "Running" in status_label.text()
        
        # Verify start button is disabled during tracking
        start_button = self.tracker_page.findChild(QPushButton, "start_tracking_btn")
        assert start_button is not None
        assert not start_button.isEnabled()
    
    def test_tracking_error_handling(self):
        """Test UI handles tracking errors gracefully."""
        # Create tracking error event
        error_event = TrackingError(
            error_message="Camera connection failed",
            error_type="hardware_error",
            recoverable=True
        )
        
        # Process error event
        self.tracker_page.handle_tracking_error(error_event)
        QTest.qWait(50)
        
        # Verify error is displayed to user
        error_label = self.tracker_page.findChild(QLabel, "error_display_label")
        assert error_label is not None
        assert "Camera connection failed" in error_label.text()
    
    def test_performance_metrics_display(self):
        """Test performance metrics are displayed correctly."""
        # Simulate performance data
        mock_performance = {
            'fps': 30.5,
            'processing_time_ms': 15.2,
            'frame_count': 1000,
            'detected_objects': 2
        }
        
        # Update performance display
        self.tracker_page.update_performance_metrics(mock_performance)
        QTest.qWait(50)
        
        # Verify metrics are shown
        fps_label = self.tracker_page.findChild(QLabel, "fps_label")
        assert fps_label is not None
        assert "30.5" in fps_label.text()
        
        processing_label = self.tracker_page.findChild(QLabel, "processing_time_label")
        assert processing_label is not None
        assert "15.2" in processing_label.text()
    
    def test_multiple_slider_interactions(self):
        """Test multiple slider interactions publish correct events."""
        # Find all detection sliders
        threshold_slider = self.tracker_page.findChild(QSlider, "threshold_slider")
        min_area_slider = self.tracker_page.findChild(QSlider, "min_area_slider")
        max_area_slider = self.tracker_page.findChild(QSlider, "max_area_slider")
        
        assert all([threshold_slider, min_area_slider, max_area_slider])
        
        # Change multiple values
        threshold_slider.setValue(25)
        min_area_slider.setValue(100)
        max_area_slider.setValue(3000)
        QTest.qWait(100)
        
        # Verify multiple events were published
        tracking_events = [e for e in self.published_events if isinstance(e, ChangeTrackerSettings)]
        assert len(tracking_events) >= 3, "Should have events for each slider change"
    
    def test_real_time_tracking_simulation(self):
        """Test real-time tracking data updates don't impact performance."""
        start_time = time.time()
        frame_count = 50
        
        # Simulate rapid tracking updates
        for frame_id in range(frame_count):
            mock_beys = [BeyData(id=1, pos=(frame_id, frame_id*2), velocity=(1.0, 2.0),
                                raw_velocity=(1.0, 2.0), acceleration=(0.1, 0.2), 
                                shape=(20, 20), frame=frame_id)]
            tracking_event = TrackingDataUpdated(
                frame_id=frame_id,
                timestamp=time.time(),
                beys=mock_beys,
                hits=[]
            )
            
            self.tracker_page.handle_tracking_data_updated(tracking_event)
            QTest.qWait(10)  # 10ms per frame = ~100 FPS simulation
        
        elapsed_time = time.time() - start_time
        
        # Verify processing kept up with real-time requirements
        assert elapsed_time < 2.0, f"Processing {frame_count} frames took too long: {elapsed_time}s"
        
        # Verify final frame data is displayed
        frame_counter = self.tracker_page.findChild(QLabel, "frame_counter_label")
        assert frame_counter is not None
        assert str(frame_count - 1) in frame_counter.text()
    
    def test_ui_state_consistency(self):
        """Test UI maintains consistent state during rapid changes."""
        # Start tracking
        start_event = TrackingStarted(camera_type="Mock", resolution=(640, 360))
        self.tracker_page.handle_tracking_started(start_event)
        QTest.qWait(50)
        
        # Send some tracking data
        for i in range(10):
            tracking_event = TrackingDataUpdated(
                frame_id=i,
                timestamp=time.time(),
                beys=[BeyData(id=1, pos=(i*10, i*20), velocity=(1.0, 2.0),
                             raw_velocity=(1.0, 2.0), acceleration=(0.1, 0.2),
                             shape=(20, 20), frame=i)],
                hits=[]
            )
            self.tracker_page.handle_tracking_data_updated(tracking_event)
            QTest.qWait(5)
        
        # Stop tracking
        stop_event = TrackingStopped(reason="user_request")
        self.tracker_page.handle_tracking_stopped(stop_event)
        QTest.qWait(50)
        
        # Verify UI returned to stopped state
        start_button = self.tracker_page.findChild(QPushButton, "start_tracking_btn")
        assert start_button is not None
        assert start_button.isEnabled(), "Start button should be enabled after stopping"
        
        status_label = self.tracker_page.findChild(QLabel, "tracking_status_label")
        assert status_label is not None
        assert "Stopped" in status_label.text() or "Ready" in status_label.text()
    
    def test_widget_styling_conformance(self):
        """Test widgets have correct styling matching reference design."""
        # Verify main styling properties
        self.tracker_page.show()
        QTest.qWait(100)
        
        # Check background styling
        bg_color = self.tracker_page.palette().color(self.tracker_page.backgroundRole())
        assert bg_color.name() in ["#1e1e1e", "#000000", "#2b2b2b"], "Background should be dark theme"
        
        # Check that critical labels exist and have appropriate fonts
        title_label = self.tracker_page.findChild(QLabel, "page_title_label")
        if title_label:
            font = title_label.font()
            assert font.pointSize() >= 16, "Title should have large font size"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 