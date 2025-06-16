"""
Comprehensive tests for Enhanced EDA GUI System.

Tests cover theme system, enhanced widgets, main GUI, performance metrics,
and compliance with Cyber-Kinetic design specifications.
"""

import pytest
import time
import sys
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

import sys
sys.path.append('../')

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

# Import components under test
from gui.ui_components.theme_manager import CyberKineticTheme, CyberKineticColors, theme
from gui.ui_components.enhanced_widgets import (
    CyberCard, StatusIndicator, MetricDisplay, SystemStatusPanel,
    LogPanel, ActionButton, SettingsGroup, ProgressRing
)
from gui.eda_main_gui import EDAMainWindow, EnhancedSystemHubPage
from core.interfaces import IGUIService


class MockGUIService:
    """Mock GUI service for testing."""
    
    def __init__(self):
        self._running = True
        self._current_page = "system_hub"
        self._callbacks = {}
        self.call_log = []
    
    def is_running(self) -> bool:
        return self._running
    
    def show_page(self, page_name: str):
        self.call_log.append(f"show_page:{page_name}")
        self._current_page = page_name
    
    def show_notification(self, message: str, duration: int = 3000):
        self.call_log.append(f"notification:{message}")
    
    def request_start_tracking(self, dev_mode: bool = False, cam_src: int = 0, video_path: str = None):
        self.call_log.append(f"start_tracking:dev={dev_mode},cam={cam_src}")
    
    def request_stop_tracking(self):
        self.call_log.append("stop_tracking")
    
    def request_calibration(self):
        self.call_log.append("calibration")
    
    def update_tracker_settings(self, **kwargs):
        self.call_log.append(f"tracker_settings:{kwargs}")
    
    def update_realsense_settings(self, **kwargs):
        self.call_log.append(f"realsense_settings:{kwargs}")
    
    def update_projection_config(self, width: int, height: int):
        self.call_log.append(f"projection_config:{width}x{height}")
    
    def register_page_update_callback(self, callback):
        self._callbacks['page_update'] = callback
    
    def register_notification_callback(self, callback):
        self._callbacks['notification'] = callback
    
    def trigger_state_update(self, state: Dict[str, Any]):
        """Trigger a state update for testing."""
        if 'page_update' in self._callbacks:
            self._callbacks['page_update'](state)
    
    def get_current_page(self) -> str:
        return self._current_page


@pytest.fixture
def qapp():
    """Provide QApplication instance for tests."""
    if not QApplication.instance():
        app = QApplication([])
        yield app
        app.quit()
    else:
        yield QApplication.instance()


@pytest.fixture
def mock_gui_service():
    """Provide mock GUI service."""
    return MockGUIService()


class TestCyberKineticTheme:
    """Test the Cyber-Kinetic theme system."""
    
    def test_color_definitions(self):
        """Test that all required colors are defined correctly."""
        colors = CyberKineticColors()
        
        # Test primary colors
        assert colors.PRIMARY_INTERACTIVE == QColor("#0FF0FC")
        assert colors.SECONDARY_INTERACTIVE == QColor("#F000B0")
        assert colors.BACKGROUND_DEEP == QColor("#1A0529")
        assert colors.BACKGROUND_MID == QColor("#300A4A")
        
        # Test text colors
        assert colors.TEXT_PRIMARY == QColor("#FFFFFF")
        assert colors.TEXT_SECONDARY == QColor("#A0F8FC")
        assert colors.TEXT_TERTIARY == QColor("#C0C0C0")
        
        # Test status colors
        assert colors.SUCCESS == QColor("#7FFF00")
        assert colors.WARNING == QColor("#FFBF00")
        assert colors.ERROR == QColor("#FF4500")
    
    def test_gradients(self):
        """Test gradient generation."""
        primary_gradient = CyberKineticColors.get_gradient_primary()
        secondary_gradient = CyberKineticColors.get_gradient_secondary()
        
        assert primary_gradient is not None
        assert secondary_gradient is not None
    
    def test_theme_application(self, qapp):
        """Test theme application to QApplication."""
        cyber_theme = CyberKineticTheme()
        
        # Should not crash when applying theme
        cyber_theme.apply_to_application(qapp)
        
        # Test global stylesheet generation
        stylesheet = cyber_theme.get_global_stylesheet()
        assert len(stylesheet) > 1000  # Should be comprehensive
        assert "QPushButton" in stylesheet
        assert "QGroupBox" in stylesheet
        assert "#0FF0FC" in stylesheet  # Primary color should be present
    
    def test_button_styles(self):
        """Test button style generation."""
        cyber_theme = CyberKineticTheme()
        
        primary_style = cyber_theme.get_button_style("primary")
        secondary_style = cyber_theme.get_button_style("secondary")
        ghost_style = cyber_theme.get_button_style("ghost")
        success_style = cyber_theme.get_button_style("success")
        
        assert isinstance(primary_style, str)
        assert isinstance(secondary_style, str)
        assert isinstance(ghost_style, str)
        assert isinstance(success_style, str)


