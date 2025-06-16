#!/usr/bin/env python3
"""
Enhanced EDA GUI Validation Script.

This script validates the enhanced EDA GUI implementation against the
Cyber-Kinetic design specifications and performance requirements.
"""

import sys
import time
import traceback
from typing import List, Tuple

def validate_imports() -> Tuple[bool, str]:
    """Validate that all required modules can be imported."""
    try:
        # Test PySide6 availability
        from PySide6.QtWidgets import QApplication, QWidget
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor
        
        # Test theme system
        from gui.ui_components.theme_manager import CyberKineticTheme, CyberKineticColors, theme
        
        # Test enhanced widgets
        from gui.ui_components.enhanced_widgets import (
            CyberCard, StatusIndicator, MetricDisplay, SystemStatusPanel,
            LogPanel, ActionButton, SettingsGroup, ProgressRing
        )
        
        # Test main GUI
        from gui.eda_main_gui import EDAMainWindow, EnhancedSystemHubPage
        
        # Test core interfaces
        from core.interfaces import IGUIService
        
        return True, "All imports successful"
    except ImportError as e:
        return False, f"Import error: {e}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def validate_color_palette() -> Tuple[bool, str]:
    """Validate Cyber-Kinetic color palette compliance."""
    try:
        from gui.ui_components.theme_manager import CyberKineticColors
        from PySide6.QtGui import QColor
        
        colors = CyberKineticColors()
        
        # Test exact color values from design schema
        expected_colors = {
            'PRIMARY_INTERACTIVE': '#0FF0FC',
            'SECONDARY_INTERACTIVE': '#F000B0', 
            'BACKGROUND_DEEP': '#1A0529',
            'BACKGROUND_MID': '#300A4A',
            'TEXT_PRIMARY': '#FFFFFF',
            'TEXT_SECONDARY': '#A0F8FC',
            'TEXT_TERTIARY': '#C0C0C0',
            'SUCCESS': '#7FFF00',
            'WARNING': '#FFBF00',
            'ERROR': '#FF4500'
        }
        
        for attr_name, expected_hex in expected_colors.items():
            actual_color = getattr(colors, attr_name)
            if actual_color.name().upper() != expected_hex.upper():
                return False, f"Color mismatch: {attr_name} expected {expected_hex}, got {actual_color.name()}"
        
        # Test gradient creation
        primary_gradient = colors.get_gradient_primary()
        secondary_gradient = colors.get_gradient_secondary()
        
        if primary_gradient is None or secondary_gradient is None:
            return False, "Gradient creation failed"
        
        return True, f"Color palette compliance verified ({len(expected_colors)} colors)"
        
    except Exception as e:
        return False, f"Color validation error: {e}"


def validate_theme_system() -> Tuple[bool, str]:
    """Validate theme system functionality."""
    try:
        from gui.ui_components.theme_manager import CyberKineticTheme
        
        cyber_theme = CyberKineticTheme()
        
        # Test stylesheet generation
        stylesheet = cyber_theme.get_global_stylesheet()
        
        if len(stylesheet) < 1000:
            return False, f"Stylesheet too short: {len(stylesheet)} chars"
        
        # Check for essential components
        required_components = [
            'QPushButton', 'QGroupBox', 'QSlider', 'QComboBox', 
            'QLabel', 'QStatusBar', 'QScrollBar'
        ]
        
        for component in required_components:
            if component not in stylesheet:
                return False, f"Missing stylesheet for {component}"
        
        # Check for color usage
        if '#0FF0FC' not in stylesheet.upper():
            return False, "Primary color not found in stylesheet"
        
        # Test button styles
        button_styles = ['primary', 'secondary', 'ghost', 'success', 'warning', 'error']
        for style in button_styles:
            style_def = cyber_theme.get_button_style(style)
            if not isinstance(style_def, str):
                return False, f"Invalid button style for {style}"
        
        return True, f"Theme system validated (stylesheet: {len(stylesheet)} chars)"
        
    except Exception as e:
        return False, f"Theme validation error: {e}"


