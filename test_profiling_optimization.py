#!/usr/bin/env python3
"""
Test script for Recommendations 1 and 2: CPU Profiling and Event Batching Optimization.

This script demonstrates the localhost optimization analysis for Unity ↔ bban-tracker communication.
It profiles different serialization methods and tests event batching performance.
"""

import time
import json
import sys
import os
from pathlib import Path
from typing import List, Dict, Any

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    import msgpack
except ImportError:
    print("MessagePack not available, installing...")
    os.system("pip install msgpack")
    import msgpack

# Import our profiling system
from adapters.performance_profiler import PerformanceProfiler, get_global_profiler


class MockBeyData:
    """Mock BeyData for testing."""
    def __init__(self, id: int, x: float, y: float, frame: int):
        self.id = id
        self.pos = (x, y)
        self.velocity = (2.5, 1.8)
        self.raw_velocity = (2.7, 1.9)
        self.acceleration = (0.1, 0.05)
        self.shape = (20, 20)
        self.frame = frame
    
    def getId(self):
        return self.id
    
    def getPos(self):
        return self.pos
    
    def getVel(self):
        return self.velocity
    
    def getRawVel(self):
        return self.raw_velocity
    
    def getAcc(self):
        return self.acceleration
    
    def getShape(self):
        return self.shape
    
    def getFrame(self):
        return self.frame


class MockHitData:
    """Mock HitData for testing."""
    def __init__(self, x: float, y: float, is_new: bool = True):
        self.pos = (x, y)
        self.shape = (15, 15)
        self.is_new_hit = is_new
        self.bey_ids = (0, 1)
    
    def getPos(self):
        return self.pos
    
    def getShape(self):
        return self.shape
    
    def isNewHit(self):
        return self.is_new_hit


def create_test_data(num_beys: int = 2, num_hits: int = 1, frame_id: int = 12345) -> tuple:
    """Create realistic test data for profiling."""
    beys = [
        MockBeyData(
            id=i,
            x=100.0 + i * 50.0,
            y=200.0 + i * 30.0,
            frame=frame_id
        )
        for i in range(num_beys)
    ]
    
    hits = [
        MockHitData(
            x=150.0 + i * 40.0,
            y=220.0 + i * 35.0,
            is_new=True
        )
        for i in range(num_hits)
    ]
    
    return beys, hits


def test_json_serialization(beys: List[MockBeyData], hits: List[MockHitData], frame_id: int) -> str:
    """Test JSON serialization (current corrected adapter approach)."""
    data = {
        'frame_id': frame_id,
        'timestamp': time.perf_counter(),
        'beys': [
            {
                'id': bey.getId(),
                'pos_x': bey.getPos()[0],
                'pos_y': bey.getPos()[1],
                'velocity_x': bey.getVel()[0],
                'velocity_y': bey.getVel()[1],
                'raw_velocity_x': bey.getRawVel()[0],
                'raw_velocity_y': bey.getRawVel()[1],
                'acceleration_x': bey.getAcc()[0],
                'acceleration_y': bey.getAcc()[1],
                'width': bey.getShape()[0],
                'height': bey.getShape()[1],
                'frame': bey.getFrame()
            }
            for bey in beys
        ],
        'hits': [
            {
                'pos_x': hit.getPos()[0],
                'pos_y': hit.getPos()[1],
                'width': hit.getShape()[0],
                'height': hit.getShape()[1],
                'is_new_hit': hit.isNewHit()
            }
            for hit in hits
        ]
    }
    return json.dumps(data)


def test_msgpack_serialization(beys: List[MockBeyData], hits: List[MockHitData], frame_id: int) -> bytes:
    """Test MessagePack serialization (shared memory adapter approach)."""
    data = {
        'frame_id': frame_id,
        'timestamp': time.perf_counter(),
        'beys': [
            {
                'id': bey.getId(),
                'pos_x': bey.getPos()[0],
                'pos_y': bey.getPos()[1],
                'velocity_x': bey.getVel()[0],
                'velocity_y': bey.getVel()[1],
                'raw_velocity_x': bey.getRawVel()[0],
                'raw_velocity_y': bey.getRawVel()[1],
                'acceleration_x': bey.getAcc()[0],
                'acceleration_y': bey.getAcc()[1],
                'width': bey.getShape()[0],
                'height': bey.getShape()[1],
                'frame': bey.getFrame()
            }
            for bey in beys
        ],
        'hits': [
            {
                'pos_x': hit.getPos()[0],
                'pos_y': hit.getPos()[1],
                'width': hit.getShape()[0],
                'height': hit.getShape()[1],
                'is_new_hit': hit.isNewHit()
            }
            for hit in hits
        ]
    }
    return msgpack.packb(data, use_bin_type=True)