class TestEnhancedWidgets:
    """Test enhanced widget components."""
    
    def test_cyber_card_creation(self, qapp):
        """Test CyberCard widget creation."""
        card = CyberCard("Test Card")
        
        assert card.title() == "Test Card"
        assert isinstance(card, QWidget)
    
    def test_status_indicator(self, qapp):
        """Test StatusIndicator widget."""
        indicator = StatusIndicator()
        
        # Test status changes
        indicator.set_status("connected", False)
        indicator.set_status("active", True)
        indicator.set_status("error", False)
        
        # Should not crash
        assert indicator._status == "error"
        assert not indicator._animated
    
    def test_metric_display(self, qapp):
        """Test MetricDisplay widget."""
        metric = MetricDisplay("FPS", "fps")
        
        # Test value updates
        metric.set_value(30.5, animated=False)
        assert metric._value == 30.5
        
        metric.set_value(60.0, animated=True)
        assert metric._target_value == 60.0
    
    def test_progress_ring(self, qapp):
        """Test ProgressRing widget."""
        ring = ProgressRing(80)
        
        ring.set_progress(0.0)
        assert ring._progress == 0.0
        
        ring.set_progress(0.75)
        assert ring._progress == 0.75
        
        ring.set_progress(1.5)  # Should be clamped
        assert ring._progress == 1.0
    
    def test_system_status_panel(self, qapp):
        """Test SystemStatusPanel widget."""
        panel = SystemStatusPanel()
        
        # Test service status updates
        panel.update_service_status("tracking", "active", True)
        panel.update_metric("fps", 45.2)
        panel.update_metric("latency", 12.5)
        
        # Should not crash
        assert isinstance(panel, QWidget)
    
    def test_log_panel(self, qapp):
        """Test LogPanel widget."""
        log_panel = LogPanel()
        
        # Test log entry addition
        log_panel.add_log_entry("Test message", "info", "12:34:56")
        log_panel.add_log_entry("Warning message", "warning", "12:35:00")
        log_panel.add_log_entry("Error message", "error", "12:35:15")
        
        # Should have entries
        assert log_panel._log_layout.count() > 1  # Includes stretch
    
    def test_action_button_styles(self, qapp):
        """Test ActionButton with different styles."""
        primary_btn = ActionButton("Primary", "primary")
        secondary_btn = ActionButton("Secondary", "secondary")
        ghost_btn = ActionButton("Ghost", "ghost")
        
        assert primary_btn._button_style == "primary"
        assert secondary_btn._button_style == "secondary" 
        assert ghost_btn._button_style == "ghost"
    
    def test_settings_group(self, qapp):
        """Test SettingsGroup widget."""
        settings = SettingsGroup("Test Settings")
        
        # Test adding different control types
        settings.add_slider("threshold", "Threshold", 1, 50, 25)
        settings.add_combo("mode", "Mode", ["A", "B", "C"], 1)
        settings.add_spinbox("count", "Count", 0, 100, 10)
        
        # Test value retrieval
        assert settings.get_value("threshold") == 25
        assert settings.get_value("mode") == 1
        assert settings.get_value("count") == 10


