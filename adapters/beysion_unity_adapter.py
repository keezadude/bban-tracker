"""
BeysionUnityAdapter implementation for BBAN-Tracker projection client communication.

This adapter implements the IProjectionAdapter interface to enable high-performance
inter-process communication with the immutable Unity client via shared memory protocol.
"""

import os
import sys
import mmap
import time
import threading
import subprocess
import signal
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from ..core.interfaces import IProjectionAdapter
from .shared_memory_protocol import (
    SharedMemoryFrame, SharedMemoryHeader, UnityCommand, ProjectionConfig,
    ProtocolSerializer, create_shared_memory_frame, CommandType,
    DEFAULT_SHARED_MEMORY_SIZE, HEADER_SIZE, MAX_PAYLOAD_SIZE
)


@dataclass
class AdapterPerformanceMetrics:
    """Performance tracking for the adapter."""
    frames_sent: int = 0
    serialization_times: List[float] = field(default_factory=list)
    write_times: List[float] = field(default_factory=list)
    total_bytes_written: int = 0
    connection_attempts: int = 0
    last_heartbeat: float = 0.0
    
    def add_serialization_time(self, time_ms: float):
        """Add a serialization time measurement."""
        self.serialization_times.append(time_ms)
        if len(self.serialization_times) > 100:
            self.serialization_times.pop(0)
    
    def add_write_time(self, time_ms: float):
        """Add a write time measurement."""
        self.write_times.append(time_ms)
        if len(self.write_times) > 100:
            self.write_times.pop(0)
    
    def get_avg_serialization_time(self) -> float:
        """Get average serialization time in ms."""
        return sum(self.serialization_times) / len(self.serialization_times) if self.serialization_times else 0.0
    
    def get_avg_write_time(self) -> float:
        """Get average write time in ms."""
        return sum(self.write_times) / len(self.write_times) if self.write_times else 0.0


