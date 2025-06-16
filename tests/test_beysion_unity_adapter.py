"""
Unit tests for BeysionUnityAdapter implementation.

These tests verify the projection client adapter functionality including
shared memory protocol, Unity client communication, and performance characteristics.
Tests use mocking to avoid dependencies on actual Unity client or shared memory.
"""

import pytest
import time
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock, mock_open
from dataclasses import dataclass

from adapters.beysion_unity_adapter import BeysionUnityAdapter, AdapterPerformanceMetrics
from adapters.shared_memory_protocol import (
    SharedMemoryFrame, BeyData, HitData, ProjectionConfig, UnityCommand,
    CommandType, ProtocolSerializer, SharedMemoryHeader
)
from core.interfaces import IProjectionAdapter


class TestAdapterPerformanceMetrics:
    """Test suite for AdapterPerformanceMetrics."""
    
    def test_initialization(self):
        """Test metrics initialization."""
        metrics = AdapterPerformanceMetrics()
        assert metrics.frames_sent == 0
        assert metrics.serialization_times == []
        assert metrics.write_times == []
        assert metrics.total_bytes_written == 0
        assert metrics.connection_attempts == 0
        assert metrics.last_heartbeat == 0.0
    
    def test_add_serialization_time(self):
        """Test adding serialization time measurements."""
        metrics = AdapterPerformanceMetrics()
        
        # Add some measurements
        metrics.add_serialization_time(1.5)
        metrics.add_serialization_time(2.0)
        metrics.add_serialization_time(1.8)
        
        assert len(metrics.serialization_times) == 3
        assert metrics.get_avg_serialization_time() == pytest.approx(1.77, abs=0.01)
    
    def test_serialization_time_rolling_window(self):
        """Test that serialization times maintain rolling window of 100."""
        metrics = AdapterPerformanceMetrics()
        
        # Add 150 measurements
        for i in range(150):
            metrics.add_serialization_time(float(i))
        
        # Should only keep the last 100
        assert len(metrics.serialization_times) == 100
        assert metrics.serialization_times[0] == 50.0  # First of the last 100
        assert metrics.serialization_times[-1] == 149.0  # Last measurement
    
    def test_write_time_tracking(self):
        """Test write time tracking functionality."""
        metrics = AdapterPerformanceMetrics()
        
        metrics.add_write_time(0.5)
        metrics.add_write_time(0.8)
        
        assert len(metrics.write_times) == 2
        assert metrics.get_avg_write_time() == pytest.approx(0.65)
    
    def test_empty_metrics_averages(self):
        """Test average calculations with no data."""
        metrics = AdapterPerformanceMetrics()
        
        assert metrics.get_avg_serialization_time() == 0.0
        assert metrics.get_avg_write_time() == 0.0