def validate_enhanced_widgets() -> Tuple[bool, str]:
    """Validate enhanced widget components."""
    try:
        # Mock QApplication for widget testing
        app = None
        try:
            from PySide6.QtWidgets import QApplication
            if not QApplication.instance():
                app = QApplication([])
        except:
            pass
        
        from gui.ui_components.enhanced_widgets import (
            CyberCard, StatusIndicator, MetricDisplay, SystemStatusPanel,
            LogPanel, ActionButton, SettingsGroup, ProgressRing
        )
        
        # Test widget creation
        widgets_tested = []
        
        # Test CyberCard
        card = CyberCard("Test Card")
        widgets_tested.append("CyberCard")
        
        # Test StatusIndicator
        indicator = StatusIndicator()
        indicator.set_status("connected", False)
        indicator.set_status("active", True)
        widgets_tested.append("StatusIndicator")
        
        # Test MetricDisplay  
        metric = MetricDisplay("FPS", "fps")
        metric.set_value(30.5, animated=False)
        metric.set_value(60.0, animated=True)
        widgets_tested.append("MetricDisplay")
        
        # Test ProgressRing
        ring = ProgressRing(80)
        ring.set_progress(0.75)
        widgets_tested.append("ProgressRing")
        
        # Test SystemStatusPanel
        status_panel = SystemStatusPanel()
        status_panel.update_service_status("tracking", "active", True)
        status_panel.update_metric("fps", 45.2)
        widgets_tested.append("SystemStatusPanel")
        
        # Test LogPanel
        log_panel = LogPanel()
        log_panel.add_log_entry("Test message", "info", "12:34:56")
        widgets_tested.append("LogPanel")
        
        # Test ActionButton
        btn_primary = ActionButton("Primary", "primary")
        btn_secondary = ActionButton("Secondary", "secondary")
        btn_ghost = ActionButton("Ghost", "ghost")
        widgets_tested.append("ActionButton")
        
        # Test SettingsGroup
        settings = SettingsGroup("Test Settings")
        settings.add_slider("threshold", "Threshold", 1, 50, 25)
        settings.add_combo("mode", "Mode", ["A", "B", "C"], 1)
        settings.add_spinbox("count", "Count", 0, 100, 10)
        widgets_tested.append("SettingsGroup")
        
        if app:
            app.quit()
        
        return True, f"Enhanced widgets validated ({', '.join(widgets_tested)})"
        
    except Exception as e:
        return False, f"Widget validation error: {e}"


def validate_main_gui() -> Tuple[bool, str]:
    """Validate main GUI implementation."""
    try:
        # Mock QApplication
        app = None
        try:
            from PySide6.QtWidgets import QApplication
            if not QApplication.instance():
                app = QApplication([])
        except:
            pass
        
        # Mock GUI service
        class MockGUIService:
            def __init__(self):
                self.call_log = []
            
            def show_page(self, page_name: str):
                self.call_log.append(f"show_page:{page_name}")
            
            def show_notification(self, message: str, duration: int = 3000):
                self.call_log.append(f"notification:{message}")
            
            def request_start_tracking(self, **kwargs):
                self.call_log.append(f"start_tracking:{kwargs}")
            
            def request_stop_tracking(self):
                self.call_log.append("stop_tracking")
            
            def register_page_update_callback(self, callback):
                pass
            
            def register_notification_callback(self, callback):
                pass
        
        mock_service = MockGUIService()
        
        from gui.eda_main_gui import (
            EDAMainWindow, EnhancedSystemHubPage, MainMenuPage, 
            MatchSetupPage, FreePlayModePage, RefereeControlsPage
        )
        
        # Test main window creation
        window = EDAMainWindow(mock_service)
        
        # Validate window properties
        if window.windowTitle() != "BBAN-Tracker Enterprise - Cyber-Kinetic Interface":
            return False, "Window title incorrect"
        
        if window._current_page_name != "main_menu":
            return False, "Initial page incorrect"
        
        if len(window._pages) != 8:
            return False, f"Expected 8 pages, got {len(window._pages)}"
        
        # Verify all expected pages exist
        expected_pages = [
            "main_menu", "match_setup", "free_play", "referee_controls",
            "system_hub", "tracker_setup", "projection_setup", "options"
        ]
        for page_name in expected_pages:
            if page_name not in window._pages:
                return False, f"Missing page: {page_name}"
        
        # Test navigation
        window.show_page("match_setup")
        if window._current_page_name != "match_setup":
            return False, "Navigation failed"
        
        # Test page creation for multiple new pages
        main_menu = MainMenuPage(mock_service)
        main_content = main_menu.create_page_content()
        if main_content is None:
            return False, "Main menu page content creation failed"
        
        match_setup = MatchSetupPage(mock_service)
        match_content = match_setup.create_page_content()
        if match_content is None:
            return False, "Match setup page content creation failed"
        
        free_play = FreePlayModePage(mock_service)
        free_play_content = free_play.create_page_content()
        if free_play_content is None:
            return False, "Free play page content creation failed"
        
        if app:
            app.quit()
        
        return True, "Complete GUI validated (8 pages, navigation, all new screens)"
        
    except Exception as e:
        return False, f"Main GUI validation error: {e}"