class BeysionUnityAdapter(IProjectionAdapter):
    """
    Production adapter for Unity client communication via shared memory.
    
    This adapter provides high-performance inter-process communication with
    the immutable Unity client using a custom shared memory protocol optimized
    for real-time tracking data transmission.
    """
    
    def __init__(self, 
                 shared_memory_name: str = "beysion_tracker_data",
                 shared_memory_size: int = DEFAULT_SHARED_MEMORY_SIZE,
                 unity_executable_path: Optional[str] = None):
        """
        Initialize the Unity adapter.
        
        Args:
            shared_memory_name: Name of the shared memory segment
            shared_memory_size: Size of shared memory in bytes
            unity_executable_path: Path to Unity client executable
        """
        self._shared_memory_name = shared_memory_name
        self._shared_memory_size = shared_memory_size
        self._unity_executable_path = unity_executable_path
        
        # Shared memory resources
        self._shared_memory: Optional[mmap.mmap] = None
        self._shared_memory_file: Optional[int] = None
        self._write_lock = threading.RLock()
        
        # Connection state
        self._connected = False
        self._frame_counter = 0
        self._current_projection_config: Optional[ProjectionConfig] = None
        
        # Unity process management
        self._unity_process: Optional[subprocess.Popen] = None
        self._auto_launch_unity = True
        
        # Performance monitoring
        self._metrics = AdapterPerformanceMetrics()
        
        # Heartbeat monitoring
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()
        
        # Command buffer for Unity -> Tracker communication
        self._command_buffer_name = f"{shared_memory_name}_commands"
        self._command_buffer: Optional[mmap.mmap] = None
        self._command_buffer_file: Optional[int] = None
    
    def connect(self) -> bool:
        """
        Establish shared memory connection to Unity client.
        
        Returns:
            True if connection was successful
        """
        try:
            self._metrics.connection_attempts += 1
            
            # Create or connect to shared memory for data transmission
            if not self._create_shared_memory():
                return False
            
            # Create command buffer for Unity -> Tracker communication
            if not self._create_command_buffer():
                self._cleanup_shared_memory()
                return False
            
            # Launch Unity client if needed and enabled
            if self._auto_launch_unity and not self._is_unity_running():
                if not self._launch_unity_client():
                    print("[BeysionUnityAdapter] Warning: Failed to launch Unity client")
                    # Continue anyway - Unity might be launched manually
            
            # Start heartbeat monitoring
            self._start_heartbeat_monitoring()
            
            self._connected = True
            print(f"[BeysionUnityAdapter] Connected to shared memory: {self._shared_memory_name}")
            return True
            
        except Exception as e:
            print(f"[BeysionUnityAdapter] Connection failed: {e}")
            self._cleanup_resources()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from Unity client and clean up resources."""
        self._connected = False
        
        # Stop heartbeat monitoring
        self._stop_heartbeat_monitoring()
        
        # Clean up shared memory resources
        self._cleanup_resources()
        
        # Optionally terminate Unity process if we launched it
        if self._unity_process and self._unity_process.poll() is None:
            try:
                self._unity_process.terminate()
                self._unity_process.wait(timeout=5.0)
                print("[BeysionUnityAdapter] Unity client terminated")
            except (subprocess.TimeoutExpired, Exception) as e:
                print(f"[BeysionUnityAdapter] Warning: Failed to terminate Unity: {e}")
        
        print("[BeysionUnityAdapter] Disconnected")
    
    def is_connected(self) -> bool:
        """Return True if connected to Unity client."""
        if not self._connected or not self._shared_memory:
            return False
        
        # Additional check: verify shared memory is still accessible
        try:
            # Try to access the shared memory
            self._shared_memory.seek(0)
            return True
        except (ValueError, OSError):
            self._connected = False
            return False
    
    def send_tracking_data(self, frame_id: int, beys: list, hits: list) -> bool:
        """
        Send tracking data to Unity client via shared memory.
        
        Args:
            frame_id: Frame identifier
            beys: List of BeyData objects from core events
            hits: List of HitData objects from core events
            
        Returns:
            True if data was sent successfully
        """
        if not self.is_connected():
            return False
        
        try:
            # Create shared memory frame
            frame = create_shared_memory_frame(
                frame_id=frame_id,
                beys=beys,
                hits=hits,
                projection_config=self._current_projection_config
            )
            
            # Serialize data with performance tracking
            serialize_start = time.perf_counter()
            payload = ProtocolSerializer.serialize_frame(frame)
            serialize_time = (time.perf_counter() - serialize_start) * 1000
            self._metrics.add_serialization_time(serialize_time)
            
            # Check payload size
            if len(payload) > MAX_PAYLOAD_SIZE:
                print(f"[BeysionUnityAdapter] Warning: Payload too large: {len(payload)} bytes")
                return False
            
            # Write to shared memory with performance tracking
            write_start = time.perf_counter()
            success = self._write_to_shared_memory(payload)
            write_time = (time.perf_counter() - write_start) * 1000
            self._metrics.add_write_time(write_time)
            
            if success:
                self._metrics.frames_sent += 1
                self._metrics.total_bytes_written += len(payload)
                self._frame_counter += 1
                return True
            
            return False
            
        except Exception as e:
            print(f"[BeysionUnityAdapter] Error sending tracking data: {e}")
            return False
    
    def send_projection_config(self, width: int, height: int) -> bool:
        """
        Send projection configuration to Unity client.
        
        Args:
            width: Projection width in pixels
            height: Projection height in pixels
            
        Returns:
            True if config was sent successfully
        """
        try:
            # Update current projection config
            self._current_projection_config = ProjectionConfig(
                width=width,
                height=height
            )
            
            # Send a special config-only frame
            frame = SharedMemoryFrame(
                frame_id=self._frame_counter,
                timestamp=time.perf_counter(),
                beys=[],
                hits=[],
                projection_config=self._current_projection_config
            )
            
            payload = ProtocolSerializer.serialize_frame(frame)
            success = self._write_to_shared_memory(payload)
            
            if success:
                self._frame_counter += 1
                print(f"[BeysionUnityAdapter] Projection config sent: {width}×{height}")
            
            return success
            
        except Exception as e:
            print(f"[BeysionUnityAdapter] Error sending projection config: {e}")
            return False
    
    def receive_commands(self) -> List[UnityCommand]:
        """
        Check for and return commands from Unity client.
        
        Returns:
            List of commands received from Unity
        """
        commands = []
        
        if not self.is_connected() or not self._command_buffer:
            return commands
        
        try:
            # Read command buffer header
            self._command_buffer.seek(0)
            header_data = self._command_buffer.read(HEADER_SIZE)
            
            if len(header_data) < HEADER_SIZE:
                return commands
            
            header = SharedMemoryHeader.unpack(header_data)
            
            if not header.validate() or header.data_size == 0:
                return commands
            
            # Read command data
            command_data = self._command_buffer.read(header.data_size)
            
            if len(command_data) != header.data_size:
                return commands
            
            # Verify checksum
            calculated_checksum = ProtocolSerializer.calculate_checksum(command_data)
            if calculated_checksum != header.checksum:
                print("[BeysionUnityAdapter] Command checksum mismatch")
                return commands
            
            # Deserialize commands
            command = ProtocolSerializer.deserialize_command(command_data)
            commands.append(command)
            
            # Clear the command buffer after reading
            self._command_buffer.seek(0)
            self._command_buffer.write(b'\x00' * HEADER_SIZE)
            
        except Exception as e:
            print(f"[BeysionUnityAdapter] Error receiving commands: {e}")
        
        return commands
    
    def get_client_info(self) -> Optional[Dict[str, Any]]:
        """
        Return information about the connected Unity client.
        
        Returns:
            Dictionary with client information or None if not connected
        """
        if not self.is_connected():
            return None
        
        return {
            'client_type': 'Unity',
            'protocol_version': '1.0',
            'shared_memory_name': self._shared_memory_name,
            'shared_memory_size': self._shared_memory_size,
            'frames_sent': self._metrics.frames_sent,
            'avg_serialization_time_ms': self._metrics.get_avg_serialization_time(),
            'avg_write_time_ms': self._metrics.get_avg_write_time(),
            'total_bytes_written': self._metrics.total_bytes_written,
            'unity_process_running': self._is_unity_running(),
            'last_heartbeat': self._metrics.last_heartbeat
        }
    
    # ==================== INTERNAL IMPLEMENTATION ==================== #
    
    def _create_shared_memory(self) -> bool:
        """Create or connect to shared memory segment."""
        try:
            if sys.platform == "win32":
                # Windows implementation using mmap
                import mmap
                # Create a temporary file for memory mapping on Windows
                import tempfile
                temp_file = tempfile.NamedTemporaryFile(delete=False)
                temp_file.write(b'\x00' * self._shared_memory_size)
                temp_file.flush()
                
                self._shared_memory_file = temp_file.fileno()
                self._shared_memory = mmap.mmap(
                    self._shared_memory_file, 
                    self._shared_memory_size,
                    access=mmap.ACCESS_WRITE
                )
            else:
                # Unix/Linux implementation using POSIX shared memory
                import posix_ipc
                try:
                    # Try to create new shared memory
                    self._shm = posix_ipc.SharedMemory(
                        self._shared_memory_name,
                        posix_ipc.O_CREAT | posix_ipc.O_EXCL,
                        size=self._shared_memory_size
                    )
                except posix_ipc.ExistentialError:
                    # Shared memory already exists, connect to it
                    self._shm = posix_ipc.SharedMemory(self._shared_memory_name)
                
                self._shared_memory = mmap.mmap(
                    self._shm.fd,
                    self._shared_memory_size
                )
            
            # Initialize shared memory with zeros
            self._shared_memory.seek(0)
            self._shared_memory.write(b'\x00' * self._shared_memory_size)
            self._shared_memory.flush()
            
            return True
            
        except Exception as e:
            print(f"[BeysionUnityAdapter] Failed to create shared memory: {e}")
            return False
    
    def _create_command_buffer(self) -> bool:
        """Create command buffer for Unity -> Tracker communication."""
        try:
            command_buffer_size = 64 * 1024  # 64KB for commands
            
            if sys.platform == "win32":
                # Windows implementation
                import tempfile
                temp_file = tempfile.NamedTemporaryFile(delete=False)
                temp_file.write(b'\x00' * command_buffer_size)
                temp_file.flush()
                
                self._command_buffer_file = temp_file.fileno()
                self._command_buffer = mmap.mmap(
                    self._command_buffer_file,
                    command_buffer_size,
                    access=mmap.ACCESS_WRITE
                )
            else:
                # Unix/Linux implementation
                import posix_ipc
                try:
                    self._cmd_shm = posix_ipc.SharedMemory(
                        self._command_buffer_name,
                        posix_ipc.O_CREAT | posix_ipc.O_EXCL,
                        size=command_buffer_size
                    )
                except posix_ipc.ExistentialError:
                    self._cmd_shm = posix_ipc.SharedMemory(self._command_buffer_name)
                
                self._command_buffer = mmap.mmap(
                    self._cmd_shm.fd,
                    command_buffer_size
                )
            
            # Initialize command buffer
            self._command_buffer.seek(0)
            self._command_buffer.write(b'\x00' * command_buffer_size)
            self._command_buffer.flush()
            
            return True
            
        except Exception as e:
            print(f"[BeysionUnityAdapter] Failed to create command buffer: {e}")
            return False
    
    def _write_to_shared_memory(self, payload: bytes) -> bool:
        """Write payload to shared memory with proper header."""
        if not self._shared_memory:
            return False
        
        try:
            with self._write_lock:
                # Calculate checksum
                checksum = ProtocolSerializer.calculate_checksum(payload)
                
                # Create header
                header = SharedMemoryHeader(
                    frame_counter=self._frame_counter,
                    data_size=len(payload),
                    checksum=checksum
                )
                
                # Write header and payload
                self._shared_memory.seek(0)
                self._shared_memory.write(header.pack())
                self._shared_memory.write(payload)
                self._shared_memory.flush()
                
                return True
                
        except Exception as e:
            print(f"[BeysionUnityAdapter] Failed to write to shared memory: {e}")
            return False
    
    def _launch_unity_client(self) -> bool:
        """Launch Unity client if executable path is configured."""
        if not self._unity_executable_path:
            # Try to find Unity executable in common locations
            possible_paths = [
                Path.cwd() / "beysion-unity" / "BeysionClient.exe",
                Path.cwd().parent / "beysion-unity" / "BeysionClient.exe", 
                Path("C:/Program Files/Beysion/BeysionClient.exe"),
                Path("/usr/local/bin/beysion-client"),
                Path("./BeysionClient"),
                Path("./BeysionClient.exe")
            ]
            
            for path in possible_paths:
                if path.exists():
                    self._unity_executable_path = str(path)
                    break
            else:
                print("[BeysionUnityAdapter] Unity executable not found")
                return False
        
        try:
            # Launch Unity client with shared memory parameters
            cmd = [
                self._unity_executable_path,
                f"--shared-memory-name={self._shared_memory_name}",
                f"--command-buffer-name={self._command_buffer_name}"
            ]
            
            self._unity_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            print(f"[BeysionUnityAdapter] Launched Unity client: PID {self._unity_process.pid}")
            return True
            
        except Exception as e:
            print(f"[BeysionUnityAdapter] Failed to launch Unity client: {e}")
            return False
    
    def _is_unity_running(self) -> bool:
        """Check if Unity client process is running."""
        if not self._unity_process:
            return False
        
        return self._unity_process.poll() is None
    
    def _start_heartbeat_monitoring(self) -> None:
        """Start heartbeat monitoring thread."""
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="UnityAdapter-Heartbeat"
        )
        self._heartbeat_thread.start()
    
    def _stop_heartbeat_monitoring(self) -> None:
        """Stop heartbeat monitoring thread."""
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1.0)
    
    def _heartbeat_loop(self) -> None:
        """Heartbeat monitoring loop."""
        while not self._stop_heartbeat.wait(1.0):  # Check every second
            try:
                # Send heartbeat command to Unity
                heartbeat_cmd = UnityCommand(
                    command_type=CommandType.HEARTBEAT,
                    parameters={}
                )
                
                # Note: In a real implementation, this would check for
                # a heartbeat response from Unity to detect disconnections
                self._metrics.last_heartbeat = time.perf_counter()
                
            except Exception as e:
                print(f"[BeysionUnityAdapter] Heartbeat error: {e}")
    
    def _cleanup_shared_memory(self) -> None:
        """Clean up shared memory resources."""
        try:
            if self._shared_memory:
                self._shared_memory.close()
                self._shared_memory = None
            
            if hasattr(self, '_shm'):
                self._shm.close_fd()
                self._shm.unlink()
                
        except Exception as e:
            print(f"[BeysionUnityAdapter] Error cleaning up shared memory: {e}")
    
    def _cleanup_command_buffer(self) -> None:
        """Clean up command buffer resources."""
        try:
            if self._command_buffer:
                self._command_buffer.close()
                self._command_buffer = None
                
            if hasattr(self, '_cmd_shm'):
                self._cmd_shm.close_fd()
                self._cmd_shm.unlink()
                
        except Exception as e:
            print(f"[BeysionUnityAdapter] Error cleaning up command buffer: {e}")
    
    def _cleanup_resources(self) -> None:
        """Clean up all adapter resources."""
        self._cleanup_shared_memory()
        self._cleanup_command_buffer()
    
    def __del__(self):
        """Destructor to ensure resources are cleaned up."""
        if self._connected:
            self.disconnect() 