"""
Performance profiler for Unity ↔ bban-tracker communication optimization.

This module implements Recommendations 1 and 2 from localhost optimization analysis:
1. Profile CPU Usage of Serialization/Deserialization  
2. Batch Events per Frame for optimal localhost performance

Designed specifically for localhost (127.0.0.1) where CPU is the primary bottleneck,
not network bandwidth or latency.
"""

import cProfile
import pstats
import time
import json
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Union
from collections import defaultdict
from statistics import mean, median, stdev
from pathlib import Path
import msgpack

from .shared_memory_protocol import ProtocolSerializer, SharedMemoryFrame, create_shared_memory_frame


@dataclass
class SerializationMetrics:
    """Detailed metrics for serialization performance analysis."""
    operation_name: str
    total_calls: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    max_time_ms: float = 0.0
    call_times: List[float] = field(default_factory=list)
    payload_sizes: List[int] = field(default_factory=list)
    
    def add_measurement(self, time_ms: float, payload_size_bytes: int = 0):
        """Add a performance measurement."""
        self.total_calls += 1
        self.total_time_ms += time_ms
        self.min_time_ms = min(self.min_time_ms, time_ms)
        self.max_time_ms = max(self.max_time_ms, time_ms)
        
        # Rolling window to prevent memory growth
        self.call_times.append(time_ms)
        if len(self.call_times) > 1000:
            self.call_times.pop(0)
            
        if payload_size_bytes > 0:
            self.payload_sizes.append(payload_size_bytes)
            if len(self.payload_sizes) > 1000:
                self.payload_sizes.pop(0)
    
    @property
    def avg_time_ms(self) -> float:
        """Average execution time in milliseconds."""
        return self.total_time_ms / self.total_calls if self.total_calls > 0 else 0.0
    
    @property
    def median_time_ms(self) -> float:
        """Median execution time in milliseconds."""
        return median(self.call_times) if self.call_times else 0.0
    
    @property
    def std_dev_ms(self) -> float:
        """Standard deviation of execution times."""
        return stdev(self.call_times) if len(self.call_times) > 1 else 0.0
    
    @property
    def avg_payload_size(self) -> float:
        """Average payload size in bytes."""
        return mean(self.payload_sizes) if self.payload_sizes else 0.0
    
    @property
    def calls_per_second(self) -> float:
        """Estimated calls per second based on recent performance."""
        if not self.call_times:
            return 0.0
        avg_time_s = self.avg_time_ms / 1000.0
        return 1.0 / avg_time_s if avg_time_s > 0 else 0.0


@dataclass 
class BatchingMetrics:
    """Metrics for event batching performance."""
    frames_batched: int = 0
    events_per_batch: List[int] = field(default_factory=list)
    batch_processing_times: List[float] = field(default_factory=list)
    bandwidth_saved_bytes: int = 0
    cpu_time_saved_ms: float = 0.0
    
    def add_batch(self, event_count: int, processing_time_ms: float, bytes_saved: int = 0):
        """Record a batch processing event."""
        self.frames_batched += 1
        self.events_per_batch.append(event_count)
        self.batch_processing_times.append(processing_time_ms)
        self.bandwidth_saved_bytes += bytes_saved
        
        # Rolling window
        if len(self.events_per_batch) > 500:
            self.events_per_batch.pop(0)
        if len(self.batch_processing_times) > 500:
            self.batch_processing_times.pop(0)
    
    @property
    def avg_events_per_batch(self) -> float:
        """Average number of events per batch."""
        return mean(self.events_per_batch) if self.events_per_batch else 0.0
    
    @property
    def avg_batch_time_ms(self) -> float:
        """Average batch processing time."""
        return mean(self.batch_processing_times) if self.batch_processing_times else 0.0


