"""
Integration tests for CORE-02: Projection Client Adapter Dependency Injection.

This test suite verifies that the real BeysionUnityAdapter is properly
integrated into the dependency injection system and functions correctly
with the ProjectionService.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock

from core.event_broker import EventBroker, DependencyContainer
from core.interfaces import IProjectionAdapter, ITrackerHardware
from adapters.beysion_unity_adapter import BeysionUnityAdapter
from services.projection_service import ProjectionService
from main_eda import BBanTrackerApplication


class TestCORE02Integration:
    """Test suite for CORE-02 implementation."""
    
    def setup_method(self):
        """Set up test environment for each test."""
        self.test_config = {
            'dev_mode': True,
            'cam_src': 0,
            'unity_path': '/test/path/unity.exe'
        }
    
    def teardown_method(self):
        """Clean up after each test."""
        pass
    
    def test_real_adapter_injection(self):
        """Test that real BeysionUnityAdapter is injected, not placeholder."""
        # Create application
        app = BBanTrackerApplication(self.test_config)
        
        # Mock the hardware to avoid RealSense dependency
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            # Mock the adapter's platform-specific operations
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc') as mock_ipc:
                    mock_ipc.SharedMemory.return_value = Mock()
                    
                    # Initialize application
                    success = app.initialize()
                    
                    # Verify initialization succeeded
                    assert success, "Application should initialize successfully"
                    
                    # Verify the real adapter is registered
                    projection_adapter = app.container.resolve(IProjectionAdapter)
                    assert isinstance(projection_adapter, BeysionUnityAdapter), \
                        f"Expected BeysionUnityAdapter, got {type(projection_adapter)}"
                    
                    # Verify it's not the old placeholder
                    assert hasattr(projection_adapter, '_shared_memory_name'), \
                        "Real adapter should have shared memory attributes"
                    
                    # Clean up
                    app.shutdown()
    
    def test_adapter_initialization_config(self):
        """Test adapter initializes with proper configuration."""
        # Create application with specific config
        app = BBanTrackerApplication(self.test_config)
        
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    app.initialize()
                    
                    # Get the adapter and verify configuration
                    adapter = app.projection_adapter
                    assert adapter._shared_memory_name == "beysion_tracker_data"
                    assert adapter._shared_memory_size == 1024*1024  # 1MB
                    assert adapter._unity_executable_path == '/test/path/unity.exe'
                    
                    app.shutdown()
    
    def test_projection_service_communication(self):
        """Test ProjectionService can communicate through real adapter."""
        # Create event broker
        event_broker = EventBroker(max_workers=2, max_queue_size=100)
        
        # Create mock adapter that implements the interface
        mock_adapter = Mock(spec=IProjectionAdapter)
        mock_adapter.connect.return_value = True
        mock_adapter.is_connected.return_value = True
        mock_adapter.send_tracking_data.return_value = True
        mock_adapter.send_projection_config.return_value = True
        mock_adapter.receive_commands.return_value = []
        mock_adapter.get_client_info.return_value = {'status': 'connected'}
        
        # Create projection service with real interface
        projection_service = ProjectionService(event_broker, mock_adapter)
        
        try:
            # Start the service
            projection_service.start()
            assert projection_service.is_running()
            
            # Verify adapter connection is attempted
            time.sleep(0.1)  # Let service initialize
            mock_adapter.connect.assert_called_once()
            
            # Test sending projection config
            from core.events import ProjectionConfigUpdated
            config_event = ProjectionConfigUpdated(width=1920, height=1080)
            event_broker.publish(config_event)
            
            # Wait for event processing
            time.sleep(0.1)
            mock_adapter.send_projection_config.assert_called_with(1920, 1080)
            
        finally:
            projection_service.stop()
            event_broker.shutdown()
    
    def test_shared_memory_creation_mocked(self):
        """Test shared memory setup works (mocked for CI)."""
        # Test with Windows platform mock
        with patch('adapters.beysion_unity_adapter.sys.platform', 'win32'):
            with patch('adapters.beysion_unity_adapter.tempfile') as mock_tempfile:
                with patch('adapters.beysion_unity_adapter.mmap') as mock_mmap:
                    # Set up mocks
                    mock_file = Mock()
                    mock_file.fileno.return_value = 123
                    mock_tempfile.NamedTemporaryFile.return_value = mock_file
                    mock_mmap.mmap.return_value = Mock()
                    
                    # Create adapter
                    adapter = BeysionUnityAdapter(
                        shared_memory_name="test_memory",
                        shared_memory_size=64*1024
                    )
                    
                    # Test connection (which creates shared memory)
                    result = adapter.connect()
                    
                    # Verify mocks were called correctly
                    mock_tempfile.NamedTemporaryFile.assert_called_once()
                    mock_mmap.mmap.assert_called()
                    
                    # Clean up
                    adapter.disconnect()
    
    def test_adapter_error_handling(self):
        """Test adapter handles initialization errors gracefully."""
        # Test with invalid configuration
        adapter = BeysionUnityAdapter(
            shared_memory_name="test",
            shared_memory_size=-1  # Invalid size
        )
        
        # Connection should fail gracefully
        result = adapter.connect()
        assert not result, "Connection should fail with invalid config"
        assert not adapter.is_connected()
    
    def test_event_flow_integration(self):
        """Test complete event flow from tracking to projection."""
        event_broker = EventBroker(max_workers=2, max_queue_size=100)
        
        # Create mock adapter
        mock_adapter = Mock(spec=IProjectionAdapter)
        mock_adapter.connect.return_value = True
        mock_adapter.is_connected.return_value = True
        mock_adapter.send_tracking_data.return_value = True
        
        # Create projection service
        projection_service = ProjectionService(event_broker, mock_adapter)
        
        try:
            projection_service.start()
            time.sleep(0.1)  # Let service start
            
            # Simulate tracking data event
            from core.events import TrackingDataUpdated
            tracking_event = TrackingDataUpdated(
                frame_id=123,
                timestamp=time.time(),
                beys=[],
                hits=[]
            )
            
            event_broker.publish(tracking_event)
            time.sleep(0.1)  # Let event process
            
            # Verify adapter received the data
            mock_adapter.send_tracking_data.assert_called_with(123, [], [])
            
        finally:
            projection_service.stop()
            event_broker.shutdown()
    
    def test_di_container_registration(self):
        """Test dependency injection container properly registers the adapter."""
        container = DependencyContainer()
        
        # Create real adapter instance
        adapter = BeysionUnityAdapter()
        
        # Register in container
        container.register_singleton(IProjectionAdapter, adapter)
        
        # Verify registration
        assert container.is_registered(IProjectionAdapter)
        
        # Verify resolution returns the same instance
        resolved = container.resolve(IProjectionAdapter)
        assert resolved is adapter
        assert isinstance(resolved, BeysionUnityAdapter)
    
    def test_application_full_integration(self):
        """Test full application integration with real adapter."""
        app = BBanTrackerApplication(self.test_config)
        
        with patch('main_eda.RealSenseD400_HAL') as mock_hardware:
            mock_hardware.return_value = Mock()
            
            # Mock adapter's platform dependencies
            with patch('adapters.beysion_unity_adapter.sys.platform', 'linux'):
                with patch('adapters.beysion_unity_adapter.posix_ipc'):
                    
                    # Initialize application
                    success = app.initialize()
                    assert success
                    
                    # Verify all services are running
                    assert app.tracking_service.is_running()
                    assert app.gui_service.is_running()
                    assert app.projection_service.is_running()
                    
                    # Verify projection service has real adapter
                    projection_adapter = app.container.resolve(IProjectionAdapter)
                    assert isinstance(projection_adapter, BeysionUnityAdapter)
                    
                    # Test graceful shutdown
                    app.shutdown()
                    
                    # Verify services stopped
                    assert not app.tracking_service.is_running()
                    assert not app.gui_service.is_running()
                    assert not app.projection_service.is_running()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 