class TestBeysionUnityAdapter:
    """Test suite for BeysionUnityAdapter implementation."""
    
    def setup_method(self):
        """Set up adapter for each test."""
        self.adapter = BeysionUnityAdapter(
            shared_memory_name="test_memory",
            shared_memory_size=1024*1024,
            unity_executable_path=None
        )
        
        # Mock data for testing
        self.mock_beys = [
            MockBeyData(id=1, pos=(100, 200), velocity=(1.0, 2.0)),
            MockBeyData(id=2, pos=(300, 400), velocity=(0.5, -1.0))
        ]
        
        self.mock_hits = [
            MockHitData(pos=(150, 250), bey_ids=(1, 2), is_new_hit=True)
        ]
    
    def teardown_method(self):
        """Clean up adapter after each test."""
        if hasattr(self, 'adapter') and self.adapter.is_connected():
            self.adapter.disconnect()
    
    def test_implements_interface(self):
        """Test that adapter correctly implements IProjectionAdapter interface."""
        assert isinstance(self.adapter, IProjectionAdapter)
        
        # Verify all required methods exist
        required_methods = [
            'connect', 'disconnect', 'is_connected', 'send_tracking_data',
            'send_projection_config', 'receive_commands', 'get_client_info'
        ]
        
        for method in required_methods:
            assert hasattr(self.adapter, method), f"Missing required method: {method}"
            assert callable(getattr(self.adapter, method)), f"Method {method} is not callable"
    
    def test_initial_state(self):
        """Test adapter initial state before connection."""
        assert not self.adapter.is_connected()
        assert self.adapter.get_client_info() is None
        assert not self.adapter.send_tracking_data(1, [], [])
        assert not self.adapter.send_projection_config(1920, 1080)
        assert self.adapter.receive_commands() == []
    
    @patch('adapters.beysion_unity_adapter.mmap.mmap')
    @patch('adapters.beysion_unity_adapter.tempfile.NamedTemporaryFile')
    def test_shared_memory_creation_windows(self, mock_tempfile, mock_mmap):
        """Test shared memory creation on Windows platform."""
        # Setup mocks
        mock_file = Mock()
        mock_file.fileno.return_value = 123
        mock_file.write.return_value = None
        mock_file.flush.return_value = None
        mock_tempfile.return_value = mock_file
        
        mock_memory = Mock()
        mock_memory.seek.return_value = None
        mock_memory.write.return_value = None
        mock_memory.flush.return_value = None
        mock_mmap.return_value = mock_memory
        
        with patch('sys.platform', 'win32'):
            result = self.adapter._create_shared_memory()
        
        assert result is True
        mock_tempfile.assert_called_once()
        mock_mmap.assert_called_once()
        assert self.adapter._shared_memory is mock_memory
    
    @patch('adapters.beysion_unity_adapter.posix_ipc.SharedMemory')
    @patch('adapters.beysion_unity_adapter.mmap.mmap')
    def test_shared_memory_creation_unix(self, mock_mmap, mock_shm_class):
        """Test shared memory creation on Unix/Linux platform."""
        # Setup mocks
        mock_shm = Mock()
        mock_shm.fd = 456
        mock_shm_class.return_value = mock_shm
        
        mock_memory = Mock()
        mock_memory.seek.return_value = None
        mock_memory.write.return_value = None
        mock_memory.flush.return_value = None
        mock_mmap.return_value = mock_memory
        
        with patch('sys.platform', 'linux'):
            result = self.adapter._create_shared_memory()
        
        assert result is True
        mock_shm_class.assert_called_once()
        mock_mmap.assert_called_once_with(456, self.adapter._shared_memory_size)
        assert self.adapter._shared_memory is mock_memory
    
    def test_shared_memory_creation_failure(self):
        """Test shared memory creation failure handling."""
        with patch('adapters.beysion_unity_adapter.tempfile.NamedTemporaryFile', 
                   side_effect=Exception("Mock failure")):
            result = self.adapter._create_shared_memory()
        
        assert result is False
        assert self.adapter._shared_memory is None
    
    @patch.object(BeysionUnityAdapter, '_create_shared_memory')
    @patch.object(BeysionUnityAdapter, '_create_command_buffer')
    @patch.object(BeysionUnityAdapter, '_start_heartbeat_monitoring')
    def test_connection_success(self, mock_heartbeat, mock_cmd_buffer, mock_shared_memory):
        """Test successful connection to Unity client."""
        # Setup mocks
        mock_shared_memory.return_value = True
        mock_cmd_buffer.return_value = True
        mock_heartbeat.return_value = None
        
        with patch.object(self.adapter, '_is_unity_running', return_value=True):
            result = self.adapter.connect()
        
        assert result is True
        assert self.adapter.is_connected()
        mock_shared_memory.assert_called_once()
        mock_cmd_buffer.assert_called_once()
        mock_heartbeat.assert_called_once()
    
    @patch.object(BeysionUnityAdapter, '_create_shared_memory')
    def test_connection_failure(self, mock_shared_memory):
        """Test connection failure handling."""
        mock_shared_memory.return_value = False
        
        result = self.adapter.connect()
        
        assert result is False
        assert not self.adapter.is_connected()
    
    @patch.object(BeysionUnityAdapter, '_stop_heartbeat_monitoring')
    @patch.object(BeysionUnityAdapter, '_cleanup_resources')
    def test_disconnection(self, mock_cleanup, mock_stop_heartbeat):
        """Test proper disconnection and cleanup."""
        # Simulate connected state
        self.adapter._connected = True
        
        self.adapter.disconnect()
        
        assert not self.adapter.is_connected()
        mock_stop_heartbeat.assert_called_once()
        mock_cleanup.assert_called_once()
    
    def test_send_tracking_data_not_connected(self):
        """Test sending tracking data when not connected."""
        result = self.adapter.send_tracking_data(1, self.mock_beys, self.mock_hits)
        assert result is False
    
    @patch.object(BeysionUnityAdapter, 'is_connected')
    @patch('adapters.beysion_unity_adapter.create_shared_memory_frame')
    @patch('adapters.beysion_unity_adapter.ProtocolSerializer.serialize_frame')
    @patch.object(BeysionUnityAdapter, '_write_to_shared_memory')
    def test_send_tracking_data_success(self, mock_write, mock_serialize, mock_create_frame, mock_connected):
        """Test successful tracking data transmission."""
        # Setup mocks
        mock_connected.return_value = True
        mock_frame = Mock()
        mock_create_frame.return_value = mock_frame
        mock_payload = b'mock_serialized_data'
        mock_serialize.return_value = mock_payload
        mock_write.return_value = True
        
        result = self.adapter.send_tracking_data(123, self.mock_beys, self.mock_hits)
        
        assert result is True
        mock_create_frame.assert_called_once_with(
            frame_id=123,
            beys=self.mock_beys,
            hits=self.mock_hits,
            projection_config=None
        )
        mock_serialize.assert_called_once_with(mock_frame)
        mock_write.assert_called_once_with(mock_payload)
        
        # Verify performance metrics updated
        assert self.adapter._metrics.frames_sent == 1
        assert self.adapter._metrics.total_bytes_written == len(mock_payload)
    
    @patch.object(BeysionUnityAdapter, 'is_connected')
    @patch('adapters.beysion_unity_adapter.ProtocolSerializer.serialize_frame')
    @patch.object(BeysionUnityAdapter, '_write_to_shared_memory')
    def test_send_projection_config(self, mock_write, mock_serialize, mock_connected):
        """Test sending projection configuration."""
        mock_connected.return_value = True
        mock_serialize.return_value = b'config_data'
        mock_write.return_value = True
        
        result = self.adapter.send_projection_config(1920, 1080)
        
        assert result is True
        assert self.adapter._current_projection_config is not None
        assert self.adapter._current_projection_config.width == 1920
        assert self.adapter._current_projection_config.height == 1080
        mock_write.assert_called_once()
    
    def test_receive_commands_not_connected(self):
        """Test receiving commands when not connected."""
        commands = self.adapter.receive_commands()
        assert commands == []
    
    @patch.object(BeysionUnityAdapter, 'is_connected')
    def test_receive_commands_no_command_buffer(self, mock_connected):
        """Test receiving commands when command buffer is not available."""
        mock_connected.return_value = True
        self.adapter._command_buffer = None
        
        commands = self.adapter.receive_commands()
        assert commands == []
    
    @patch.object(BeysionUnityAdapter, 'is_connected')
    def test_receive_commands_success(self, mock_connected):
        """Test successful command reception."""
        mock_connected.return_value = True
        
        # Mock command buffer
        mock_buffer = Mock()
        mock_buffer.seek.return_value = None
        
        # Mock header data
        test_command = UnityCommand(CommandType.CALIBRATE, {})
        serialized_command = ProtocolSerializer.serialize_command(test_command)
        header = SharedMemoryHeader(
            frame_counter=1,
            data_size=len(serialized_command),
            checksum=ProtocolSerializer.calculate_checksum(serialized_command)
        )
        
        mock_buffer.read.side_effect = [header.pack(), serialized_command]
        mock_buffer.write.return_value = None
        self.adapter._command_buffer = mock_buffer
        
        commands = self.adapter.receive_commands()
        
        assert len(commands) == 1
        assert commands[0].command_type == CommandType.CALIBRATE
    
    @patch.object(BeysionUnityAdapter, 'is_connected')
    @patch.object(BeysionUnityAdapter, '_is_unity_running')
    def test_get_client_info(self, mock_unity_running, mock_connected):
        """Test getting client information."""
        mock_connected.return_value = True
        mock_unity_running.return_value = True
        
        # Set some metrics
        self.adapter._metrics.frames_sent = 100
        self.adapter._metrics.total_bytes_written = 50000
        
        info = self.adapter.get_client_info()
        
        assert info is not None
        assert info['client_type'] == 'Unity'
        assert info['protocol_version'] == '1.0'
        assert info['frames_sent'] == 100
        assert info['total_bytes_written'] == 50000
        assert info['unity_process_running'] is True
    
    def test_get_client_info_not_connected(self):
        """Test getting client info when not connected."""
        info = self.adapter.get_client_info()
        assert info is None
    
    @patch('subprocess.Popen')
    def test_launch_unity_client_success(self, mock_popen):
        """Test successful Unity client launch."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        # Set up executable path
        test_executable = "/path/to/BeysionClient.exe"
        self.adapter._unity_executable_path = test_executable
        
        result = self.adapter._launch_unity_client()
        
        assert result is True
        assert self.adapter._unity_process is mock_process
        mock_popen.assert_called_once()
        
        # Check command line arguments
        args = mock_popen.call_args[0][0]
        assert test_executable in args
        assert any("--shared-memory-name=test_memory" in arg for arg in args)
    
    def test_launch_unity_client_no_executable(self):
        """Test Unity client launch when executable not found."""
        self.adapter._unity_executable_path = None
        
        with patch('pathlib.Path.exists', return_value=False):
            result = self.adapter._launch_unity_client()
        
        assert result is False
        assert self.adapter._unity_process is None
    
    def test_is_unity_running_no_process(self):
        """Test Unity running check when no process exists."""
        assert not self.adapter._is_unity_running()
    
    def test_is_unity_running_with_process(self):
        """Test Unity running check with active process."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Still running
        self.adapter._unity_process = mock_process
        
        assert self.adapter._is_unity_running()
        
        # Test with terminated process
        mock_process.poll.return_value = 0  # Terminated
        assert not self.adapter._is_unity_running()
    
    def test_write_to_shared_memory_no_memory(self):
        """Test writing to shared memory when memory is not available."""
        result = self.adapter._write_to_shared_memory(b'test_data')
        assert result is False
    
    def test_write_to_shared_memory_success(self):
        """Test successful write to shared memory."""
        # Mock shared memory
        mock_memory = Mock()
        mock_memory.seek.return_value = None
        mock_memory.write.return_value = None
        mock_memory.flush.return_value = None
        self.adapter._shared_memory = mock_memory
        
        test_payload = b'test_payload_data'
        result = self.adapter._write_to_shared_memory(test_payload)
        
        assert result is True
        # Verify header and payload were written
        assert mock_memory.write.call_count == 2  # Header + payload


