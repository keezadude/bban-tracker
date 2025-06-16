"""
Integration tests for HMI-SHELL: Main Application Shell Integration.

This test suite verifies that the GUI shell properly integrates with the main
EDA application and that both console and GUI modes work correctly.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock

from main_eda import BBanTrackerApplication


class TestHMIShellIntegration:
    """Test suite for HMI-SHELL implementation."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.test_config = {
            'dev_mode': True,
            'cam_src': 0,
            'unity_path': '/test/path/unity.exe',
            'demo_time': 0
        }
    
    def teardown_method(self):
        """Clean up after each test."""
        pass
    
    def test_application_supports_both_modes(self):
        """Test that application supports both GUI and console modes."""
        app = BBanTrackerApplication(self.test_config)
        
        # Test that run method accepts gui_mode parameter
        assert hasattr(app, 'run')
        
        # Check method signature supports gui_mode
        import inspect
        sig = inspect.signature(app.run)
        assert 'gui_mode' in sig.parameters
        
        # Check default value
        default_value = sig.parameters['gui_mode'].default
        assert default_value is True  # GUI mode is default
    
    def test_console_mode_execution(self):
        """Test console mode runs without GUI dependencies."""
        app = BBanTrackerApplication(self.test_config)
        
        # Mock all dependencies
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    
                    # Initialize application
                    success = app.initialize()
                    assert success
                    
                    # Test console mode in a separate thread with timeout
                    app.config['demo_time'] = 1  # 1 second demo
                    
                    def run_console():
                        app._run_console_mode()
                    
                    console_thread = threading.Thread(target=run_console)
                    console_thread.start()
                    console_thread.join(timeout=3.0)  # Max 3 seconds
                    
                    # Verify thread completed
                    assert not console_thread.is_alive()
                    
                    app.shutdown()
    
    def test_gui_mode_fallback_to_console(self):
        """Test GUI mode falls back to console when GUI dependencies unavailable."""
        app = BBanTrackerApplication(self.test_config)
        
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    
                    app.initialize()
                    
                    # Mock GUI import to fail
                    with patch('main_eda.BBanTrackerApplication._run_console_mode') as mock_console:
                        with patch('builtins.__import__', side_effect=ImportError("No PySide6")):
                            
                            # Try to run GUI mode
                            app._run_gui_mode()
                            
                            # Should fall back to console mode
                            mock_console.assert_called_once()
                    
                    app.shutdown()
    
    def test_gui_mode_with_mock_gui(self):
        """Test GUI mode creates and runs GUI application."""
        app = BBanTrackerApplication(self.test_config)
        
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    
                    app.initialize()
                    
                    # Mock GUI application
                    mock_gui_app = Mock()
                    mock_gui_app.exec.return_value = 0  # Successful exit
                    
                    with patch('gui.eda_main_gui.create_eda_gui_application') as mock_create_gui:
                        mock_create_gui.return_value = mock_gui_app
                        
                        # Run GUI mode
                        app._run_gui_mode()
                        
                        # Verify GUI was created and executed
                        mock_create_gui.assert_called_once_with(app.gui_service)
                        mock_gui_app.exec.assert_called_once()
                    
                    app.shutdown()
    
    def test_signal_handling_in_gui_mode(self):
        """Test signal handling works correctly in GUI mode."""
        app = BBanTrackerApplication(self.test_config)
        
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    
                    app.initialize()
                    
                    # Test signal handler registration
                    with patch('signal.signal') as mock_signal:
                        
                        # Mock GUI components
                        mock_gui_app = Mock()
                        mock_gui_app.exec.return_value = 0
                        
                        with patch('gui.eda_main_gui.create_eda_gui_application') as mock_create_gui:
                            mock_create_gui.return_value = mock_gui_app
                            
                            # Start application in a thread to test signal handling
                            def run_app():
                                app.run(gui_mode=True)
                            
                            app_thread = threading.Thread(target=run_app)
                            app_thread.start()
                            
                            # Give it a moment to set up
                            time.sleep(0.1)
                            
                            # Trigger shutdown
                            app.shutdown_requested = True
                            
                            # Wait for completion
                            app_thread.join(timeout=2.0)
                            
                            # Verify signal handlers were registered
                            assert mock_signal.call_count >= 2  # SIGINT and SIGTERM
    
    def test_eda_demonstration_in_gui_mode(self):
        """Test EDA pattern demonstration runs in GUI mode."""
        app = BBanTrackerApplication(self.test_config)
        
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    
                    app.initialize()
                    
                    # Mock GUI service methods to track EDA demonstration
                    app.gui_service.request_start_tracking = Mock()
                    app.gui_service.update_tracker_settings = Mock()
                    app.gui_service.update_projection_config = Mock()
                    
                    # Mock GUI components
                    mock_gui_app = Mock()
                    mock_gui_app.exec.return_value = 0
                    
                    with patch('gui.eda_main_gui.create_eda_gui_application') as mock_create_gui:
                        mock_create_gui.return_value = mock_gui_app
                        
                        # Run GUI mode
                        app._run_gui_mode()
                        
                        # Verify EDA demonstration was called
                        app.gui_service.request_start_tracking.assert_called()
                        app.gui_service.update_tracker_settings.assert_called()
                        app.gui_service.update_projection_config.assert_called()
                    
                    app.shutdown()
    
    def test_gui_service_integration(self):
        """Test GUI service is properly passed to GUI application."""
        app = BBanTrackerApplication(self.test_config)
        
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    
                    app.initialize()
                    
                    # Verify GUI service exists
                    assert app.gui_service is not None
                    assert app.gui_service.is_running()
                    
                    # Mock GUI application creation
                    with patch('gui.eda_main_gui.create_eda_gui_application') as mock_create_gui:
                        mock_gui_app = Mock()
                        mock_gui_app.exec.return_value = 0
                        mock_create_gui.return_value = mock_gui_app
                        
                        # Run GUI mode
                        app._run_gui_mode()
                        
                        # Verify GUI service was passed to GUI application
                        mock_create_gui.assert_called_once_with(app.gui_service)
                    
                    app.shutdown()
    
    def test_command_line_argument_parsing(self):
        """Test command line arguments for GUI/console mode selection."""
        from main_eda import parse_arguments
        import sys
        
        # Test default (GUI mode)
        original_argv = sys.argv
        try:
            sys.argv = ['main_eda.py']
            args = parse_arguments()
            assert not args.console_mode  # Default is GUI mode
            
            # Test console mode flag
            sys.argv = ['main_eda.py', '--console-mode']
            args = parse_arguments()
            assert args.console_mode
            
            # Test other arguments still work
            sys.argv = ['main_eda.py', '--dev', '--unity-path', '/test/unity.exe']
            args = parse_arguments()
            assert args.dev
            assert args.unity_path == '/test/unity.exe'
            assert not args.console_mode  # Should be default
            
        finally:
            sys.argv = original_argv
    
    def test_config_integration(self):
        """Test configuration is properly passed through to GUI mode."""
        config = {
            'dev_mode': True,
            'cam_src': 1,
            'unity_path': '/custom/unity/path',
            'demo_time': 10
        }
        
        app = BBanTrackerApplication(config)
        
        # Verify config is stored
        assert app.config == config
        
        # Config should be accessible to all modes
        assert app.config['dev_mode'] is True
        assert app.config['cam_src'] == 1
        assert app.config['unity_path'] == '/custom/unity/path'
    
    def test_error_handling_in_gui_mode(self):
        """Test error handling in GUI mode."""
        app = BBanTrackerApplication(self.test_config)
        
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    
                    app.initialize()
                    
                    # Mock GUI to raise an exception
                    with patch('gui.eda_main_gui.create_eda_gui_application') as mock_create_gui:
                        mock_create_gui.side_effect = Exception("GUI creation failed")
                        
                        # Should handle exception gracefully
                        try:
                            app._run_gui_mode()
                        except Exception:
                            pytest.fail("GUI mode should handle exceptions gracefully")
                    
                    app.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 