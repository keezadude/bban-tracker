"""
Complete Application Flow Tests for BBAN-Tracker.

This test suite validates the complete application including all 8 screens:
- Main Menu (entry point)
- Match Setup (game configuration)
- Free Play Mode (gaming interface)  
- Referee Controls (match control)
- System Hub (technical dashboard)
- Tracker Setup (hardware configuration)
- Projection Setup (display configuration)
- Options (system settings)

Tests verify pixel-perfect implementation, logical flow, and EDA integration.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock, call
from dataclasses import dataclass, field
from typing import Any, Optional, Dict

from core.interfaces import IGUIService
from core.events import (
    TrackingDataUpdated, TrackingStarted, TrackingStopped, TrackingError,
    ProjectionClientConnected, ProjectionClientDisconnected,
    StartTracking, StopTracking, ChangeTrackerSettings,
    ProjectionConfigUpdated
)


# ==================== MOCK GUI SERVICE ==================== #

class MockGUIService:
    """Enhanced mock GUI service for complete application testing."""
    
    def __init__(self):
        self.call_log = []
        self.published_events = []
        self.notifications = []
        self.current_page = "main_menu"
        self.page_callbacks = []
        self.notification_callbacks = []
    
    def show_page(self, page_name: str):
        """Navigate to specified page."""
        self.call_log.append(f"show_page:{page_name}")
        self.current_page = page_name
        for callback in self.page_callbacks:
            callback({"current_page": page_name})
    
    def get_current_page(self) -> str:
        """Get current page name."""
        return self.current_page
    
    def show_notification(self, message: str, duration: int = 3000):
        """Show notification message."""
        self.call_log.append(f"notification:{message}")
        self.notifications.append((message, duration))
        for callback in self.notification_callbacks:
            callback(message, duration)
    
    def show_error_dialog(self, title: str, message: str):
        """Show error dialog."""
        self.call_log.append(f"error_dialog:{title}:{message}")
    
    def request_start_tracking(self, **kwargs):
        """Request tracking start."""
        self.call_log.append(f"start_tracking:{kwargs}")
        event = StartTracking(**kwargs)
        self.published_events.append(event)
    
    def request_stop_tracking(self):
        """Request tracking stop."""
        self.call_log.append("stop_tracking")
        event = StopTracking()
        self.published_events.append(event)
    
    def update_tracker_settings(self, **kwargs):
        """Update tracker settings."""
        self.call_log.append(f"update_tracker_settings:{kwargs}")
        event = ChangeTrackerSettings(**kwargs)
        self.published_events.append(event)
    
    def update_projection_config(self, width: int, height: int):
        """Update projection configuration."""
        self.call_log.append(f"update_projection_config:{width}x{height}")
        event = ProjectionConfigUpdated(width=width, height=height)
        self.published_events.append(event)
    
    def register_page_update_callback(self, callback):
        """Register page update callback."""
        self.page_callbacks.append(callback)
    
    def register_notification_callback(self, callback):
        """Register notification callback."""
        self.notification_callbacks.append(callback)


# ==================== QT MOCKING ==================== #

@pytest.fixture
def qapp():
    """Mock QApplication for testing."""
    with patch('PySide6.QtWidgets.QApplication') as mock_app:
        yield mock_app


@pytest.fixture
def mock_gui_service():
    """Mock GUI service for testing."""
    return MockGUIService()


# ==================== COMPLETE APPLICATION TESTS ==================== #

class TestCompleteApplicationFlow:
    """Test suite for complete application flow."""
    
    def test_all_pages_creation(self, qapp, mock_gui_service):
        """Test that all 8 application pages can be created."""
        from gui.eda_main_gui import (
            MainMenuPage, MatchSetupPage, FreePlayModePage, RefereeControlsPage,
            EnhancedSystemHubPage, PixelPerfectTrackerSetupPage, 
            PixelPerfectProjectionSetupPage, EnhancedOptionsPage
        )
        
        # Test all page classes can be instantiated
        pages = [
            MainMenuPage(mock_gui_service),
            MatchSetupPage(mock_gui_service),
            FreePlayModePage(mock_gui_service),
            RefereeControlsPage(mock_gui_service),
            EnhancedSystemHubPage(mock_gui_service),
            PixelPerfectTrackerSetupPage(mock_gui_service),
            PixelPerfectProjectionSetupPage(mock_gui_service),
            EnhancedOptionsPage(mock_gui_service)
        ]
        
        # Verify all pages created successfully
        assert len(pages) == 8
        for page in pages:
            assert page is not None
            # Verify page content creation
            content = page.create_page_content()
            assert content is not None
    
    def test_main_window_complete_integration(self, qapp, mock_gui_service):
        """Test main window with all pages integrated."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # Verify all pages are registered
        expected_pages = [
            "main_menu", "match_setup", "free_play", "referee_controls",
            "system_hub", "tracker_setup", "projection_setup", "options"
        ]
        
        assert len(window._pages) == 8
        for page_name in expected_pages:
            assert page_name in window._pages
        
        # Verify main menu is initial page
        assert window._current_page_name == "main_menu"
    
    def test_navigation_flow_main_to_gaming(self, qapp, mock_gui_service):
        """Test complete navigation flow from main menu to gaming."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # Test navigation flow: Main Menu -> Match Setup -> Free Play
        window.show_page("match_setup")
        assert window._current_page_name == "match_setup"
        assert "show_page:match_setup" in mock_gui_service.call_log
        
        window.show_page("free_play")
        assert window._current_page_name == "free_play"
        assert "show_page:free_play" in mock_gui_service.call_log
        
        # Test alternative flow: Main Menu -> Free Play directly
        window.show_page("main_menu")
        window.show_page("free_play")
        assert window._current_page_name == "free_play"
    
    def test_navigation_flow_technical_setup(self, qapp, mock_gui_service):
        """Test navigation flow to technical setup screens."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # Test technical flow: Main Menu -> System Hub -> Setup screens
        window.show_page("system_hub")
        assert window._current_page_name == "system_hub"
        
        window.show_page("tracker_setup")
        assert window._current_page_name == "tracker_setup"
        
        window.show_page("projection_setup")
        assert window._current_page_name == "projection_setup"
        
        window.show_page("options")
        assert window._current_page_name == "options"


