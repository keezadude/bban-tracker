"""
Optimized Unity adapter with CPU profiling and event batching.

This adapter implements Recommendations 1 and 2 from localhost optimization analysis:
1. Profile CPU Usage of Serialization/Deserialization  
2. Batch Events per Frame for optimal localhost performance

Combines the best of both UDP and shared memory approaches with performance monitoring.
"""

import socket
import time
import threading
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field

import msgpack

from .beysion_unity_adapter_corrected import BeysionUnityAdapterCorrected, NetworkPerformanceMetrics
from .shared_memory_protocol import ProtocolSerializer, create_shared_memory_frame, ProjectionConfig
from .performance_profiler import PerformanceProfiler, get_global_profiler, profile_serialization
from ..core.interfaces import IProjectionAdapter
from ..core.events import BeyData, HitData


@dataclass
class OptimizedPerformanceMetrics:
    """Enhanced metrics including CPU profiling and batching statistics."""
    # Base networking metrics
    frames_sent: int = 0
    udp_send_times: List[float] = field(default_factory=list)
    tcp_response_times: List[float] = field(default_factory=list)
    total_bytes_sent: int = 0
    connection_attempts: int = 0
    connection_failures: int = 0
    last_message_time: float = 0.0
    packet_loss_count: int = 0
    
    # Serialization profiling metrics
    serialization_times: List[float] = field(default_factory=list)
    deserialization_times: List[float] = field(default_factory=list)
    payload_sizes: List[int] = field(default_factory=list)
    
    # Batching metrics
    batches_sent: int = 0
    events_batched: int = 0
    batch_processing_times: List[float] = field(default_factory=list)
    cpu_time_saved_ms: float = 0.0
    bandwidth_saved_bytes: int = 0
    
    def add_serialization_time(self, time_ms: float, payload_size: int = 0):
        """Add serialization time measurement."""
        self.serialization_times.append(time_ms)
        if len(self.serialization_times) > 100:
            self.serialization_times.pop(0)
        
        if payload_size > 0:
            self.payload_sizes.append(payload_size)
            if len(self.payload_sizes) > 100:
                self.payload_sizes.pop(0)
    
    def add_batch_metrics(self, event_count: int, processing_time_ms: float, bytes_saved: int = 0):
        """Add batch processing metrics."""
        self.batches_sent += 1
        self.events_batched += event_count
        self.batch_processing_times.append(processing_time_ms)
        self.bandwidth_saved_bytes += bytes_saved
        
        if len(self.batch_processing_times) > 100:
            self.batch_processing_times.pop(0)
    
    def get_avg_serialization_time(self) -> float:
        """Get average serialization time in milliseconds."""
        return sum(self.serialization_times) / len(self.serialization_times) if self.serialization_times else 0.0
    
    def get_avg_batch_size(self) -> float:
        """Get average batch size."""
        return self.events_batched / self.batches_sent if self.batches_sent > 0 else 0.0
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        return {
            'frames_sent': self.frames_sent,
            'batches_sent': self.batches_sent,
            'avg_batch_size': self.get_avg_batch_size(),
            'avg_serialization_time_ms': self.get_avg_serialization_time(),
            'avg_payload_size_bytes': sum(self.payload_sizes) / len(self.payload_sizes) if self.payload_sizes else 0,
            'total_bandwidth_saved_bytes': self.bandwidth_saved_bytes,
            'total_cpu_time_saved_ms': self.cpu_time_saved_ms,
            'estimated_fps_capability': 1000.0 / self.get_avg_serialization_time() if self.get_avg_serialization_time() > 0 else 0
        }