def test_custom_format_serialization(beys: List[MockBeyData], hits: List[MockHitData], frame_id: int) -> str:
    """Test custom string formatting (main.py compatible approach)."""
    message = f"{frame_id}, beys:"
    
    for bey in beys:
        bey_id = bey.getId()
        x, y = bey.getPos()
        message += f"({bey_id}, {x}, {y})"
    
    message += ", hits:"
    
    for hit in hits:
        if hit.isNewHit():
            x, y = hit.getPos()
            message += f"({x}, {y})"
    
    return message


def run_serialization_benchmark(iterations: int = 1000, num_beys: int = 2, num_hits: int = 1):
    """Run comprehensive serialization benchmark."""
    print(f"\n{'='*60}")
    print(f"SERIALIZATION PERFORMANCE BENCHMARK")
    print(f"Iterations: {iterations}, Beys: {num_beys}, Hits: {num_hits}")
    print(f"Target: 60 FPS (16.67ms frame budget)")
    print(f"{'='*60}")
    
    # Get profiler
    profiler = get_global_profiler()
    
    # Create test data
    beys, hits = create_test_data(num_beys, num_hits)
    
    print(f"\nRunning {iterations} iterations for each serialization method...")
    
    # Test JSON serialization
    for i in range(iterations):
        frame_id = 10000 + i
        beys, hits = create_test_data(num_beys, num_hits, frame_id)
        profiler.profile_serialization("json_serialize", test_json_serialization, beys, hits, frame_id)
    
    # Test MessagePack serialization
    for i in range(iterations):
        frame_id = 10000 + i
        beys, hits = create_test_data(num_beys, num_hits, frame_id)
        profiler.profile_serialization("msgpack_serialize", test_msgpack_serialization, beys, hits, frame_id)
    
    # Test custom format serialization
    for i in range(iterations):
        frame_id = 10000 + i
        beys, hits = create_test_data(num_beys, num_hits, frame_id)
        profiler.profile_serialization("custom_format", test_custom_format_serialization, beys, hits, frame_id)
    
    # Test deserialization
    json_sample = test_json_serialization(*create_test_data(num_beys, num_hits), 12345)
    msgpack_sample = test_msgpack_serialization(*create_test_data(num_beys, num_hits), 12345)
    
    for i in range(iterations):
        profiler.profile_serialization("json_deserialize", json.loads, json_sample)
        profiler.profile_serialization("msgpack_deserialize", msgpack.unpackb, msgpack_sample, raw=False)
    
    # Generate performance report
    report = profiler.get_performance_report()
    
    print(f"\n{'='*60}")
    print(f"SERIALIZATION PERFORMANCE RESULTS")
    print(f"{'='*60}")
    
    # Sort by performance
    serialization_metrics = report.get('serialization_metrics', {})
    serialize_results = []
    deserialize_results = []
    
    for method_name, metrics in serialization_metrics.items():
        if 'serialize' in method_name and 'deserialize' not in method_name:
            serialize_results.append((method_name, metrics))
        elif 'deserialize' in method_name:
            deserialize_results.append((method_name, metrics))
    
    # Sort by average time
    serialize_results.sort(key=lambda x: x[1]['avg_time_ms'])
    deserialize_results.sort(key=lambda x: x[1]['avg_time_ms'])
    
    print(f"\nSERIALIZATION PERFORMANCE RANKING:")
    print(f"{'Method':<20} {'Avg Time':<12} {'Payload Size':<15} {'FPS Limit':<12} {'% of Frame':<12}")
    print(f"{'-'*75}")
    
    for method_name, metrics in serialize_results:
        avg_time = metrics['avg_time_ms']
        payload_size = metrics['avg_payload_size_bytes']
        fps_limit = metrics['estimated_fps_limit']
        frame_percent = (avg_time / 16.67) * 100  # % of 60 FPS frame
        
        print(f"{method_name:<20} {avg_time:<12.3f} {payload_size:<15.0f} {fps_limit:<12.0f} {frame_percent:<12.1f}%")
    
    print(f"\nDESERIALIZATION PERFORMANCE RANKING:")
    print(f"{'Method':<20} {'Avg Time':<12} {'FPS Limit':<12} {'% of Frame':<12}")
    print(f"{'-'*60}")
    
    for method_name, metrics in deserialize_results:
        avg_time = metrics['avg_time_ms']
        fps_limit = metrics['estimated_fps_limit']
        frame_percent = (avg_time / 16.67) * 100
        
        print(f"{method_name:<20} {avg_time:<12.3f} {fps_limit:<12.0f} {frame_percent:<12.1f}%")
    
    # Recommendations
    recommendations = report.get('recommendations', [])
    if recommendations:
        print(f"\n{'='*60}")
        print(f"OPTIMIZATION RECOMMENDATIONS")
        print(f"{'='*60}")
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec}")
    
    return report