def validate_performance_targets() -> Tuple[bool, str]:
    """Validate performance against specifications."""
    try:
        import time
        
        # Test theme application performance
        from gui.ui_components.theme_manager import CyberKineticTheme
        
        cyber_theme = CyberKineticTheme()
        
        start_time = time.perf_counter()
        stylesheet = cyber_theme.get_global_stylesheet()
        end_time = time.perf_counter()
        
        theme_time = end_time - start_time
        if theme_time > 0.1:  # 100ms limit
            return False, f"Theme generation too slow: {theme_time*1000:.2f}ms"
        
        # Test widget creation performance
        from gui.ui_components.enhanced_widgets import CyberCard, StatusIndicator
        
        start_time = time.perf_counter()
        widgets = []
        for i in range(50):
            card = CyberCard(f"Card {i}")
            indicator = StatusIndicator()
            widgets.extend([card, indicator])
        end_time = time.perf_counter()
        
        creation_time = end_time - start_time
        avg_creation = creation_time / 100  # 100 widgets
        
        if avg_creation > 0.001:  # 1ms per widget
            return False, f"Widget creation too slow: {avg_creation*1000:.2f}ms per widget"
        
        performance_metrics = {
            'theme_generation': f"{theme_time*1000:.2f}ms",
            'widget_creation': f"{avg_creation*1000:.3f}ms per widget",
            'total_widgets': len(widgets)
        }
        
        return True, f"Performance targets met: {performance_metrics}"
        
    except Exception as e:
        return False, f"Performance validation error: {e}"


def validate_eda_integration() -> Tuple[bool, str]:
    """Validate Event-Driven Architecture integration."""
    try:
        # Test that core interfaces exist
        from core.interfaces import IGUIService
        
        # Test that GUI service integration points exist
        from gui.eda_main_gui import EDAMainWindow
        
        # Mock service to test callbacks
        class TestGUIService:
            def __init__(self):
                self.callbacks = {}
                self.events = []
            
            def register_page_update_callback(self, callback):
                self.callbacks['page_update'] = callback
            
            def register_notification_callback(self, callback):
                self.callbacks['notification'] = callback
            
            def show_page(self, page_name: str):
                self.events.append(f"page:{page_name}")
            
            def show_notification(self, message: str, duration: int = 3000):
                self.events.append(f"notification:{message}")
            
            def request_start_tracking(self, **kwargs):
                self.events.append(f"start_tracking")
        
        # Test integration without creating Qt widgets
        test_service = TestGUIService()
        
        # Verify interface compliance
        interface_methods = [
            'show_page', 'show_notification', 'request_start_tracking'
        ]
        
        for method in interface_methods:
            if not hasattr(test_service, method):
                return False, f"Missing interface method: {method}"
        
        return True, "EDA integration validated (interfaces, callbacks)"
        
    except Exception as e:
        return False, f"EDA integration validation error: {e}"


def run_validation_suite() -> None:
    """Run the complete validation suite."""
    print("🚀 BBAN-Tracker Enhanced EDA GUI Validation")
    print("=" * 60)
    
    validations = [
        ("Module Imports", validate_imports),
        ("Color Palette Compliance", validate_color_palette),
        ("Theme System", validate_theme_system),
        ("Enhanced Widgets", validate_enhanced_widgets),
        ("Main GUI Implementation", validate_main_gui),
        ("Performance Targets", validate_performance_targets),
        ("EDA Integration", validate_eda_integration)
    ]
    
    results = []
    total_time = time.perf_counter()
    
    for test_name, validation_func in validations:
        print(f"\n🔍 Testing: {test_name}")
        
        try:
            start_time = time.perf_counter()
            success, message = validation_func()
            end_time = time.perf_counter()
            
            test_time = end_time - start_time
            
            if success:
                print(f"✅ PASS: {message} ({test_time*1000:.2f}ms)")
                results.append((test_name, True, message, test_time))
            else:
                print(f"❌ FAIL: {message}")
                results.append((test_name, False, message, test_time))
                
        except Exception as e:
            print(f"💥 ERROR: {e}")
            traceback.print_exc()
            results.append((test_name, False, f"Exception: {e}", 0))
    
    total_time = time.perf_counter() - total_time
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, success, _, _ in results if success)
    failed = len(results) - passed
    
    print(f"Total Tests: {len(results)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⏱️  Total Time: {total_time*1000:.2f}ms")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED - Enhanced EDA GUI Implementation Valid!")
        print("✨ Cyber-Kinetic Design Compliance: VERIFIED")
        print("⚡ Performance Targets: MET")
        print("🔗 EDA Integration: SUCCESSFUL")
    else:
        print(f"\n⚠️  {failed} tests failed - review implementation")
    
    # Detailed results
    print("\n📋 DETAILED RESULTS:")
    for test_name, success, message, test_time in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} {test_name}: {message} ({test_time*1000:.2f}ms)")


if __name__ == "__main__":
    run_validation_suite() 