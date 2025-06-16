"""
Unit tests for RealSenseD400_HAL hardware abstraction layer.

These tests verify the hardware abstraction functionality including
initialization, frame reading, option management, and performance monitoring.
Tests use mocking to avoid dependencies on actual hardware.
"""

import pytest
import numpy as np
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from hardware.realsense_d400_hal import RealSenseD400_HAL
from core.interfaces import ITrackerHardware


class TestRealSenseD400_HAL:
    """Test suite for RealSenseD400_HAL implementation."""
    
    def setup_method(self):
        """Set up fresh HAL instance for each test."""
        self.hal = RealSenseD400_HAL()
        self.test_frame = np.zeros((360, 640), dtype=np.uint8)  # Mock frame data
    
    def teardown_method(self):
        """Clean up HAL resources after each test."""
        if hasattr(self, 'hal') and self.hal.is_connected():
            self.hal.stop_stream()
    
    def test_implements_interface(self):
        """Test that HAL correctly implements ITrackerHardware interface."""
        assert isinstance(self.hal, ITrackerHardware)
        
        # Verify all required methods exist
        required_methods = [
            'initialize', 'start_stream', 'stop_stream', 'read_next_frame',
            'get_latest_frame', 'set_option', 'get_option', 'get_supported_options',
            'get_hardware_info', 'is_connected'
        ]
        
        for method in required_methods:
            assert hasattr(self.hal, method), f"Missing required method: {method}"
            assert callable(getattr(self.hal, method)), f"Method {method} is not callable"
    
    def test_initial_state(self):
        """Test HAL initial state before initialization."""
        assert not self.hal.is_connected()
        assert self.hal.get_latest_frame() is None
        assert self.hal.read_next_frame() is None
        assert not self.hal.set_option('test_option', 123)
        
        info = self.hal.get_hardware_info()
        assert info['hardware_type'] == 'unknown'
        assert not info['connected']
    
    @patch('hardware.realsense_d400_hal.RealsenseStream')
    def test_initialize_realsense_success(self, mock_realsense_class):
        """Test successful RealSense initialization."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_realsense_class.return_value.start.return_value = mock_camera
        
        # Test initialization
        config = {'dev_mode': False}
        result = self.hal.initialize(config)
        
        assert result is True
        assert self.hal.is_connected()
        assert self.hal._hardware_type == 'realsense'
        
        # Verify camera was started
        mock_realsense_class.assert_called_once()
        mock_camera.readNext.assert_called_once()
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_initialize_webcam_dev_mode(self, mock_webcam_class):
        """Test webcam initialization in dev mode."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Test initialization
        config = {'dev_mode': True, 'cam_src': 1}
        result = self.hal.initialize(config)
        
        assert result is True
        assert self.hal.is_connected()
        assert self.hal._hardware_type == 'webcam'
        
        # Verify webcam was initialized with correct source
        mock_webcam_class.assert_called_once_with(src=1)
    
    @patch('hardware.realsense_d400_hal.VideoFileStream')
    def test_initialize_video_file(self, mock_video_class):
        """Test video file initialization."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_video_class.return_value.start.return_value = mock_camera
        
        # Create a temporary file path for testing
        test_video_path = "/tmp/test_video.mp4"
        
        with patch('pathlib.Path.exists', return_value=True):
            config = {'video_path': test_video_path}
            result = self.hal.initialize(config)
        
        assert result is True
        assert self.hal.is_connected()
        assert self.hal._hardware_type == 'video'
        
        mock_video_class.assert_called_once_with(test_video_path)
    
    @patch('hardware.realsense_d400_hal.RealsenseStream')
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_initialize_realsense_fallback(self, mock_webcam_class, mock_realsense_class):
        """Test fallback to webcam when RealSense fails."""
        # Setup mocks - RealSense fails, webcam succeeds
        mock_realsense_class.side_effect = Exception("RealSense not available")
        
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Test initialization
        config = {'dev_mode': False}
        result = self.hal.initialize(config)
        
        assert result is True
        assert self.hal.is_connected()
        assert self.hal._hardware_type == 'webcam'
        
        # Verify fallback occurred
        mock_realsense_class.assert_called_once()
        mock_webcam_class.assert_called_once_with(src=0)
    
    def test_initialize_video_file_not_found(self):
        """Test initialization failure when video file doesn't exist."""
        config = {'video_path': '/nonexistent/video.mp4'}
        result = self.hal.initialize(config)
        
        assert result is False
        assert not self.hal.is_connected()
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_initialize_camera_failure(self, mock_webcam_class):
        """Test initialization failure when camera can't produce frames."""
        # Setup mock that fails to produce frames
        mock_camera = Mock()
        mock_camera.readNext.return_value = None
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        config = {'dev_mode': True}
        result = self.hal.initialize(config)
        
        assert result is False
        assert not self.hal.is_connected()
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_frame_reading(self, mock_webcam_class):
        """Test frame reading functionality."""
        # Setup mock
        mock_camera = Mock()
        test_frames = [self.test_frame, self.test_frame + 1, self.test_frame + 2]
        mock_camera.readNext.side_effect = test_frames
        mock_camera.read.return_value = self.test_frame
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        config = {'dev_mode': True}
        self.hal.initialize(config)
        
        # Test read_next_frame (blocking)
        frame1 = self.hal.read_next_frame()
        frame2 = self.hal.read_next_frame()
        
        assert np.array_equal(frame1, test_frames[1])  # Skip first frame used in init
        assert np.array_equal(frame2, test_frames[2])
        
        # Test get_latest_frame (non-blocking)
        latest_frame = self.hal.get_latest_frame()
        assert np.array_equal(latest_frame, self.test_frame)
        
        # Verify performance metrics are tracked
        metrics = self.hal.get_performance_metrics()
        assert metrics['total_frames_read'] == 2
        assert len(metrics['frame_read_times']) == 2
    
    @patch('hardware.realsense_d400_hal.RealsenseStream')
    def test_realsense_option_management(self, mock_realsense_class):
        """Test RealSense option setting and getting."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_camera.set_option = Mock()
        mock_camera.get_option = Mock(return_value=150.0)
        mock_realsense_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        config = {'dev_mode': False}
        self.hal.initialize(config)
        
        # Test setting options
        result = self.hal.set_option('laser_power', 150)
        assert result is True
        mock_camera.set_option.assert_called_once()
        
        # Test getting options
        value = self.hal.get_option('laser_power')
        assert value == 150.0
        mock_camera.get_option.assert_called_once()
        
        # Test unsupported option
        result = self.hal.set_option('unsupported_option', 123)
        assert result is False
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_webcam_option_limitations(self, mock_webcam_class):
        """Test that webcam options are properly limited."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        config = {'dev_mode': True}
        self.hal.initialize(config)
        
        # Test that webcam doesn't support RealSense options
        result = self.hal.set_option('laser_power', 150)
        assert result is False
        
        value = self.hal.get_option('exposure')
        assert value is None
        
        # Test supported options
        options = self.hal.get_supported_options()
        assert 'hardware_type' in options
        assert options['hardware_type']['range'] == ['webcam']
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_start_stop_stream(self, mock_webcam_class):
        """Test stream management."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_camera.read.return_value = self.test_frame
        mock_camera.close = Mock()
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        config = {'dev_mode': True}
        self.hal.initialize(config)
        
        # Test start_stream (should verify existing stream)
        result = self.hal.start_stream()
        assert result is True
        
        # Test stop_stream
        self.hal.stop_stream()
        assert not self.hal.is_connected()
        mock_camera.close.assert_called_once()
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_hardware_info(self, mock_webcam_class):
        """Test hardware information retrieval."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        start_time = time.perf_counter()
        config = {'dev_mode': True}
        self.hal.initialize(config)
        init_time = time.perf_counter() - start_time
        
        # Read some frames to generate metrics
        self.hal.read_next_frame()
        self.hal.read_next_frame()
        
        # Test hardware info
        info = self.hal.get_hardware_info()
        
        assert info['hardware_type'] == 'webcam'
        assert info['connected'] is True
        assert info['total_frames_read'] == 2
        assert info['initialization_time_ms'] > 0
        assert info['initialization_time_ms'] < init_time * 1000 + 100  # Allow some margin
        assert 'average_frame_read_time_ms' in info
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_error_handling(self, mock_webcam_class):
        """Test error handling and recovery."""
        # Setup mock that can fail
        mock_camera = Mock()
        mock_camera.readNext.side_effect = [self.test_frame, Exception("Camera error"), self.test_frame]
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        config = {'dev_mode': True}
        self.hal.initialize(config)
        
        # Test error handling in frame reading
        frame1 = self.hal.read_next_frame()
        assert frame1 is None  # Should return None on error
        
        # Test that HAL continues to work after error
        frame2 = self.hal.read_next_frame()
        assert np.array_equal(frame2, self.test_frame)
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_performance_metrics(self, mock_webcam_class):
        """Test performance monitoring functionality."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = self.test_frame
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        config = {'dev_mode': True}
        self.hal.initialize(config)
        
        # Read frames to generate metrics
        for _ in range(5):
            self.hal.read_next_frame()
        
        # Get performance metrics
        metrics = self.hal.get_performance_metrics()
        
        assert metrics['total_frames_read'] == 5
        assert len(metrics['frame_read_times']) == 5
        assert 'frame_read_stats' in metrics
        
        stats = metrics['frame_read_stats']
        assert stats['count'] == 5
        assert stats['average_ms'] >= 0
        assert stats['min_ms'] >= 0
        assert stats['max_ms'] >= stats['min_ms']
        
        # Test reset
        self.hal.reset_performance_metrics()
        metrics_after_reset = self.hal.get_performance_metrics()
        assert metrics_after_reset['total_frames_read'] == 0
        assert len(metrics_after_reset['frame_read_times']) == 0
    
    def test_uninitialized_hal_behavior(self):
        """Test HAL behavior when not initialized."""
        # All operations should fail gracefully
        assert not self.hal.start_stream()
        assert self.hal.read_next_frame() is None
        assert self.hal.get_latest_frame() is None
        assert not self.hal.set_option('test', 123)
        assert self.hal.get_option('test') is None
        assert not self.hal.is_connected()
        
        # Hardware info should still be available
        info = self.hal.get_hardware_info()
        assert info['hardware_type'] == 'unknown'
        assert not info['connected']


# ==================== PERFORMANCE TESTS ==================== #

class TestRealSenseHALPerformance:
    """Performance-focused tests for RealSenseD400_HAL."""
    
    def setup_method(self):
        """Set up HAL for performance testing."""
        self.hal = RealSenseD400_HAL()
    
    def teardown_method(self):
        """Clean up HAL resources."""
        if hasattr(self, 'hal') and self.hal.is_connected():
            self.hal.stop_stream()
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_frame_read_latency(self, mock_webcam_class):
        """Test frame reading latency meets performance requirements."""
        # Setup mock
        mock_camera = Mock()
        test_frame = np.zeros((360, 640), dtype=np.uint8)
        mock_camera.readNext.return_value = test_frame
        mock_camera.read.return_value = test_frame
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        config = {'dev_mode': True}
        self.hal.initialize(config)
        
        # Measure frame read performance
        num_frames = 100
        start_time = time.perf_counter()
        
        for _ in range(num_frames):
            frame = self.hal.read_next_frame()
            assert frame is not None
        
        total_time = time.perf_counter() - start_time
        avg_frame_time = total_time / num_frames
        
        # Verify performance requirements
        assert avg_frame_time < 0.001  # < 1ms average (target from blueprint)
        
        print(f"Frame read performance: {avg_frame_time*1000:.3f}ms average")
    
    @patch('hardware.realsense_d400_hal.RealsenseStream')
    def test_option_setting_latency(self, mock_realsense_class):
        """Test option setting latency meets requirements."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = np.zeros((360, 640), dtype=np.uint8)
        mock_camera.set_option = Mock()
        mock_realsense_class.return_value.start.return_value = mock_camera
        
        # Initialize HAL
        config = {'dev_mode': False}
        self.hal.initialize(config)
        
        # Measure option setting performance
        num_operations = 50
        start_time = time.perf_counter()
        
        for i in range(num_operations):
            result = self.hal.set_option('laser_power', 100 + i)
            assert result is True
        
        total_time = time.perf_counter() - start_time
        avg_option_time = total_time / num_operations
        
        # Verify performance requirements
        assert avg_option_time < 0.01  # < 10ms average (target from blueprint)
        
        # Check internal performance metrics
        metrics = self.hal.get_performance_metrics()
        assert metrics['option_set_stats']['average_ms'] < 10.0
        
        print(f"Option setting performance: {avg_option_time*1000:.3f}ms average")
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_initialization_time(self, mock_webcam_class):
        """Test initialization time meets requirements."""
        # Setup mock
        mock_camera = Mock()
        mock_camera.readNext.return_value = np.zeros((360, 640), dtype=np.uint8)
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Measure initialization time
        config = {'dev_mode': True}
        start_time = time.perf_counter()
        result = self.hal.initialize(config)
        init_time = time.perf_counter() - start_time
        
        assert result is True
        assert init_time < 0.5  # < 500ms (target from blueprint)
        
        # Verify internal tracking
        info = self.hal.get_hardware_info()
        assert info['initialization_time_ms'] < 500
        
        print(f"Initialization time: {init_time*1000:.1f}ms")