def test_event_batching(batch_sizes: List[int] = [1, 3, 5, 10, 20], iterations_per_batch: int = 100):
    """Test event batching performance."""
    print(f"\n{'='*60}")
    print(f"EVENT BATCHING PERFORMANCE TEST")
    print(f"Batch sizes: {batch_sizes}")
    print(f"Iterations per batch size: {iterations_per_batch}")
    print(f"{'='*60}")
    
    profiler = get_global_profiler()
    
    results = {}
    
    for batch_size in batch_sizes:
        print(f"\nTesting batch size: {batch_size}")
        
        batch_times = []
        total_events = 0
        
        for iteration in range(iterations_per_batch):
            # Create a batch of events
            batch_events = []
            for i in range(batch_size):
                frame_id = iteration * batch_size + i
                beys, hits = create_test_data(2, 1, frame_id)
                
                event_data = {
                    'frame_id': frame_id,
                    'beys': beys,
                    'hits': hits,
                    'timestamp': time.perf_counter()
                }
                batch_events.append(event_data)
            
            # Time batch processing
            start_time = time.perf_counter()
            
            # Simulate batch serialization
            batch_message = {
                'type': 'batch',
                'count': len(batch_events),
                'events': batch_events
            }
            serialized = json.dumps(batch_message, default=str)  # Convert complex objects to strings
            
            # Simulate UDP send (just measure serialization + overhead)
            processing_time = (time.perf_counter() - start_time) * 1000
            batch_times.append(processing_time)
            total_events += batch_size
        
        # Calculate metrics
        avg_batch_time = sum(batch_times) / len(batch_times)
        avg_time_per_event = avg_batch_time / batch_size
        estimated_fps = 1000.0 / avg_batch_time if avg_batch_time > 0 else 0
        
        results[batch_size] = {
            'avg_batch_time_ms': avg_batch_time,
            'avg_time_per_event_ms': avg_time_per_event,
            'estimated_fps': estimated_fps,
            'total_events': total_events
        }
        
        print(f"  Avg batch time: {avg_batch_time:.3f}ms")
        print(f"  Avg time per event: {avg_time_per_event:.3f}ms")
        print(f"  Estimated FPS capability: {estimated_fps:.1f}")
    
    # Print comparison
    print(f"\n{'='*60}")
    print(f"BATCHING PERFORMANCE COMPARISON")
    print(f"{'='*60}")
    print(f"{'Batch Size':<12} {'Batch Time':<12} {'Per Event':<12} {'FPS Limit':<12} {'Efficiency':<12}")
    print(f"{'-'*65}")
    
    baseline_time = results[1]['avg_time_per_event_ms']  # Single event time
    
    for batch_size, metrics in results.items():
        batch_time = metrics['avg_batch_time_ms']
        per_event_time = metrics['avg_time_per_event_ms']
        fps_limit = metrics['estimated_fps']
        efficiency = (baseline_time / per_event_time) * 100 if per_event_time > 0 else 0
        
        print(f"{batch_size:<12} {batch_time:<12.3f} {per_event_time:<12.3f} {fps_limit:<12.1f} {efficiency:<12.1f}%")
    
    # Find optimal batch size
    best_batch_size = min(results.keys(), key=lambda bs: results[bs]['avg_time_per_event_ms'])
    best_metrics = results[best_batch_size]
    
    print(f"\n🏆 OPTIMAL BATCH SIZE: {best_batch_size}")
    print(f"   Per-event time: {best_metrics['avg_time_per_event_ms']:.3f}ms")
    print(f"   FPS capability: {best_metrics['estimated_fps']:.1f}")
    print(f"   Efficiency vs single: {(baseline_time / best_metrics['avg_time_per_event_ms']) * 100:.1f}%")
    
    return results