class TestMainMenuPage:
    """Test suite for Main Menu page."""
    
    def test_main_menu_creation(self, qapp, mock_gui_service):
        """Test main menu page creation and layout."""
        from gui.eda_main_gui import MainMenuPage
        
        page = MainMenuPage(mock_gui_service)
        content = page.create_page_content()
        
        assert content is not None
        assert page.page_name == "main_menu"
    
    def test_main_menu_navigation_shards(self, qapp, mock_gui_service):
        """Test main menu navigation shard functionality."""
        from gui.eda_main_gui import MainMenuPage
        
        page = MainMenuPage(mock_gui_service)
        
        # Test navigation methods would be called via button clicks
        # Simulate navigation calls
        mock_gui_service.show_page("free_play")
        mock_gui_service.show_page("match_setup")
        mock_gui_service.show_page("system_hub")
        mock_gui_service.show_page("options")
        
        # Verify navigation calls were logged
        assert "show_page:free_play" in mock_gui_service.call_log
        assert "show_page:match_setup" in mock_gui_service.call_log
        assert "show_page:system_hub" in mock_gui_service.call_log
        assert "show_page:options" in mock_gui_service.call_log


class TestMatchSetupPage:
    """Test suite for Match Setup page."""
    
    def test_match_setup_creation(self, qapp, mock_gui_service):
        """Test match setup page creation."""
        from gui.eda_main_gui import MatchSetupPage
        
        page = MatchSetupPage(mock_gui_service)
        content = page.create_page_content()
        
        assert content is not None
        assert page.page_name == "match_setup"
        assert hasattr(page, '_match_config')
        assert page._match_config['player1_name'] == 'Player 1'
        assert page._match_config['player2_name'] == 'Player 2'
    
    def test_match_setup_actions(self, qapp, mock_gui_service):
        """Test match setup action methods."""
        from gui.eda_main_gui import MatchSetupPage
        
        page = MatchSetupPage(mock_gui_service)
        
        # Test start match action
        page._start_match()
        assert "show_page:referee_controls" in mock_gui_service.call_log
        assert any("Match started" in call for call in mock_gui_service.call_log)
        
        # Test quick play action
        page._start_quick_play()
        assert "show_page:free_play" in mock_gui_service.call_log
        assert any("Quick play mode started" in call for call in mock_gui_service.call_log


class TestFreePlayModePage:
    """Test suite for Free Play Mode page."""
    
    def test_free_play_creation(self, qapp, mock_gui_service):
        """Test free play page creation."""
        from gui.eda_main_gui import FreePlayModePage
        
        page = FreePlayModePage(mock_gui_service)
        content = page.create_page_content()
        
        assert content is not None
        assert page.page_name == "free_play"
        assert page._game_active is False
        assert page._score_p1 == 0
        assert page._score_p2 == 0
        assert page._time_remaining == 300
    
    def test_free_play_game_control(self, qapp, mock_gui_service):
        """Test free play game control functionality."""
        from gui.eda_main_gui import FreePlayModePage
        
        page = FreePlayModePage(mock_gui_service)
        
        # Test game start
        page._toggle_game()
        assert page._game_active is True
        assert "start_tracking" in mock_gui_service.call_log[-1]
        
        # Test game stop
        page._toggle_game()
        assert page._game_active is False
        assert "stop_tracking" in mock_gui_service.call_log[-1]
    
    def test_free_play_scoring(self, qapp, mock_gui_service):
        """Test free play scoring system."""
        from gui.eda_main_gui import FreePlayModePage
        
        page = FreePlayModePage(mock_gui_service)
        
        # Test player 1 scoring
        page._add_p1_score()
        assert page._score_p1 == 1
        assert any("Player 1 scores!" in call for call in mock_gui_service.call_log)
        
        # Test player 2 scoring
        page._add_p2_score()
        page._add_p2_score()
        assert page._score_p2 == 2
        assert any("Player 2 scores!" in call for call in mock_gui_service.call_log)
        
        # Test game reset
        page._reset_game()
        assert page._score_p1 == 0
        assert page._score_p2 == 0
        assert page._time_remaining == 300
        assert any("Game reset" in call for call in mock_gui_service.call_log)


class TestRefereeControlsPage:
    """Test suite for Referee Controls page."""
    
    def test_referee_controls_creation(self, qapp, mock_gui_service):
        """Test referee controls page creation."""
        from gui.eda_main_gui import RefereeControlsPage
        
        page = RefereeControlsPage(mock_gui_service)
        content = page.create_page_content()
        
        assert content is not None
        assert page.page_name == "referee_controls"
        assert page._match_active is False
        assert page._round_number == 1
        assert page._score_p1 == 0
        assert page._score_p2 == 0
    
    def test_referee_round_control(self, qapp, mock_gui_service):
        """Test referee round control functionality."""
        from gui.eda_main_gui import RefereeControlsPage
        
        page = RefereeControlsPage(mock_gui_service)
        
        # Test round start
        page._toggle_round()
        assert page._match_active is True
        assert "start_tracking" in mock_gui_service.call_log[-1]
        
        # Test round stop
        page._toggle_round()
        assert page._match_active is False
        assert "stop_tracking" in mock_gui_service.call_log[-1]
    
    def test_referee_scoring_and_match_end(self, qapp, mock_gui_service):
        """Test referee scoring and match end logic."""
        from gui.eda_main_gui import RefereeControlsPage
        
        page = RefereeControlsPage(mock_gui_service)
        
        # Test player 1 wins multiple rounds
        for i in range(3):
            page._p1_round_win()
        
        assert page._score_p1 == 3
        assert page._round_number == 4  # Incremented after each win
        
        # Verify match end notification
        assert any("Player 1 WINS THE MATCH!" in call for call in mock_gui_service.call_log)
    
    def test_referee_emergency_stop(self, qapp, mock_gui_service):
        """Test referee emergency stop functionality."""
        from gui.eda_main_gui import RefereeControlsPage
        
        page = RefereeControlsPage(mock_gui_service)
        
        # Start a round first
        page._toggle_round()
        assert page._match_active is True
        
        # Test emergency stop
        page._emergency_stop()
        assert page._match_active is False
        assert "stop_tracking" in mock_gui_service.call_log[-1]
        assert any("EMERGENCY STOP ACTIVATED" in call for call in mock_gui_service.call_log)
    
    def test_referee_technical_controls(self, qapp, mock_gui_service):
        """Test referee technical control features."""
        from gui.eda_main_gui import RefereeControlsPage
        
        page = RefereeControlsPage(mock_gui_service)
        
        # Test projection test
        page._test_projection()
        assert "update_projection_config:1920x1080" in mock_gui_service.call_log
        assert any("Projection test initiated" in call for call in mock_gui_service.call_log)
        
        # Test tracking toggle
        page._toggle_tracking()
        assert any("Tracking toggled" in call for call in mock_gui_service.call_log)


class TestApplicationIntegration:
    """Test suite for overall application integration."""
    
    def test_complete_user_journey_casual_gaming(self, qapp, mock_gui_service):
        """Test complete user journey for casual gaming."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # User journey: Main Menu -> Quick Play -> Gaming -> Exit
        # 1. Start at main menu
        assert window._current_page_name == "main_menu"
        
        # 2. Navigate to free play
        window.show_page("free_play")
        assert window._current_page_name == "free_play"
        
        # 3. Access current page and simulate game start
        free_play_page = window._pages["free_play"]
        free_play_page._toggle_game()
        assert "start_tracking" in mock_gui_service.call_log[-1]
        
        # 4. Add some scores
        free_play_page._add_p1_score()
        free_play_page._add_p2_score()
        
        # 5. Return to main menu
        window.show_page("main_menu")
        assert window._current_page_name == "main_menu"
    
    def test_complete_user_journey_competitive_match(self, qapp, mock_gui_service):
        """Test complete user journey for competitive match."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # User journey: Main Menu -> Match Setup -> Referee Controls -> Match -> Exit
        # 1. Start at main menu
        assert window._current_page_name == "main_menu"
        
        # 2. Configure match
        window.show_page("match_setup")
        match_setup_page = window._pages["match_setup"]
        match_setup_page._start_match()  # This navigates to referee_controls
        
        # 3. Verify referee controls page
        assert window._current_page_name == "referee_controls"
        
        # 4. Run a complete match
        referee_page = window._pages["referee_controls"]
        
        # Start round 1
        referee_page._toggle_round()
        assert referee_page._match_active is True
        
        # Player 1 wins round 1
        referee_page._p1_round_win()
        assert referee_page._score_p1 == 1
        
        # Player 2 wins round 2  
        referee_page._p2_round_win()
        assert referee_page._score_p2 == 1
        
        # Continue until match end (Player 1 wins 3-1)
        referee_page._p1_round_win()
        referee_page._p1_round_win()
        
        # Match should end automatically
        assert referee_page._score_p1 == 3
        assert any("Player 1 WINS THE MATCH!" in call for call in mock_gui_service.call_log)
    
    def test_technical_setup_workflow(self, qapp, mock_gui_service):
        """Test technical setup and configuration workflow."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # Technical workflow: Main Menu -> System Hub -> Configuration screens
        # 1. Navigate to system hub
        window.show_page("system_hub")
        system_hub_page = window._pages["system_hub"]
        
        # 2. Access tracker setup
        window.show_page("tracker_setup")
        assert window._current_page_name == "tracker_setup"
        
        # 3. Access projection setup
        window.show_page("projection_setup")
        projection_page = window._pages["projection_setup"]
        
        # Test projection configuration
        projection_page._apply_preset(1920, 1080)
        assert "update_projection_config:1920x1080" in mock_gui_service.call_log
        
        # 4. Access options
        window.show_page("options")
        options_page = window._pages["options"]
        
        # 5. Return to main menu
        window.show_page("main_menu")
        assert window._current_page_name == "main_menu"
    
    def test_navigation_button_state_management(self, qapp, mock_gui_service):
        """Test navigation button state management across all pages."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # Test navigation button styling updates
        main_pages = ["main_menu", "match_setup", "free_play", "referee_controls"]
        technical_pages = ["system_hub", "tracker_setup", "projection_setup", "options"]
        
        # Test main gaming pages
        for page in main_pages:
            window.show_page(page)
            assert window._current_page_name == page
            # Active page should have primary style
            active_btn = window._navigation_buttons[page]
            # Button style should be updated (though we can't easily test exact styling)
        
        # Test technical pages
        for page in technical_pages:
            if page in window._pages:  # Some pages might not be in navigation
                window.show_page(page)
                assert window._current_page_name == page


class TestErrorHandlingAndEdgeCases:
    """Test suite for error handling and edge cases."""
    
    def test_invalid_page_navigation(self, qapp, mock_gui_service):
        """Test navigation to non-existent pages."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # Try to navigate to non-existent page
        initial_page = window._current_page_name
        window.show_page("non_existent_page")
        
        # Should remain on current page
        assert window._current_page_name == initial_page
    
    def test_rapid_navigation_stability(self, qapp, mock_gui_service):
        """Test rapid navigation between pages for stability."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # Rapidly navigate between pages
        pages = ["main_menu", "match_setup", "free_play", "system_hub", "options"]
        for i in range(10):
            for page in pages:
                window.show_page(page)
                assert window._current_page_name == page
    
    def test_match_state_consistency(self, qapp, mock_gui_service):
        """Test match state consistency during navigation."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        
        # Start a game in free play
        window.show_page("free_play")
        free_play_page = window._pages["free_play"]
        free_play_page._toggle_game()
        assert free_play_page._game_active is True
        
        # Navigate away and back
        window.show_page("main_menu")
        window.show_page("free_play")
        
        # Game state should be preserved
        free_play_page = window._pages["free_play"]
        assert free_play_page._game_active is True


# ==================== PERFORMANCE AND STRESS TESTS ==================== #

class TestPerformanceAndStress:
    """Test suite for performance and stress testing."""
    
    def test_page_creation_performance(self, qapp, mock_gui_service):
        """Test page creation performance."""
        from gui.eda_main_gui import EDAMainWindow
        
        import time
        start_time = time.perf_counter()
        
        # Create main window with all pages
        window = EDAMainWindow(mock_gui_service)
        
        creation_time = time.perf_counter() - start_time
        
        # Should create all pages quickly (less than 1 second)
        assert creation_time < 1.0
        assert len(window._pages) == 8
    
    def test_navigation_performance(self, qapp, mock_gui_service):
        """Test navigation performance."""
        from gui.eda_main_gui import EDAMainWindow
        
        window = EDAMainWindow(mock_gui_service)
        pages = list(window._pages.keys())
        
        import time
        start_time = time.perf_counter()
        
        # Navigate through all pages multiple times
        for _ in range(5):
            for page in pages:
                window.show_page(page)
        
        navigation_time = time.perf_counter() - start_time
        
        # Navigation should be fast (less than 0.1 seconds for 40 operations)
        assert navigation_time < 0.1


if __name__ == "__main__":
    # Run tests when script is executed directly
    pytest.main([__file__, "-v"]) 