class EventBatcher:
    """Event batching system for high-frequency localhost optimization."""
    
    def __init__(self, max_batch_size: int = 10, max_batch_age_ms: float = 16.67):
        """
        Initialize event batcher.
        
        Args:
            max_batch_size: Maximum events per batch
            max_batch_age_ms: Maximum age before forcing batch flush (default: 1 frame @ 60 FPS)
        """
        self.max_batch_size = max_batch_size
        self.max_batch_age_ms = max_batch_age_ms
        
        self._pending_events: List[Dict[str, Any]] = []
        self._batch_start_time: Optional[float] = None
        self._lock = threading.RLock()
        self._batch_callback: Optional[Callable] = None
        
        # Performance metrics
        self.metrics = BatchingMetrics()
    
    def set_batch_callback(self, callback: Callable[[List[Dict[str, Any]]], bool]):
        """Set callback function for processing batched events."""
        self._batch_callback = callback
    
    def add_event(self, event_data: Dict[str, Any]) -> bool:
        """
        Add event to batch. Returns True if batch was flushed.
        
        Args:
            event_data: Event data to batch
            
        Returns:
            True if batch was processed and flushed
        """
        with self._lock:
            # Initialize batch timing
            if not self._pending_events:
                self._batch_start_time = time.perf_counter()
            
            self._pending_events.append(event_data)
            
            # Check flush conditions
            should_flush = (
                len(self._pending_events) >= self.max_batch_size or
                self._is_batch_aged()
            )
            
            if should_flush:
                return self._flush_batch()
            
            return False
    
    def force_flush(self) -> bool:
        """Force flush current batch regardless of size/age."""
        with self._lock:
            return self._flush_batch()
    
    def _is_batch_aged(self) -> bool:
        """Check if current batch has exceeded max age."""
        if not self._batch_start_time:
            return False
        
        age_ms = (time.perf_counter() - self._batch_start_time) * 1000
        return age_ms >= self.max_batch_age_ms
    
    def _flush_batch(self) -> bool:
        """Internal method to flush current batch."""
        if not self._pending_events or not self._batch_callback:
            return False
        
        batch_start = time.perf_counter()
        event_count = len(self._pending_events)
        
        try:
            # Process batch
            success = self._batch_callback(self._pending_events.copy())
            
            # Record metrics
            processing_time = (time.perf_counter() - batch_start) * 1000
            self.metrics.add_batch(event_count, processing_time)
            
            # Clear batch
            self._pending_events.clear()
            self._batch_start_time = None
            
            return success
            
        except Exception as e:
            print(f"[EventBatcher] Error processing batch: {e}")
            # Clear failed batch to prevent backing up
            self._pending_events.clear()
            self._batch_start_time = None
            return False