def simulate_real_time_performance(duration_seconds: int = 10, target_fps: int = 60):
    """Simulate real-time performance at target FPS."""
    print(f"\n{'='*60}")
    print(f"REAL-TIME PERFORMANCE SIMULATION")
    print(f"Duration: {duration_seconds} seconds at {target_fps} FPS")
    print(f"Target frame time: {1000/target_fps:.2f}ms")
    print(f"{'='*60}")
    
    profiler = get_global_profiler()
    frame_interval = 1.0 / target_fps
    
    frames_processed = 0
    frames_missed = 0
    total_processing_time = 0
    max_processing_time = 0
    min_processing_time = float('inf')
    
    start_time = time.perf_counter()
    last_frame_time = start_time
    
    print(f"Starting real-time simulation...")
    
    while time.perf_counter() - start_time < duration_seconds:
        frame_start = time.perf_counter()
        
        # Check if we're on schedule
        expected_frame_time = last_frame_time + frame_interval
        if frame_start < expected_frame_time:
            # Sleep until it's time for the next frame
            sleep_time = expected_frame_time - frame_start
            time.sleep(sleep_time)
            frame_start = time.perf_counter()
        
        # Process frame
        frame_id = frames_processed
        beys, hits = create_test_data(2, 1, frame_id)
        
        # Profile the serialization
        result, processing_time = profiler.profile_serialization("realtime_json", test_json_serialization, beys, hits, frame_id)
        
        frame_end = time.perf_counter()
        total_frame_time = (frame_end - frame_start) * 1000
        
        # Update statistics
        frames_processed += 1
        total_processing_time += processing_time
        max_processing_time = max(max_processing_time, processing_time)
        min_processing_time = min(min_processing_time, processing_time)
        
        # Check if we missed our frame deadline
        if total_frame_time > (1000 / target_fps):
            frames_missed += 1
        
        last_frame_time = frame_start
        
        # Print progress every second
        if frames_processed % target_fps == 0:
            seconds_elapsed = int((frame_end - start_time))
            avg_processing = total_processing_time / frames_processed
            print(f"  {seconds_elapsed}s: {frames_processed} frames, avg: {avg_processing:.3f}ms, missed: {frames_missed}")
    
    # Final results
    avg_processing_time = total_processing_time / frames_processed if frames_processed > 0 else 0
    miss_rate = (frames_missed / frames_processed) * 100 if frames_processed > 0 else 0
    actual_fps = frames_processed / duration_seconds
    
    print(f"\n📊 REAL-TIME PERFORMANCE RESULTS:")
    print(f"   Frames processed: {frames_processed}")
    print(f"   Frames missed: {frames_missed} ({miss_rate:.1f}%)")
    print(f"   Actual FPS: {actual_fps:.1f}")
    print(f"   Avg processing time: {avg_processing_time:.3f}ms")
    print(f"   Min processing time: {min_processing_time:.3f}ms")
    print(f"   Max processing time: {max_processing_time:.3f}ms")
    print(f"   CPU usage estimate: {(avg_processing_time / (1000/target_fps)) * 100:.1f}% of frame budget")
    
    # Performance assessment
    if miss_rate < 1:
        print(f"   ✅ Excellent: <1% frame drops")
    elif miss_rate < 5:
        print(f"   ⚠️  Good: <5% frame drops")
    elif miss_rate < 10:
        print(f"   ⚠️  Acceptable: <10% frame drops")
    else:
        print(f"   ❌ Poor: >10% frame drops")
    
    return {
        'frames_processed': frames_processed,
        'frames_missed': frames_missed,
        'miss_rate': miss_rate,
        'actual_fps': actual_fps,
        'avg_processing_time': avg_processing_time,
        'max_processing_time': max_processing_time,
        'min_processing_time': min_processing_time
    }