class TestEDAMainWindow:
    """Test the main EDA window implementation."""
    
    def test_window_creation(self, qapp, mock_gui_service):
        """Test main window creation."""
        window = EDAMainWindow(mock_gui_service)
        
        assert window.windowTitle() == "BBAN-Tracker Enterprise - Cyber-Kinetic Interface"
        assert window._current_page_name == "system_hub"
        assert len(window._pages) == 4  # system_hub, tracker_setup, projection_setup, options
    
    def test_navigation(self, qapp, mock_gui_service):
        """Test page navigation."""
        window = EDAMainWindow(mock_gui_service)
        
        # Test navigation to different pages
        window.show_page("tracker_setup")
        assert window._current_page_name == "tracker_setup"
        assert "show_page:tracker_setup" in mock_gui_service.call_log
        
        window.show_page("projection_setup")
        assert window._current_page_name == "projection_setup"
        
        window.show_page("options")
        assert window._current_page_name == "options"
    
    def test_toolbar_actions(self, qapp, mock_gui_service):
        """Test toolbar action functionality."""
        window = EDAMainWindow(mock_gui_service)
        
        # Test start tracking
        window._start_tracking()
        assert any("start_tracking" in call for call in mock_gui_service.call_log)
        
        # Test stop tracking
        window._stop_tracking()
        assert "stop_tracking" in mock_gui_service.call_log
    
    def test_state_updates(self, qapp, mock_gui_service):
        """Test handling of state updates."""
        window = EDAMainWindow(mock_gui_service)
        
        # Trigger state update
        test_state = {
            'tracking_active': True,
            'projection_connected': False,
            'performance_metrics': {
                'tracking_fps': {'value': 45.2, 'unit': 'fps'},
                'projection_latency': {'value': 12.5, 'unit': 'ms'}
            }
        }
        
        mock_gui_service.trigger_state_update(test_state)
        
        # Should not crash and should update UI elements
        assert window._system_status is not None
    
    def test_notification_handling(self, qapp, mock_gui_service):
        """Test notification system."""
        window = EDAMainWindow(mock_gui_service)
        
        # Test notification callback
        window._handle_notification("Test notification", 3000)
        
        # Should add to log panel
        assert window._log_panel is not None


class TestEnhancedPages:
    """Test enhanced page implementations."""
    
    def test_system_hub_page(self, qapp, mock_gui_service):
        """Test EnhancedSystemHubPage."""
        page = EnhancedSystemHubPage(mock_gui_service)
        content = page.create_page_content()
        
        assert isinstance(content, QWidget)
        
        # Test action methods
        page._start_free_play()
        assert any("start_tracking" in call for call in mock_gui_service.call_log)
        
        page._test_hardware()
        assert any("notification" in call for call in mock_gui_service.call_log)
    
    def test_page_event_integration(self, qapp, mock_gui_service):
        """Test page integration with event system."""
        page = EnhancedSystemHubPage(mock_gui_service)
        
        # Test event subscription setup (should not crash)
        page.setup_event_subscriptions()


class TestPerformanceCompliance:
    """Test performance compliance with specifications."""
    
    def test_ui_update_performance(self, qapp, mock_gui_service):
        """Test UI update performance (<16ms target)."""
        window = EDAMainWindow(mock_gui_service)
        
        # Measure page switching performance
        start_time = time.perf_counter()
        
        for _ in range(10):
            window.show_page("tracker_setup")
            window.show_page("projection_setup")
            window.show_page("system_hub")
        
        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 30  # 30 page switches
        
        # Should be well under 16ms (0.016 seconds)
        assert avg_time < 0.010, f"UI update too slow: {avg_time*1000:.2f}ms"
    
    def test_widget_creation_performance(self, qapp):
        """Test widget creation performance."""
        start_time = time.perf_counter()
        
        # Create multiple widgets
        widgets = []
        for i in range(100):
            card = CyberCard(f"Card {i}")
            indicator = StatusIndicator()
            metric = MetricDisplay(f"Metric {i}", "unit")
            widgets.extend([card, indicator, metric])
        
        end_time = time.perf_counter()
        creation_time = end_time - start_time
        
        # Should create 300 widgets quickly
        assert creation_time < 1.0, f"Widget creation too slow: {creation_time:.3f}s"
    
    def test_theme_application_performance(self, qapp):
        """Test theme application performance."""
        cyber_theme = CyberKineticTheme()
        
        start_time = time.perf_counter()
        cyber_theme.apply_to_application(qapp)
        end_time = time.perf_counter()
        
        theme_time = end_time - start_time
        
        # Theme application should be fast
        assert theme_time < 0.1, f"Theme application too slow: {theme_time:.3f}s"
    
    def test_memory_usage(self, qapp, mock_gui_service):
        """Test memory usage compliance."""
        import gc
        import sys
        
        # Force garbage collection
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Create and destroy multiple windows
        windows = []
        for i in range(5):
            window = EDAMainWindow(mock_gui_service)
            windows.append(window)
        
        # Clean up
        for window in windows:
            window.close()
            window.deleteLater()
        
        windows.clear()
        gc.collect()
        
        final_objects = len(gc.get_objects())
        object_growth = final_objects - initial_objects
        
        # Should not have significant memory leaks
        assert object_growth < 1000, f"Potential memory leak: {object_growth} objects"