class PerformanceProfiler:
    """Main performance profiler for Unity ↔ tracker communication."""
    
    def __init__(self, enable_cpu_profiling: bool = True, enable_batching: bool = True):
        """
        Initialize performance profiler.
        
        Args:
            enable_cpu_profiling: Enable detailed CPU profiling
            enable_batching: Enable event batching optimization
        """
        self.enable_cpu_profiling = enable_cpu_profiling
        self.enable_batching = enable_batching
        
        # Profiling components
        self.event_batcher = EventBatcher() if enable_batching else None
        
        # Metrics storage
        self.serialization_metrics: Dict[str, SerializationMetrics] = {}
        self._lock = threading.RLock()
    
    def profile_serialization(self, operation_name: str, 
                            serializer_func: Callable, 
                            data: Any, 
                            *args, **kwargs) -> tuple:
        """
        Profile a serialization operation with detailed metrics.
        
        Args:
            operation_name: Name for metrics tracking (e.g., "json_serialize", "msgpack_serialize")
            serializer_func: Function to profile
            data: Data to serialize
            
        Returns:
            (result, execution_time_ms)
        """
        start_time = time.perf_counter()
        
        try:
            result = serializer_func(data, *args, **kwargs)
            
            # Calculate metrics
            execution_time = (time.perf_counter() - start_time) * 1000
            payload_size = len(result) if isinstance(result, (bytes, str)) else 0
            
            # Store metrics
            with self._lock:
                if operation_name not in self.serialization_metrics:
                    self.serialization_metrics[operation_name] = SerializationMetrics(operation_name)
                
                self.serialization_metrics[operation_name].add_measurement(execution_time, payload_size)
            
            return result, execution_time
            
        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            print(f"[PerformanceProfiler] Error in {operation_name}: {e}")
            raise
    
    def compare_serializers(self, test_data: Any, iterations: int = 100) -> Dict[str, SerializationMetrics]:
        """
        Compare different serialization methods for the same data.
        
        Args:
            test_data: Data to use for comparison testing
            iterations: Number of test iterations
            
        Returns:
            Dictionary of metrics for each serializer
        """
        print(f"[PerformanceProfiler] Comparing serializers with {iterations} iterations...")
        
        # Test JSON serialization (current corrected adapter)
        def json_serialize(data):
            return json.dumps(data)
        
        def json_deserialize(data):
            return json.loads(data)
        
        # Test MessagePack serialization (shared memory adapter)
        def msgpack_serialize(data):
            return msgpack.packb(data, use_bin_type=True)
        
        def msgpack_deserialize(data):
            return msgpack.unpackb(data, raw=False)
        
        # Test custom string formatting (current main.py style)
        def custom_format_serialize(data):
            # Simulate the _format_tracking_message format
            if isinstance(data, dict) and 'beys' in data:
                msg = f"{data.get('frame_id', 0)}, beys:"
                for bey in data.get('beys', []):
                    msg += f"({bey.get('id', 0)}, {bey.get('pos_x', 0)}, {bey.get('pos_y', 0)})"
                msg += ", hits:"
                for hit in data.get('hits', []):
                    msg += f"({hit.get('pos_x', 0)}, {hit.get('pos_y', 0)})"
                return msg
            return str(data)
        
        # Prepare test data
        test_json_data = json.dumps(test_data) if not isinstance(test_data, str) else test_data
        test_msgpack_data = msgpack.packb(test_data, use_bin_type=True) if not isinstance(test_data, bytes) else test_data
        
        # Test serialization performance
        for i in range(iterations):
            # JSON tests
            self.profile_serialization('json_serialize', json_serialize, test_data)
            if isinstance(test_json_data, str):
                self.profile_serialization('json_deserialize', json_deserialize, test_json_data)
            
            # MessagePack tests
            self.profile_serialization('msgpack_serialize', msgpack_serialize, test_data)
            self.profile_serialization('msgpack_deserialize', msgpack_deserialize, test_msgpack_data)
            
            # Custom format test
            self.profile_serialization('custom_format', custom_format_serialize, test_data)
        
        return self.serialization_metrics.copy()
    
    def create_test_frame_data(self, num_beys: int = 2, num_hits: int = 1) -> Dict[str, Any]:
        """Create realistic test data for profiling."""
        return {
            'frame_id': 12345,
            'timestamp': time.perf_counter(),
            'beys': [
                {
                    'id': i,
                    'pos_x': float(100 + i * 50),
                    'pos_y': float(200 + i * 30),
                    'velocity_x': 2.5,
                    'velocity_y': 1.8,
                    'raw_velocity_x': 2.7,
                    'raw_velocity_y': 1.9,
                    'acceleration_x': 0.1,
                    'acceleration_y': 0.05,
                    'width': 20,
                    'height': 20,
                    'frame': 12345
                }
                for i in range(num_beys)
            ],
            'hits': [
                {
                    'pos_x': float(150 + i * 40),
                    'pos_y': float(220 + i * 35),
                    'width': 15,
                    'height': 15,
                    'bey_id_1': 0,
                    'bey_id_2': 1,
                    'is_new_hit': True
                }
                for i in range(num_hits)
            ]
        }
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        with self._lock:
            report = {
                'timestamp': time.perf_counter(),
                'serialization_metrics': {},
                'batching_metrics': None,
                'recommendations': []
            }
            
            # Serialization performance
            for name, metrics in self.serialization_metrics.items():
                report['serialization_metrics'][name] = {
                    'total_calls': metrics.total_calls,
                    'avg_time_ms': metrics.avg_time_ms,
                    'median_time_ms': metrics.median_time_ms,
                    'std_dev_ms': metrics.std_dev_ms,
                    'min_time_ms': metrics.min_time_ms,
                    'max_time_ms': metrics.max_time_ms,
                    'avg_payload_size_bytes': metrics.avg_payload_size,
                    'estimated_fps_limit': metrics.calls_per_second
                }
            
            # Batching metrics
            if self.event_batcher:
                batch_metrics = self.event_batcher.metrics
                report['batching_metrics'] = {
                    'frames_batched': batch_metrics.frames_batched,
                    'avg_events_per_batch': batch_metrics.avg_events_per_batch,
                    'avg_batch_time_ms': batch_metrics.avg_batch_time_ms,
                    'bandwidth_saved_bytes': batch_metrics.bandwidth_saved_bytes
                }
            
            # Generate recommendations based on data
            report['recommendations'] = self._generate_recommendations()
            
            return report
    
    def _generate_recommendations(self) -> List[str]:
        """Generate optimization recommendations based on profiling data."""
        recommendations = []
        
        with self._lock:
            # Analyze serialization performance
            if self.serialization_metrics:
                # Find slowest serializer
                slowest_time = 0
                slowest_name = ""
                fastest_time = float('inf')
                fastest_name = ""
                
                for name, metrics in self.serialization_metrics.items():
                    if 'serialize' in name and metrics.avg_time_ms > slowest_time:
                        slowest_time = metrics.avg_time_ms
                        slowest_name = name
                    
                    if 'serialize' in name and metrics.avg_time_ms < fastest_time:
                        fastest_time = metrics.avg_time_ms
                        fastest_name = name
                
                if slowest_name and fastest_name and slowest_name != fastest_name:
                    improvement = ((slowest_time - fastest_time) / slowest_time) * 100
                    recommendations.append(
                        f"Switch from {slowest_name} to {fastest_name} for {improvement:.1f}% performance improvement"
                    )
                
                # Check if any serializer is too slow for real-time
                target_frame_time = 16.67  # 60 FPS
                for name, metrics in self.serialization_metrics.items():
                    if metrics.avg_time_ms > target_frame_time * 0.1:  # Using more than 10% of frame time
                        recommendations.append(
                            f"{name} is using {metrics.avg_time_ms:.2f}ms per call - consider optimization for 60 FPS target"
                        )
            
            # Batching recommendations
            if self.event_batcher and self.event_batcher.metrics.frames_batched > 0:
                avg_batch_size = self.event_batcher.metrics.avg_events_per_batch
                if avg_batch_size < 2:
                    recommendations.append("Event batching is underutilized - consider increasing batch size or timeout")
                elif avg_batch_size > 8:
                    recommendations.append("Large event batches detected - may cause frame stutter, consider smaller batches")
        
        return recommendations
    
    def save_report(self, filepath: Union[str, Path]) -> None:
        """Save performance report to file."""
        report = self.get_performance_report()
        filepath = Path(filepath)
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"[PerformanceProfiler] Report saved to {filepath}")


# Global profiler instance for easy access
_global_profiler: Optional[PerformanceProfiler] = None

def get_global_profiler() -> PerformanceProfiler:
    """Get or create global performance profiler instance."""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = PerformanceProfiler()
    return _global_profiler

def profile_serialization(operation_name: str, serializer_func: Callable, data: Any, *args, **kwargs):
    """Convenience function for profiling serialization operations."""
    return get_global_profiler().profile_serialization(operation_name, serializer_func, data, *args, **kwargs) 