def main():
    """Main test function implementing Recommendations 1 and 2."""
    print("🚀 LOCALHOST OPTIMIZATION TESTING")
    print("Implementing Recommendations 1 & 2 from localhost analysis")
    print("1. Profile CPU Usage of Serialization/Deserialization")
    print("2. Batch Events per Frame for optimal localhost performance")
    
    try:
        # Recommendation 1: Profile CPU Usage
        print("\n🔍 RECOMMENDATION 1: CPU PROFILING")
        benchmark_report = run_serialization_benchmark(iterations=1000, num_beys=2, num_hits=1)
        
        # Recommendation 2: Batch Events per Frame
        print("\n📦 RECOMMENDATION 2: EVENT BATCHING")
        batching_results = test_event_batching(batch_sizes=[1, 3, 5, 10, 15], iterations_per_batch=100)
        
        # Real-time performance test
        print("\n⏱️  REAL-TIME PERFORMANCE VALIDATION")
        realtime_results = simulate_real_time_performance(duration_seconds=5, target_fps=60)
        
        # Final recommendations
        print(f"\n{'='*60}")
        print(f"🎯 FINAL OPTIMIZATION RECOMMENDATIONS")
        print(f"{'='*60}")
        
        # Analyze results and provide actionable recommendations
        serialization_metrics = benchmark_report.get('serialization_metrics', {})
        
        if serialization_metrics:
            # Find fastest serializer
            fastest_method = min(
                [m for m in serialization_metrics.keys() if 'serialize' in m and 'deserialize' not in m],
                key=lambda m: serialization_metrics[m]['avg_time_ms']
            )
            fastest_time = serialization_metrics[fastest_method]['avg_time_ms']
            
            print(f"1. 📈 SERIALIZATION: Use {fastest_method}")
            print(f"   - Average time: {fastest_time:.3f}ms")
            print(f"   - FPS capability: {serialization_metrics[fastest_method]['estimated_fps']:.0f}")
            print(f"   - CPU usage: {(fastest_time / 16.67) * 100:.1f}% of 60 FPS frame budget")
        
        # Find optimal batch size
        optimal_batch = min(batching_results.keys(), key=lambda bs: batching_results[bs]['avg_time_per_event_ms'])
        optimal_metrics = batching_results[optimal_batch]
        
        print(f"\n2. 📦 BATCHING: Use batch size {optimal_batch}")
        print(f"   - Per-event time: {optimal_metrics['avg_time_per_event_ms']:.3f}ms")
        print(f"   - FPS capability: {optimal_metrics['estimated_fps']:.0f}")
        print(f"   - Efficiency gain: {((batching_results[1]['avg_time_per_event_ms'] / optimal_metrics['avg_time_per_event_ms']) - 1) * 100:.1f}%")
        
        # Real-time assessment
        if realtime_results['miss_rate'] < 5:
            print(f"\n3. ✅ REAL-TIME: Current performance is suitable for 60 FPS")
            print(f"   - Frame miss rate: {realtime_results['miss_rate']:.1f}%")
            print(f"   - Average FPS: {realtime_results['actual_fps']:.1f}")
        else:
            print(f"\n3. ⚠️  REAL-TIME: Optimization needed for stable 60 FPS")
            print(f"   - Frame miss rate: {realtime_results['miss_rate']:.1f}%")
            print(f"   - Consider reducing data frequency or payload size")
        
        print(f"\n🏁 LOCALHOST OPTIMIZATION COMPLETE")
        print(f"Results saved to console. Integration into production adapters recommended.")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 