class TestEventDrivenArchitecture:
    """Test EDA integration and event flow."""
    
    def test_event_subscription_setup(self, qapp, mock_gui_service):
        """Test event subscription setup."""
        window = EDAMainWindow(mock_gui_service)
        
        # Test that callbacks are registered
        assert 'page_update' in mock_gui_service._callbacks
        assert 'notification' in mock_gui_service._callbacks
    
    def test_event_flow(self, qapp, mock_gui_service):
        """Test complete event flow."""
        window = EDAMainWindow(mock_gui_service)
        
        # Simulate tracking start event
        window._start_tracking()
        
        # Simulate state change
        state_update = {
            'tracking_active': True,
            'performance_metrics': {
                'tracking_fps': {'value': 30.0, 'unit': 'fps'}
            }
        }
        mock_gui_service.trigger_state_update(state_update)
        
        # Check that events were processed
        assert any("start_tracking" in call for call in mock_gui_service.call_log)
    
    def test_gui_service_integration(self, qapp, mock_gui_service):
        """Test GUI service method calls."""
        window = EDAMainWindow(mock_gui_service)
        page = window._pages["tracker_setup"]
        
        # Test various GUI service calls
        page.update_tracker_settings(threshold=30)
        page.update_realsense_settings(exposure=60)
        page.update_projection_config(1920, 1080)
        
        # Verify calls were made
        assert any("tracker_settings" in call for call in mock_gui_service.call_log)
        assert any("realsense_settings" in call for call in mock_gui_service.call_log)
        assert any("projection_config" in call for call in mock_gui_service.call_log)


class TestCyberKineticDesignCompliance:
    """Test compliance with Cyber-Kinetic design specifications."""
    
    def test_color_palette_compliance(self):
        """Test that color palette matches specification."""
        colors = CyberKineticColors()
        
        # Test exact color values from design schema
        assert colors.PRIMARY_INTERACTIVE.name() == "#0ff0fc"
        assert colors.SECONDARY_INTERACTIVE.name() == "#f000b0"
        assert colors.BACKGROUND_DEEP.name() == "#1a0529"
        assert colors.BACKGROUND_MID.name() == "#300a4a"
        assert colors.TEXT_PRIMARY.name() == "#ffffff"
        assert colors.SUCCESS.name() == "#7fff00"
        assert colors.WARNING.name() == "#ffbf00"
        assert colors.ERROR.name() == "#ff4500"
    
    def test_typography_system(self):
        """Test typography system compliance."""
        cyber_theme = CyberKineticTheme()
        
        # Test font creation
        heading_font = cyber_theme.fonts.get_heading_font(24)
        body_font = cyber_theme.fonts.get_body_font(12)
        ui_font = cyber_theme.fonts.get_ui_font(11)
        
        assert heading_font.pointSize() == 24
        assert body_font.pointSize() == 12
        assert ui_font.pointSize() == 11
    
    def test_component_styling(self, qapp):
        """Test that components have proper styling."""
        # Apply theme first
        theme.apply_to_application(qapp)
        
        # Test button styling
        primary_btn = ActionButton("Test", "primary")
        secondary_btn = ActionButton("Test", "secondary")
        ghost_btn = ActionButton("Test", "ghost")
        
        # Test card styling
        card = CyberCard("Test Card")
        
        # Test status indicator
        indicator = StatusIndicator()
        
        # These should all have proper styling applied
        assert isinstance(primary_btn, QWidget)
        assert isinstance(card, QWidget)
        assert isinstance(indicator, QWidget)


def test_complete_integration(qapp, mock_gui_service):
    """Test complete system integration."""
    # Create main window
    window = EDAMainWindow(mock_gui_service)
    
    # Test navigation through all pages
    pages = ["system_hub", "tracker_setup", "projection_setup", "options"]
    for page in pages:
        window.show_page(page)
        assert window._current_page_name == page
    
    # Test system actions
    window._start_tracking()
    window._stop_tracking()
    
    # Test state updates
    state = {
        'tracking_active': True,
        'projection_connected': True,
        'performance_metrics': {
            'tracking_fps': {'value': 60.0},
            'latency': {'value': 8.5}
        }
    }
    mock_gui_service.trigger_state_update(state)
    
    # Test notifications
    window._handle_notification("Integration test complete", 3000)
    
    # Verify all operations completed without errors
    assert len(mock_gui_service.call_log) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 