# ==================== PERFORMANCE TESTS ==================== #

class TestBeysionUnityAdapterPerformance:
    """Performance-focused tests for BeysionUnityAdapter."""
    
    def setup_method(self):
        """Set up adapter for performance testing."""
        self.adapter = BeysionUnityAdapter()
    
    def teardown_method(self):
        """Clean up adapter."""
        if hasattr(self, 'adapter') and self.adapter.is_connected():
            self.adapter.disconnect()
    
    @patch.object(BeysionUnityAdapter, 'is_connected')
    @patch('adapters.beysion_unity_adapter.create_shared_memory_frame')
    @patch('adapters.beysion_unity_adapter.ProtocolSerializer.serialize_frame')
    @patch.object(BeysionUnityAdapter, '_write_to_shared_memory')
    def test_serialization_performance(self, mock_write, mock_serialize, mock_create_frame, mock_connected):
        """Test serialization performance meets requirements."""
        mock_connected.return_value = True
        mock_create_frame.return_value = Mock()
        mock_serialize.return_value = b'serialized_data'
        mock_write.return_value = True
        
        # Create larger dataset for realistic testing
        large_beys = [MockBeyData(id=i, pos=(i*10, i*20), velocity=(i, i*2)) for i in range(10)]
        large_hits = [MockHitData(pos=(i*15, i*25), bey_ids=(i, i+1), is_new_hit=True) for i in range(5)]
        
        # Measure serialization performance
        start_time = time.perf_counter()
        
        for frame_id in range(100):
            result = self.adapter.send_tracking_data(frame_id, large_beys, large_hits)
            assert result is True
        
        total_time = time.perf_counter() - start_time
        avg_time_per_frame = total_time / 100
        
        # Verify performance requirements (target: <0.5ms serialization)
        assert avg_time_per_frame < 0.001  # Less than 1ms total per frame
        
        # Check that performance metrics were collected
        assert len(self.adapter._metrics.serialization_times) > 0
        assert self.adapter._metrics.get_avg_serialization_time() < 0.5  # <0.5ms target
        
        print(f"Serialization performance: {avg_time_per_frame*1000:.3f}ms average per frame")
    
    def test_memory_usage_efficiency(self):
        """Test memory usage efficiency of the adapter."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create adapter and perform operations
        adapter = BeysionUnityAdapter()
        
        # Simulate high-throughput operation
        large_dataset = [MockBeyData(id=i, pos=(i, i), velocity=(0, 0)) for i in range(1000)]
        
        with patch.object(adapter, 'is_connected', return_value=True):
            with patch.object(adapter, '_write_to_shared_memory', return_value=True):
                for _ in range(1000):
                    adapter.send_tracking_data(1, large_dataset[:10], [])
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (target: <50MB)
        assert memory_increase < 50 * 1024 * 1024  # 50MB limit
        
        print(f"Memory usage increase: {memory_increase / (1024*1024):.1f}MB")


# ==================== MOCK CLASSES ==================== #

@dataclass
class MockBeyData:
    """Mock BeyData for testing."""
    id: int
    pos: tuple
    velocity: tuple
    raw_velocity: tuple = (0.0, 0.0)
    acceleration: tuple = (0.0, 0.0)
    shape: tuple = (10, 10)
    frame: int = 0


@dataclass
class MockHitData:
    """Mock HitData for testing."""
    pos: tuple
    bey_ids: tuple
    is_new_hit: bool
    shape: tuple = (5, 5) 