# ==================== INTEGRATION TESTS ==================== #

class TestRealSenseHALIntegration:
    """Integration tests for HAL with other system components."""
    
    @patch('hardware.realsense_d400_hal.WebcamVideoStream')
    def test_hal_with_tracking_service_integration(self, mock_webcam_class):
        """Test HAL integration with TrackingService."""
        from services.tracking_service import TrackingService
        from core.event_broker import EventBroker
        
        # Setup mocks
        mock_camera = Mock()
        test_frame = np.zeros((360, 640), dtype=np.uint8)
        mock_camera.readNext.return_value = test_frame
        mock_webcam_class.return_value.start.return_value = mock_camera
        
        # Create components
        event_broker = EventBroker()
        hal = RealSenseD400_HAL()
        tracking_service = TrackingService(event_broker, hal)
        
        try:
            # Test service lifecycle
            tracking_service.start()
            assert tracking_service.is_running()
            
            # Test that service can get hardware info through HAL
            camera_info = tracking_service.get_camera_info()
            assert 'status' in camera_info
            
        finally:
            tracking_service.stop()
            event_broker.shutdown()
    
    def test_dependency_injection_pattern(self):
        """Test that HAL properly supports dependency injection."""
        from core.event_broker import DependencyContainer
        
        # Test DI container registration
        container = DependencyContainer()
        hal_instance = RealSenseD400_HAL()
        
        container.register_singleton(ITrackerHardware, hal_instance)
        
        # Test resolution
        resolved_hal = container.resolve(ITrackerHardware)
        assert resolved_hal is hal_instance
        assert isinstance(resolved_hal, ITrackerHardware) 