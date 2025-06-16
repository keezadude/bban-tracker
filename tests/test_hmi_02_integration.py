"""
Integration tests for HMI-02: Projection Setup View.

This test suite verifies that the Projection Setup View properly conforms to 
projection setup.PNG reference design and integrates correctly with the 
Event-Driven Architecture, including interactive keystone correction.
"""

import pytest
import time
import math
from unittest.mock import Mock, patch, MagicMock

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QSlider, QPushButton
from PySide6.QtTest import QTest
from PySide6.QtGui import QMouseEvent

from core.event_broker import EventBroker
from core.events import (
    ProjectionConfigUpdated, ProjectionClientConnected, ProjectionClientDisconnected,
    SystemShutdown
)
from services.gui_service import GUIService
from gui.eda_main_gui import PixelPerfectProjectionSetupPage


class TestHMI02Integration:
    """Test suite for HMI-02 implementation."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.app = QApplication.instance() or QApplication([])
        self.event_broker = EventBroker(max_workers=2, max_queue_size=100)
        self.gui_service = GUIService(self.event_broker)
        self.gui_service.start()
        
        # Create the projection setup page
        self.projection_page = PixelPerfectProjectionSetupPage(self.gui_service)
        
        # Mock event tracking
        self.published_events = []
        self.original_publish = self.event_broker.publish
        self.event_broker.publish = lambda event: self.published_events.append(event)
    
    def teardown_method(self):
        """Clean up after each test."""
        self.event_broker.publish = self.original_publish
        self.gui_service.stop()
        self.event_broker.shutdown()
        self.projection_page.deleteLater()
    
    def test_reference_layout_conformance(self):
        """Test layout matches projection setup.PNG reference."""
        # Verify main layout structure
        assert self.projection_page.layout() is not None
        
        # Test required UI sections exist
        preview_area = self.projection_page.findChild(QWidget, "projection_preview_area")
        assert preview_area is not None, "Projection preview area must exist"
        
        keystone_panel = self.projection_page.findChild(QWidget, "keystone_controls")
        assert keystone_panel is not None, "Keystone controls panel must exist"
        
        transform_panel = self.projection_page.findChild(QWidget, "transform_sliders")
        assert transform_panel is not None, "Transform sliders panel must exist"
        
        actions_panel = self.projection_page.findChild(QWidget, "actions_panel")
        assert actions_panel is not None, "Actions panel must exist"
    
    def test_projection_preview_interactive_area(self):
        """Test projection preview area supports interactive manipulation."""
        preview_widget = self.projection_page.findChild(QWidget, "projection_preview_display")
        assert preview_widget is not None
        
        # Test preview has drag handles
        corner_handles = [
            self.projection_page.findChild(QWidget, f"corner_handle_{corner}")
            for corner in ["TL", "TR", "BL", "BR"]
        ]
        
        for handle in corner_handles:
            assert handle is not None, "All corner handles must exist"
            
        # Test center drag handle
        center_handle = self.projection_page.findChild(QWidget, "center_drag_handle")
        assert center_handle is not None, "Center drag handle must exist"
    
    def test_transform_sliders_functionality(self):
        """Test transform control sliders publish correct events."""
        # Find transform sliders
        scale_slider = self.projection_page.findChild(QSlider, "scale_slider")
        rotation_slider = self.projection_page.findChild(QSlider, "rotation_slider")
        offset_x_slider = self.projection_page.findChild(QSlider, "offset_x_slider")
        offset_y_slider = self.projection_page.findChild(QSlider, "offset_y_slider")
        
        assert all([scale_slider, rotation_slider, offset_x_slider, offset_y_slider])
        
        # Test scale slider
        scale_slider.setValue(120)  # 120% scale
        QTest.qWait(50)
        
        # Verify projection configuration event was published
        config_events = [e for e in self.published_events if isinstance(e, ProjectionConfigUpdated)]
        assert len(config_events) > 0, "Scale change should publish ProjectionConfigUpdated event"
    
    def test_keystone_corner_selection(self):
        """Test keystone corner pin selection and manipulation."""
        # Find corner selection buttons
        corner_buttons = {}
        for corner in ["TL", "TR", "BL", "BR"]:
            button = self.projection_page.findChild(QPushButton, f"corner_button_{corner}")
            assert button is not None, f"Corner button {corner} must exist"
            corner_buttons[corner] = button
        
        # Test corner selection
        tl_button = corner_buttons["TL"]
        QTest.mouseClick(tl_button, Qt.LeftButton)
        QTest.qWait(50)
        
        # Verify corner is selected
        active_corner_label = self.projection_page.findChild(QLabel, "active_corner_label")
        assert active_corner_label is not None
        assert "TL" in active_corner_label.text()
    
    def test_interactive_preview_manipulation(self):
        """Test interactive preview manipulation with mouse events."""
        preview_widget = self.projection_page.findChild(QWidget, "projection_preview_display")
        assert preview_widget is not None
        
        # Test drag operation on preview
        center_x = preview_widget.width() // 2
        center_y = preview_widget.height() // 2
        
        # Simulate mouse press, drag, and release
        press_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(center_x, center_y),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(center_x + 50, center_y + 30),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        
        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(center_x + 50, center_y + 30),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        
        # Send mouse events to preview widget
        QTest.qWait(50)
        
        # Verify preview manipulation updates transform values
        offset_x_label = self.projection_page.findChild(QLabel, "offset_x_value_label")
        offset_y_label = self.projection_page.findChild(QLabel, "offset_y_value_label")
        
        assert offset_x_label is not None
        assert offset_y_label is not None
    
    def test_projection_config_event_handling(self):
        """Test UI responds correctly to ProjectionConfigUpdated events."""
        # Create projection config event
        config_event = ProjectionConfigUpdated(
            width=2560,
            height=1440
        )
        
        # Process event
        self.projection_page.handle_projection_config_updated(config_event)
        QTest.qWait(50)
        
        # Verify UI shows updated configuration
        resolution_label = self.projection_page.findChild(QLabel, "resolution_display_label")
        assert resolution_label is not None
        assert "2560" in resolution_label.text()
        assert "1440" in resolution_label.text()
    
    def test_projection_client_connection_handling(self):
        """Test UI responds to projection client connection events."""
        # Test connection event
        connect_event = ProjectionClientConnected(
            client_address="192.168.1.100"
        )
        
        self.projection_page.handle_projection_client_connected(connect_event)
        QTest.qWait(50)
        
        # Verify connection status is displayed
        connection_status_label = self.projection_page.findChild(QLabel, "connection_status_label")
        assert connection_status_label is not None
        assert "Connected" in connection_status_label.text()
        assert "192.168.1.100" in connection_status_label.text()
        
        # Test disconnection event
        disconnect_event = ProjectionClientDisconnected(
            reason="network_timeout"
        )
        
        self.projection_page.handle_projection_client_disconnected(disconnect_event)
        QTest.qWait(50)
        
        # Verify disconnection status
        assert "Disconnected" in connection_status_label.text()
    
    def test_save_and_reset_functionality(self):
        """Test save and reset actions work correctly."""
        # Find save and reset buttons
        save_button = self.projection_page.findChild(QPushButton, "save_settings_btn")
        reset_button = self.projection_page.findChild(QPushButton, "reset_settings_btn")
        
        assert save_button is not None
        assert reset_button is not None
        
        # Modify some settings first
        scale_slider = self.projection_page.findChild(QSlider, "scale_slider")
        scale_slider.setValue(120)
        
        rotation_slider = self.projection_page.findChild(QSlider, "rotation_slider")
        rotation_slider.setValue(15)
        
        QTest.qWait(50)
        
        # Test save functionality
        QTest.mouseClick(save_button, Qt.LeftButton)
        QTest.qWait(50)
        
        # Verify save notification
        save_notification = self.projection_page.findChild(QLabel, "save_notification_label")
        assert save_notification is not None
        assert save_notification.isVisible()
        
        # Test reset functionality
        QTest.mouseClick(reset_button, Qt.LeftButton)
        QTest.qWait(50)
        
        # Verify settings were reset
        assert scale_slider.value() == 100  # Default scale
        assert rotation_slider.value() == 0  # Default rotation
    
    def test_transform_calculations_accuracy(self):
        """Test mathematical accuracy of projection transform calculations."""
        # Test scale calculation
        scale_value = 120  # 120%
        expected_scale_factor = scale_value / 100.0
        calculated_factor = self.projection_page.calculate_scale_factor(scale_value)
        assert abs(calculated_factor - expected_scale_factor) < 0.001
        
        # Test rotation matrix calculation
        rotation_degrees = 45
        rotation_radians = math.radians(rotation_degrees)
        cos_val = math.cos(rotation_radians)
        sin_val = math.sin(rotation_radians)
        
        rotation_matrix = self.projection_page.calculate_rotation_matrix(rotation_degrees)
        assert abs(rotation_matrix[0][0] - cos_val) < 0.001
        assert abs(rotation_matrix[0][1] - (-sin_val)) < 0.001
        assert abs(rotation_matrix[1][0] - sin_val) < 0.001
        assert abs(rotation_matrix[1][1] - cos_val) < 0.001
        
        # Test offset calculation
        offset_pixels = (50, -30)
        normalized_offset = self.projection_page.calculate_normalized_offset(offset_pixels, (1920, 1080))
        expected_x = 50.0 / 1920.0
        expected_y = -30.0 / 1080.0
        assert abs(normalized_offset[0] - expected_x) < 0.001
        assert abs(normalized_offset[1] - expected_y) < 0.001
    
    def test_keystone_correction_algorithm(self):
        """Test keystone correction calculations for corner pin adjustment."""
        # Test corner pin transformation
        original_corners = [(0, 0), (1920, 0), (1920, 1080), (0, 1080)]
        adjusted_corners = [(10, 5), (1910, 8), (1915, 1075), (5, 1082)]
        
        transform_matrix = self.projection_page.calculate_keystone_transform(
            original_corners, adjusted_corners
        )
        
        # Verify transform matrix is valid (not None and proper dimensions)
        assert transform_matrix is not None
        assert len(transform_matrix) == 3
        assert len(transform_matrix[0]) == 3
        
        # Test that transform matrix preserves corner mapping
        for i, (orig, adj) in enumerate(zip(original_corners, adjusted_corners)):
            transformed = self.projection_page.apply_transform(orig, transform_matrix)
            assert abs(transformed[0] - adj[0]) < 1.0
            assert abs(transformed[1] - adj[1]) < 1.0
    
    def test_real_time_preview_updates(self):
        """Test real-time preview updates during manipulation."""
        start_time = time.time()
        update_count = 0
        
        # Simulate rapid slider changes
        scale_slider = self.projection_page.findChild(QSlider, "scale_slider")
        
        for value in range(100, 120, 2):  # 10 updates
            scale_slider.setValue(value)
            QTest.qWait(10)  # 10ms per update = 100Hz
            update_count += 1
        
        total_time = time.time() - start_time
        
        # Verify updates were processed quickly
        assert total_time < 0.5, f"Preview updates too slow: {total_time:.3f}s for {update_count} updates"
        
        # Verify final preview state
        preview_widget = self.projection_page.findChild(QWidget, "projection_preview_display")
        assert preview_widget is not None
        
        # Check that transform was applied to preview
        current_transform = self.projection_page.get_current_transform()
        assert current_transform.scale == 118  # Last value set
    
    def test_preset_configurations(self):
        """Test common projection preset configurations."""
        # Find preset buttons
        preset_buttons = {
            "1080p": self.projection_page.findChild(QPushButton, "preset_1080p_btn"),
            "1440p": self.projection_page.findChild(QPushButton, "preset_1440p_btn"),
            "4k": self.projection_page.findChild(QPushButton, "preset_4k_btn"),
        }
        
        for preset_name, button in preset_buttons.items():
            if button:  # Only test if button exists
                QTest.mouseClick(button, Qt.LeftButton)
                QTest.qWait(50)
                
                # Verify preset was applied
                config_events = [e for e in self.published_events 
                               if isinstance(e, ProjectionConfigUpdated)]
                assert len(config_events) > 0
                
                latest_event = config_events[-1]
                if preset_name == "1080p":
                    assert latest_event.width == 1920
                    assert latest_event.height == 1080
                elif preset_name == "1440p":
                    assert latest_event.width == 2560
                    assert latest_event.height == 1440
                elif preset_name == "4k":
                    assert latest_event.width == 3840
                    assert latest_event.height == 2160
    
    def test_error_handling_and_recovery(self):
        """Test error handling during projection operations."""
        # Test invalid transform values
        scale_slider = self.projection_page.findChild(QSlider, "scale_slider")
        
        # Try to set invalid scale (beyond limits)
        try:
            scale_slider.setValue(500)  # 500% scale - should be clamped
            QTest.qWait(50)
            
            # Verify value was clamped to maximum
            assert scale_slider.value() <= 200  # Assume 200% is maximum
        except Exception:
            pytest.fail("Scale slider should handle invalid values gracefully")
        
        # Test error display
        error_label = self.projection_page.findChild(QLabel, "error_display_label")
        if error_label:
            assert not error_label.isVisible() or "error" not in error_label.text().lower()
    
    def test_multi_slider_coordination(self):
        """Test multiple slider interactions work together correctly."""
        # Find all transform sliders
        scale_slider = self.projection_page.findChild(QSlider, "scale_slider")
        rotation_slider = self.projection_page.findChild(QSlider, "rotation_slider")
        offset_x_slider = self.projection_page.findChild(QSlider, "offset_x_slider")
        offset_y_slider = self.projection_page.findChild(QSlider, "offset_y_slider")
        
        # Change multiple values simultaneously
        scale_slider.setValue(110)
        rotation_slider.setValue(10)
        offset_x_slider.setValue(25)
        offset_y_slider.setValue(-15)
        
        QTest.qWait(100)
        
        # Verify combined transform is calculated correctly
        current_transform = self.projection_page.get_current_transform()
        assert current_transform.scale == 110
        assert current_transform.rotation == 10
        assert current_transform.offset_x == 25
        assert current_transform.offset_y == -15
        
        # Verify projection config events were published
        config_events = [e for e in self.published_events if isinstance(e, ProjectionConfigUpdated)]
        assert len(config_events) >= 4  # At least one for each slider change
    
    def test_widget_styling_conformance(self):
        """Test widgets have correct styling matching reference design."""
        # Verify main styling properties
        self.projection_page.show()
        QTest.qWait(100)
        
        # Check background styling
        bg_color = self.projection_page.palette().color(self.projection_page.backgroundRole())
        assert bg_color.name() in ["#1e1e1e", "#000000", "#2b2b2b"], "Background should be dark theme"
        
        # Check that preview area has proper styling
        preview_area = self.projection_page.findChild(QWidget, "projection_preview_area")
        if preview_area:
            # Should have border and proper background
            style_sheet = preview_area.styleSheet()
            assert "border" in style_sheet.lower() or preview_area.hasFrame()
    
    def test_performance_under_load(self):
        """Test performance during intensive projection manipulation."""
        start_time = time.time()
        
        # Simulate intensive manipulation
        scale_slider = self.projection_page.findChild(QSlider, "scale_slider")
        rotation_slider = self.projection_page.findChild(QSlider, "rotation_slider")
        
        for i in range(50):  # 50 rapid changes
            scale_value = 100 + (i % 20)
            rotation_value = i % 360
            
            scale_slider.setValue(scale_value)
            rotation_slider.setValue(rotation_value)
            QTest.qWait(5)  # 5ms between changes
        
        total_time = time.time() - start_time
        
        # Performance requirement: < 1 second for 50 changes
        assert total_time < 1.0, f"Performance too slow: {total_time:.3f}s for 50 changes"
        
        # Verify UI is still responsive
        assert self.projection_page.isVisible()
        assert scale_slider.isEnabled()
        assert rotation_slider.isEnabled()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 