class BeysionUnityAdapterOptimized(IProjectionAdapter):
    """
    Optimized Unity adapter with performance profiling and intelligent batching.
    
    Features:
    - Real-time CPU profiling of serialization/deserialization
    - Intelligent event batching for localhost optimization
    - Automatic serialization method selection based on performance
    - Comprehensive performance metrics and recommendations
    - Adaptive optimization based on runtime performance
    """
    
    def __init__(self, 
                 udp_host: str = "127.0.0.1",
                 udp_port: int = 50007,
                 tcp_host: str = "127.0.0.1", 
                 tcp_port: int = 50008,
                 unity_executable_path: Optional[str] = None,
                 enable_batching: bool = True,
                 enable_profiling: bool = True,
                 auto_optimize: bool = True):
        """
        Initialize optimized Unity adapter.
        
        Args:
            udp_host: UDP target host (Unity listening)
            udp_port: UDP target port (Unity listening on 50007)
            tcp_host: TCP server host (for Unity to connect to)
            tcp_port: TCP server port (Unity connects to 50008)
            unity_executable_path: Path to Unity client executable
            enable_batching: Enable event batching optimization
            enable_profiling: Enable real-time performance profiling
            auto_optimize: Enable automatic optimization based on profiling data
        """
        # Network configuration
        self._udp_host = udp_host
        self._udp_port = udp_port
        self._tcp_host = tcp_host
        self._tcp_port = tcp_port
        
        # Socket resources (inherited pattern)
        self._udp_socket: Optional[socket.socket] = None
        self._tcp_server_socket: Optional[socket.socket] = None
        self._tcp_client_socket: Optional[socket.socket] = None
        
        # Connection state
        self._connected = False
        self._frame_counter = 0
        
        # Unity process management
        self._unity_executable_path = unity_executable_path
        self._unity_process: Optional[subprocess.Popen] = None
        self._auto_launch_unity = True
        
        # Performance optimization features
        self.enable_batching = enable_batching
        self.enable_profiling = enable_profiling
        self.auto_optimize = auto_optimize
        
        # Performance monitoring
        self._metrics = OptimizedPerformanceMetrics()
        self._profiler = get_global_profiler() if enable_profiling else None
        
        # Threading for TCP and optimization
        self._tcp_thread: Optional[threading.Thread] = None
        self._optimization_thread: Optional[threading.Thread] = None
        self._stop_threads = threading.Event()
        self._tcp_lock = threading.RLock()
        
        # Command callback
        self._command_callback: Optional[callable] = None
        
        # Serialization optimization
        self._current_serializer = "json"  # Start with JSON, may adapt
        self._serializer_performance: Dict[str, float] = {}
        self._adaptation_counter = 0
        
        # Event batching
        self._pending_batch: List[Dict[str, Any]] = []
        self._last_batch_time = time.perf_counter()
        self._batch_lock = threading.RLock()
        self._max_batch_size = 5
        self._max_batch_age_ms = 16.67  # 1 frame @ 60 FPS
        
        # Performance reporting
        self._last_performance_report = time.perf_counter()
        self._performance_report_interval = 10.0  # 10 seconds
        
        print(f"[BeysionUnityAdapterOptimized] Initialized with batching={enable_batching}, profiling={enable_profiling}, auto_optimize={auto_optimize}")
    
    def connect(self) -> bool:
        """Establish connection with performance monitoring."""
        try:
            self._metrics.connection_attempts += 1
            
            # Create UDP socket
            if not self._create_udp_socket():
                return False
            
            # Create TCP server
            if not self._create_tcp_server():
                self._cleanup_udp_socket()
                return False
            
            # Start TCP thread
            self._start_tcp_thread()
            
            # Start optimization thread if auto-optimization is enabled
            if self.auto_optimize:
                self._start_optimization_thread()
            
            # Launch Unity if configured
            if self._auto_launch_unity and not self._is_unity_running():
                if not self._launch_unity_client():
                    print("[BeysionUnityAdapterOptimized] Warning: Failed to launch Unity client")
            
            self._connected = True
            
            # Initialize profiler if enabled
            if self._profiler and self.enable_profiling:
                # Configure event batcher
                if self._profiler.event_batcher:
                    self._profiler.event_batcher.set_batch_callback(self._process_batched_events)
            
            print(f"[BeysionUnityAdapterOptimized] Connected with advanced optimizations enabled")
            return True
            
        except Exception as e:
            print(f"[BeysionUnityAdapterOptimized] Connection failed: {e}")
            self._metrics.connection_failures += 1
            self._cleanup_all_resources()
            return False
    
    def disconnect(self) -> None:
        """Disconnect with cleanup and final performance report."""
        self._connected = False
        
        # Generate final performance report
        if self.enable_profiling and self._profiler:
            report = self._profiler.get_performance_report()
            print(f"[BeysionUnityAdapterOptimized] Final Performance Report:")
            self._print_performance_summary(report)
            
            # Save detailed report
            try:
                report_path = Path("performance_report_final.json")
                self._profiler.save_report(report_path)
            except Exception as e:
                print(f"[BeysionUnityAdapterOptimized] Could not save performance report: {e}")
        
        # Stop threads
        self._stop_threads.set()
        
        if self._tcp_thread:
            self._tcp_thread.join(timeout=2.0)
        
        if self._optimization_thread:
            self._optimization_thread.join(timeout=2.0)
        
        # Cleanup resources
        self._cleanup_all_resources()
        
        # Terminate Unity if we launched it
        if self._unity_process and self._unity_process.poll() is None:
            try:
                self._unity_process.terminate()
                self._unity_process.wait(timeout=5.0)
            except Exception as e:
                print(f"[BeysionUnityAdapterOptimized] Warning: Failed to terminate Unity: {e}")
        
        print("[BeysionUnityAdapterOptimized] Disconnected with performance analytics")
    
    def is_connected(self) -> bool:
        """Check connection status."""
        if not self._connected:
            return False
        
        try:
            if self._udp_socket:
                self._udp_socket.getsockname()
                return True
        except (OSError, socket.error):
            self._connected = False
        
        return False
    
    def send_tracking_data(self, frame_id: int, beys: list, hits: list) -> bool:
        """
        Send tracking data with intelligent batching and performance profiling.
        
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
            # Create event data for batching/profiling
            event_data = {
                'frame_id': frame_id,
                'beys': beys,
                'hits': hits,
                'timestamp': time.perf_counter()
            }
            
            # Use batching if enabled and profiler is available
            if self.enable_batching and self._profiler and self._profiler.event_batcher:
                # Add to batch - will automatically flush when conditions are met
                batch_flushed = self._profiler.event_batcher.add_event(event_data)
                
                if batch_flushed:
                    self._metrics.frames_sent += 1
                
                return True
            else:
                # Send immediately with profiling
                return self._send_tracking_data_immediate(frame_id, beys, hits)
            
        except Exception as e:
            print(f"[BeysionUnityAdapterOptimized] Error sending tracking data: {e}")
            return False
    
    def _send_tracking_data_immediate(self, frame_id: int, beys: list, hits: list) -> bool:
        """Send tracking data immediately with serialization profiling."""
        try:
            # Profile serialization with current method
            if self._current_serializer == "json":
                message, serialize_time = self._profile_json_serialization(frame_id, beys, hits)
            elif self._current_serializer == "msgpack":
                message, serialize_time = self._profile_msgpack_serialization(frame_id, beys, hits)
            else:
                message, serialize_time = self._profile_custom_serialization(frame_id, beys, hits)
            
            # Send UDP message with timing
            send_start = time.perf_counter()
            success = self._send_udp_message(message)
            send_time = (time.perf_counter() - send_start) * 1000
            
            if success:
                # Update metrics
                self._metrics.frames_sent += 1
                self._metrics.total_bytes_sent += len(message.encode('utf-8') if isinstance(message, str) else message)
                self._metrics.last_message_time = time.perf_counter()
                self._metrics.add_serialization_time(serialize_time, len(message.encode('utf-8') if isinstance(message, str) else message))
                self._frame_counter += 1
                
                # Track serializer performance for adaptation
                self._serializer_performance[self._current_serializer] = serialize_time
                
                return True
            else:
                self._metrics.packet_loss_count += 1
                return False
                
        except Exception as e:
            print(f"[BeysionUnityAdapterOptimized] Error in immediate send: {e}")
            return False
    
    def _profile_json_serialization(self, frame_id: int, beys: list, hits: list) -> tuple:
        """Profile JSON serialization performance."""
        def json_serializer():
            # Create structured data for JSON
            data = {
                'frame_id': frame_id,
                'beys': [self._bey_to_dict(bey) for bey in beys],
                'hits': [self._hit_to_dict(hit) for hit in hits]
            }
            return json.dumps(data)
        
        if self._profiler:
            return self._profiler.profile_serialization("json_serialize", json_serializer, None)
        else:
            start_time = time.perf_counter()
            result = json_serializer()
            return result, (time.perf_counter() - start_time) * 1000
    
    def _profile_msgpack_serialization(self, frame_id: int, beys: list, hits: list) -> tuple:
        """Profile MessagePack serialization performance."""
        def msgpack_serializer():
            # Create shared memory frame for MessagePack
            frame = create_shared_memory_frame(frame_id, beys, hits)
            return ProtocolSerializer.serialize_frame(frame)
        
        if self._profiler:
            return self._profiler.profile_serialization("msgpack_serialize", msgpack_serializer, None)
        else:
            start_time = time.perf_counter()
            result = msgpack_serializer()
            return result, (time.perf_counter() - start_time) * 1000
    
    def _profile_custom_serialization(self, frame_id: int, beys: list, hits: list) -> tuple:
        """Profile custom string formatting (main.py compatible)."""
        def custom_serializer():
            message = f"{frame_id}, beys:"
            for bey in beys:
                bey_id = bey.getId() if hasattr(bey, 'getId') else getattr(bey, 'id', 0)
                if hasattr(bey, 'getPos'):
                    x, y = bey.getPos()
                else:
                    x, y = getattr(bey, 'x', 0), getattr(bey, 'y', 0)
                message += f"({bey_id}, {x}, {y})"
            
            message += ", hits:"
            for hit in hits:
                if hasattr(hit, 'getPos'):
                    x, y = hit.getPos()
                elif hasattr(hit, 'isNewHit') and hit.isNewHit():
                    x, y = getattr(hit, 'x', 0), getattr(hit, 'y', 0)
                else:
                    continue
                message += f"({x}, {y})"
            
            return message
        
        if self._profiler:
            return self._profiler.profile_serialization("custom_format", custom_serializer, None)
        else:
            start_time = time.perf_counter()
            result = custom_serializer()
            return result, (time.perf_counter() - start_time) * 1000
    
    def _process_batched_events(self, events: List[Dict[str, Any]]) -> bool:
        """Process a batch of events (callback for EventBatcher)."""
        if not events:
            return False
        
        batch_start = time.perf_counter()
        
        try:
            # Create batch message
            if self._current_serializer == "json":
                batch_message = self._create_json_batch(events)
            elif self._current_serializer == "msgpack":
                batch_message = self._create_msgpack_batch(events)
            else:
                batch_message = self._create_custom_batch(events)
            
            # Send batch
            success = self._send_udp_message(batch_message)
            
            if success:
                # Calculate metrics
                processing_time = (time.perf_counter() - batch_start) * 1000
                batch_size = len(events)
                
                # Estimate bandwidth saved (rough calculation)
                single_message_size = len(batch_message) // batch_size if batch_size > 0 else 0
                individual_overhead = 28 * batch_size  # UDP header per message
                bytes_saved = individual_overhead
                
                # Update metrics
                self._metrics.add_batch_metrics(batch_size, processing_time, bytes_saved)
                self._metrics.frames_sent += batch_size
                self._metrics.total_bytes_sent += len(batch_message.encode('utf-8') if isinstance(batch_message, str) else batch_message)
                
                return True
            
            return False
            
        except Exception as e:
            print(f"[BeysionUnityAdapterOptimized] Error processing batch: {e}")
            return False
    
    def _create_json_batch(self, events: List[Dict[str, Any]]) -> str:
        """Create JSON batch message."""
        batch_data = {
            'type': 'batch',
            'count': len(events),
            'events': events
        }
        return json.dumps(batch_data)
    
    def _create_msgpack_batch(self, events: List[Dict[str, Any]]) -> bytes:
        """Create MessagePack batch message."""
        batch_data = {
            'type': 'batch',
            'count': len(events),
            'events': events
        }
        return msgpack.packb(batch_data, use_bin_type=True)
    
    def _create_custom_batch(self, events: List[Dict[str, Any]]) -> str:
        """Create custom format batch message."""
        batch_message = f"BATCH:{len(events)};"
        for event in events:
            frame_id = event.get('frame_id', 0)
            beys = event.get('beys', [])
            hits = event.get('hits', [])
            
            batch_message += f"{frame_id},beys:"
            for bey in beys:
                bey_id = getattr(bey, 'id', 0)
                x, y = getattr(bey, 'pos', (0, 0))
                batch_message += f"({bey_id},{x},{y})"
            batch_message += ",hits:"
            for hit in hits:
                x, y = getattr(hit, 'pos', (0, 0))
                batch_message += f"({x},{y})"
            batch_message += ";"
        
        return batch_message
    
    def _bey_to_dict(self, bey) -> Dict[str, Any]:
        """Convert BeyData to dictionary for JSON serialization."""
        return {
            'id': getattr(bey, 'id', 0),
            'pos_x': getattr(bey, 'pos', (0, 0))[0],
            'pos_y': getattr(bey, 'pos', (0, 0))[1],
            'velocity_x': getattr(bey, 'velocity', (0, 0))[0],
            'velocity_y': getattr(bey, 'velocity', (0, 0))[1],
            'frame': getattr(bey, 'frame', 0)
        }
    
    def _hit_to_dict(self, hit) -> Dict[str, Any]:
        """Convert HitData to dictionary for JSON serialization."""
        return {
            'pos_x': getattr(hit, 'pos', (0, 0))[0],
            'pos_y': getattr(hit, 'pos', (0, 0))[1],
            'is_new_hit': getattr(hit, 'is_new_hit', True)
        }
    
    def _start_optimization_thread(self) -> None:
        """Start automatic optimization thread."""
        self._optimization_thread = threading.Thread(
            target=self._optimization_loop,
            daemon=True,
            name="UnityAdapter-Optimization"
        )
        self._optimization_thread.start()
    
    def _optimization_loop(self) -> None:
        """Automatic optimization loop."""
        while not self._stop_threads.is_set():
            try:
                time.sleep(5.0)  # Check every 5 seconds
                
                if self.enable_profiling and self._profiler:
                    # Get current performance data
                    report = self._profiler.get_performance_report()
                    
                    # Adapt serialization method based on performance
                    self._adapt_serialization_method(report)
                    
                    # Print periodic performance reports
                    current_time = time.perf_counter()
                    if current_time - self._last_performance_report > self._performance_report_interval:
                        self._print_performance_summary(report)
                        self._last_performance_report = current_time
                
            except Exception as e:
                print(f"[BeysionUnityAdapterOptimized] Optimization loop error: {e}")
                time.sleep(1.0)
    
    def _adapt_serialization_method(self, report: Dict[str, Any]) -> None:
        """Adapt serialization method based on performance data."""
        serialization_metrics = report.get('serialization_metrics', {})
        
        if len(serialization_metrics) < 2:
            return  # Need at least 2 methods to compare
        
        # Find the fastest serialization method
        fastest_method = None
        fastest_time = float('inf')
        
        for method_name, metrics in serialization_metrics.items():
            if 'serialize' in method_name and metrics['total_calls'] > 10:  # Need enough data
                avg_time = metrics['avg_time_ms']
                if avg_time < fastest_time:
                    fastest_time = avg_time
                    fastest_method = method_name.replace('_serialize', '')
        
        # Switch if we found a better method
        if fastest_method and fastest_method != self._current_serializer:
            self._adaptation_counter += 1
            if self._adaptation_counter >= 3:  # Only adapt after consistent results
                old_method = self._current_serializer
                self._current_serializer = fastest_method
                improvement = ((self._serializer_performance.get(old_method, 0) - fastest_time) / 
                             self._serializer_performance.get(old_method, 1)) * 100
                print(f"[BeysionUnityAdapterOptimized] Adapted serialization: {old_method} → {fastest_method} ({improvement:.1f}% improvement)")
                self._adaptation_counter = 0
    
    def _print_performance_summary(self, report: Dict[str, Any]) -> None:
        """Print performance summary to console."""
        print("\n[BeysionUnityAdapterOptimized] === PERFORMANCE SUMMARY ===")
        
        # Basic metrics
        metrics_summary = self._metrics.get_performance_summary()
        print(f"Frames sent: {metrics_summary['frames_sent']}")
        print(f"Batches sent: {metrics_summary['batches_sent']}")
        print(f"Avg batch size: {metrics_summary['avg_batch_size']:.1f}")
        print(f"Avg serialization time: {metrics_summary['avg_serialization_time_ms']:.3f}ms")
        print(f"Current serializer: {self._current_serializer}")
        print(f"Estimated FPS capability: {metrics_summary['estimated_fps_capability']:.1f}")
        
        # Serialization comparison
        serialization_metrics = report.get('serialization_metrics', {})
        if serialization_metrics:
            print(f"\nSerialization Performance:")
            for method_name, metrics in serialization_metrics.items():
                print(f"  {method_name}: {metrics['avg_time_ms']:.3f}ms avg, {metrics['total_calls']} calls")
        
        # Recommendations
        recommendations = report.get('recommendations', [])
        if recommendations:
            print(f"\nRecommendations:")
            for rec in recommendations:
                print(f"  • {rec}")
        
        print("=" * 50 + "\n")
    
    # Inherit networking methods from base class
    def _create_udp_socket(self) -> bool:
        """Create UDP client socket."""
        try:
            self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_socket.setblocking(False)
            return True
        except Exception as e:
            print(f"[BeysionUnityAdapterOptimized] Failed to create UDP socket: {e}")
            return False
    
    def _create_tcp_server(self) -> bool:
        """Create TCP server socket."""
        try:
            self._tcp_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._tcp_server_socket.bind((self._tcp_host, self._tcp_port))
            self._tcp_server_socket.listen(1)
            self._tcp_server_socket.setblocking(False)
            return True
        except Exception as e:
            print(f"[BeysionUnityAdapterOptimized] Failed to create TCP server: {e}")
            return False
    
    def _send_udp_message(self, message: Union[str, bytes]) -> bool:
        """Send UDP message to Unity."""
        try:
            if not self._udp_socket:
                return False
            
            if isinstance(message, str):
                data = message.encode('utf-8')
            else:
                data = message
            
            self._udp_socket.sendto(data, (self._udp_host, self._udp_port))
            return True
            
        except socket.error as e:
            if e.errno != socket.EWOULDBLOCK:
                print(f"[BeysionUnityAdapterOptimized] UDP send error: {e}")
            return False
        except Exception as e:
            print(f"[BeysionUnityAdapterOptimized] UDP send unexpected error: {e}")
            return False
    
    def _start_tcp_thread(self) -> None:
        """Start TCP command handling thread."""
        self._tcp_thread = threading.Thread(
            target=self._tcp_command_loop,
            daemon=True,
            name="UnityAdapter-TCP"
        )
        self._tcp_thread.start()
    
    def _tcp_command_loop(self) -> None:
        """TCP command handling loop."""
        while not self._stop_threads.is_set():
            try:
                # Handle new connections
                if self._tcp_client_socket is None:
                    try:
                        if self._tcp_server_socket:
                            client_socket, addr = self._tcp_server_socket.accept()
                            client_socket.setblocking(False)
                            with self._tcp_lock:
                                self._tcp_client_socket = client_socket
                            print(f"[BeysionUnityAdapterOptimized] Unity connected from {addr}")
                    except BlockingIOError:
                        pass
                    except Exception as e:
                        print(f"[BeysionUnityAdapterOptimized] TCP accept error: {e}")
                
                # Handle existing connection
                if self._tcp_client_socket is not None:
                    try:
                        data = self._tcp_client_socket.recv(1024)
                        if not data:
                            with self._tcp_lock:
                                self._tcp_client_socket.close()
                                self._tcp_client_socket = None
                        else:
                            response = self._process_unity_command(data.decode('utf-8').strip())
                            if response:
                                self._tcp_client_socket.send(response.encode('utf-8'))
                    except BlockingIOError:
                        pass
                    except ConnectionResetError:
                        with self._tcp_lock:
                            if self._tcp_client_socket:
                                self._tcp_client_socket.close()
                                self._tcp_client_socket = None
                    except Exception as e:
                        print(f"[BeysionUnityAdapterOptimized] TCP client error: {e}")
                
                time.sleep(0.001)  # 1ms sleep
                
            except Exception as e:
                print(f"[BeysionUnityAdapterOptimized] TCP loop error: {e}")
                time.sleep(0.1)
    
    def _process_unity_command(self, command: str) -> Optional[str]:
        """Process Unity command."""
        if command == "calibrate":
            if self._command_callback:
                self._command_callback("calibrate", self)
            return "calibrated"
        elif command == "threshold_up":
            if self._command_callback:
                new_threshold = self._command_callback("threshold_up", self)
                return f"threshold:{new_threshold}"
            return "threshold:16"
        elif command == "threshold_down":
            if self._command_callback:
                new_threshold = self._command_callback("threshold_down", self)
                return f"threshold:{new_threshold}"
            return "threshold:14"
        else:
            return None
    
    def _launch_unity_client(self) -> bool:
        """Launch Unity client executable."""
        # Implementation similar to base class
        if not self._unity_executable_path:
            possible_paths = [
                Path.cwd() / "beysion-unity-DO_NOT_MODIFY" / "beysion-unity-backup.exe",
                Path.cwd().parent / "beysion-unity-DO_NOT_MODIFY" / "beysion-unity-backup.exe",
            ]
            
            for path in possible_paths:
                if path.exists():
                    self._unity_executable_path = str(path)
                    break
            else:
                return False
        
        try:
            self._unity_process = subprocess.Popen([self._unity_executable_path])
            print(f"[BeysionUnityAdapterOptimized] Launched Unity client: PID {self._unity_process.pid}")
            return True
        except Exception as e:
            print(f"[BeysionUnityAdapterOptimized] Failed to launch Unity client: {e}")
            return False
    
    def _is_unity_running(self) -> bool:
        """Check if Unity client process is running."""
        if not self._unity_process:
            return False
        return self._unity_process.poll() is None
    
    def _cleanup_udp_socket(self) -> None:
        """Clean up UDP socket."""
        if self._udp_socket:
            try:
                self._udp_socket.close()
            except:
                pass
            self._udp_socket = None
    
    def _cleanup_tcp_resources(self) -> None:
        """Clean up TCP resources."""
        with self._tcp_lock:
            if self._tcp_client_socket:
                try:
                    self._tcp_client_socket.close()
                except:
                    pass
                self._tcp_client_socket = None
            
            if self._tcp_server_socket:
                try:
                    self._tcp_server_socket.close()
                except:
                    pass
                self._tcp_server_socket = None
    
    def _cleanup_all_resources(self) -> None:
        """Clean up all resources."""
        self._cleanup_udp_socket()
        self._cleanup_tcp_resources()
    
    def send_projection_config(self, width: int, height: int) -> bool:
        """Send projection config (placeholder for interface compliance)."""
        print(f"[BeysionUnityAdapterOptimized] Projection config: {width}×{height}")
        return True
    
    def get_client_info(self) -> Optional[Dict[str, Any]]:
        """Get comprehensive client information including performance metrics."""
        if not self.is_connected():
            return None
        
        base_info = {
            'client_type': 'Unity',
            'protocol_version': 'optimized_localhost',
            'udp_endpoint': f"{self._udp_host}:{self._udp_port}",
            'tcp_endpoint': f"{self._tcp_host}:{self._tcp_port}",
            'current_serializer': self._current_serializer,
            'batching_enabled': self.enable_batching,
            'profiling_enabled': self.enable_profiling,
            'auto_optimize_enabled': self.auto_optimize,
            'unity_process_running': self._is_unity_running(),
            'tcp_client_connected': self._tcp_client_socket is not None
        }
        
        # Add performance metrics
        performance_summary = self._metrics.get_performance_summary()
        base_info.update(performance_summary)
        
        return base_info
    
    def set_command_callback(self, callback: callable) -> None:
        """Set callback function for handling Unity commands."""
        self._command_callback = callback 