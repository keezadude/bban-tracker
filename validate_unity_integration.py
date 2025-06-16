#!/usr/bin/env python3
"""
Unity Integration Validation Test

This test validates the corrected BeysionUnityAdapter integration with the 
BBAN-Tracker EDA system and ensures optimal performance for Unity special effects.

Test Categories:
1. Protocol Compatibility Verification
2. Network Performance Analysis  
3. EDA Integration Testing
4. Bottleneck Detection
5. Unity Communication Simulation
"""

import time
import socket
import threading
import statistics
from dataclasses import dataclass
from typing import List, Dict, Any

# Import the corrected adapter and EDA components
from adapters.beysion_unity_adapter_corrected import BeysionUnityAdapterCorrected
from core.event_broker import EventBroker
from core.events import BeyData, HitData


@dataclass
class TestResult:
    """Test result with pass/fail status and performance metrics."""
    test_name: str
    passed: bool
    message: str
    performance_data: Dict[str, Any] = None


class UnityIntegrationValidator:
    """Comprehensive validation test suite for Unity integration."""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.event_broker = None
        self.adapter = None
        
    def run_all_tests(self) -> bool:
        """Run all validation tests and return overall pass/fail status."""
        print("🚀 Unity Integration Validation Test Suite")
        print("=" * 60)
        
        try:
            # Test 1: Protocol Compatibility
            self._test_protocol_compatibility()
            
            # Test 2: Network Performance
            self._test_network_performance()
            
            # Test 3: EDA Integration
            self._test_eda_integration()
            
            # Test 4: Unity Communication Simulation
            self._test_unity_communication_simulation()
            
            # Test 5: Bottleneck Detection
            self._test_bottleneck_detection()
            
            # Generate final report
            return self._generate_final_report()
            
        except Exception as e:
            print(f"❌ Critical test failure: {e}")
            return False
    
    def _test_protocol_compatibility(self) -> None:
        """Test 1: Verify protocol compatibility with Unity expectations."""
        print("\n📋 Test 1: Protocol Compatibility Verification")
        
        # Test UDP/TCP port configuration
        try:
            adapter = BeysionUnityAdapterCorrected()
            
            # Verify default ports match Unity expectations
            udp_port_correct = adapter._udp_port == 50007
            tcp_port_correct = adapter._tcp_port == 50008
            
            self.results.append(TestResult(
                test_name="UDP Port Configuration",
                passed=udp_port_correct,
                message=f"UDP port: {adapter._udp_port} (expected: 50007)"
            ))
            
            self.results.append(TestResult(
                test_name="TCP Port Configuration", 
                passed=tcp_port_correct,
                message=f"TCP port: {adapter._tcp_port} (expected: 50008)"
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                test_name="Adapter Initialization",
                passed=False,
                message=f"Failed to initialize adapter: {e}"
            ))
        
        # Test message format compatibility
        try:
            adapter = BeysionUnityAdapterCorrected()
            
            # Create test data
            test_beys = [
                BeyData(id=1, pos=(250, 180), velocity=(5.0, -2.0), raw_velocity=(5.1, -1.9), 
                       acceleration=(0.1, 0.2), shape=(20, 20), frame=100),
                BeyData(id=2, pos=(300, 220), velocity=(-3.0, 4.0), raw_velocity=(-2.9, 4.1),
                       acceleration=(-0.1, -0.1), shape=(18, 18), frame=100)
            ]
            
            test_hits = [
                HitData(pos=(275, 200), shape=(15, 15), bey_ids=(1, 2), is_new_hit=True)
            ]
            
            # Test message formatting
            message = adapter._format_tracking_message(1234, test_beys, test_hits)
            
            # Verify message format
            expected_parts = ["1234, beys:", "(1, 250, 180)", "(2, 300, 220)", ", hits:", "(275, 200)"]
            format_correct = all(part in message for part in expected_parts)
            
            self.results.append(TestResult(
                test_name="Message Format Compatibility",
                passed=format_correct,
                message=f"Generated: {message[:100]}..." if len(message) > 100 else f"Generated: {message}"
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                test_name="Message Format Generation",
                passed=False,
                message=f"Failed to generate message: {e}"
            ))
    
    def _test_network_performance(self) -> None:
        """Test 2: Analyze network performance characteristics."""
        print("\n⚡ Test 2: Network Performance Analysis")
        
        try:
            adapter = BeysionUnityAdapterCorrected()
            
            # Test UDP socket creation performance
            udp_create_times = []
            for _ in range(100):
                start_time = time.perf_counter()
                adapter._create_udp_socket()
                create_time = (time.perf_counter() - start_time) * 1000
                udp_create_times.append(create_time)
                if adapter._udp_socket:
                    adapter._udp_socket.close()
            
            avg_udp_create_time = statistics.mean(udp_create_times)
            max_udp_create_time = max(udp_create_times)
            
            performance_acceptable = avg_udp_create_time < 1.0  # Less than 1ms average
            
            self.results.append(TestResult(
                test_name="UDP Socket Creation Performance",
                passed=performance_acceptable,
                message=f"Average: {avg_udp_create_time:.3f}ms, Max: {max_udp_create_time:.3f}ms",
                performance_data={
                    'avg_time_ms': avg_udp_create_time,
                    'max_time_ms': max_udp_create_time,
                    'target_ms': 1.0
                }
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                test_name="Network Performance Analysis",
                passed=False,
                message=f"Performance test failed: {e}"
            ))
    
    def _test_eda_integration(self) -> None:
        """Test 3: Verify EDA integration and event handling."""
        print("\n🔄 Test 3: EDA Integration Testing")
        
        try:
            # Create EDA components
            self.event_broker = EventBroker(max_workers=2, max_queue_size=1000)
            self.adapter = BeysionUnityAdapterCorrected()
            
            # Test command callback integration
            callback_called = False
            callback_command = None
            callback_result = None
            
            def test_callback(command: str, adapter) -> str:
                nonlocal callback_called, callback_command, callback_result
                callback_called = True
                callback_command = command
                if command == "calibrate":
                    callback_result = "calibrated"
                elif command == "threshold_up":
                    callback_result = "threshold:16"
                elif command == "threshold_down":
                    callback_result = "threshold:14"
                else:
                    callback_result = "unknown"
                return callback_result
            
            # Set callback and test
            self.adapter.set_command_callback(test_callback)
            
            # Test calibration command
            result = self.adapter._process_unity_command("calibrate")
            calibrate_test_passed = (callback_called and 
                                   callback_command == "calibrate" and 
                                   result == "calibrated")
            
            self.results.append(TestResult(
                test_name="Command Callback Integration",
                passed=calibrate_test_passed,
                message=f"Callback called: {callback_called}, Command: {callback_command}, Result: {result}"
            ))
            
            # Reset for threshold test
            callback_called = False
            callback_command = None
            
            # Test threshold command
            result = self.adapter._process_unity_command("threshold_up")
            threshold_test_passed = (callback_called and 
                                   callback_command == "threshold_up" and 
                                   result == "threshold:16")
            
            self.results.append(TestResult(
                test_name="Threshold Command Processing",
                passed=threshold_test_passed,
                message=f"Callback called: {callback_called}, Command: {callback_command}, Result: {result}"
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                test_name="EDA Integration",
                passed=False,
                message=f"EDA integration test failed: {e}"
            ))
    
    def _test_unity_communication_simulation(self) -> None:
        """Test 4: Simulate Unity communication patterns."""
        print("\n🎮 Test 4: Unity Communication Simulation")
        
        try:
            # Test high-frequency message sending (90 FPS simulation)
            adapter = BeysionUnityAdapterCorrected()
            
            # Create test tracking data
            test_beys = [
                BeyData(id=1, pos=(250, 180), velocity=(5.0, -2.0), raw_velocity=(5.1, -1.9),
                       acceleration=(0.1, 0.2), shape=(20, 20), frame=100)
            ]
            test_hits = [
                HitData(pos=(275, 200), shape=(15, 15), bey_ids=(1, 2), is_new_hit=True)
            ]
            
            # Test message formatting performance at 90 FPS
            format_times = []
            for frame_id in range(90):  # Simulate 1 second at 90 FPS
                start_time = time.perf_counter()
                message = adapter._format_tracking_message(frame_id, test_beys, test_hits)
                format_time = (time.perf_counter() - start_time) * 1000
                format_times.append(format_time)
            
            avg_format_time = statistics.mean(format_times)
            max_format_time = max(format_times)
            
            # Performance targets for 90 FPS (11.1ms budget per frame)
            format_acceptable = avg_format_time < 0.5  # Should be under 0.5ms
            max_acceptable = max_format_time < 2.0    # Max should be under 2ms
            
            self.results.append(TestResult(
                test_name="90 FPS Message Formatting",
                passed=format_acceptable and max_acceptable,
                message=f"Avg: {avg_format_time:.3f}ms, Max: {max_format_time:.3f}ms (target: <0.5ms avg, <2ms max)",
                performance_data={
                    'avg_time_ms': avg_format_time,
                    'max_time_ms': max_format_time,
                    'target_avg_ms': 0.5,
                    'target_max_ms': 2.0
                }
            ))
            
        except Exception as e:
            self.results.append(TestResult(
                test_name="Unity Communication Simulation",
                passed=False,
                message=f"Communication simulation failed: {e}"
            ))
    
    def _test_bottleneck_detection(self) -> None:
        """Test 5: Detect potential performance bottlenecks."""
        print("\n🔍 Test 5: Bottleneck Detection Analysis")
        
        try:
            # Test memory allocation patterns
            adapter = BeysionUnityAdapterCorrected()
            
            # Simulate heavy load scenario
            large_bey_list = []
            for i in range(10):  # 10 beys (stress test)
                large_bey_list.append(
                    BeyData(id=i, pos=(250+i*10, 180+i*5), velocity=(5.0, -2.0), 
                           raw_velocity=(5.1, -1.9), acceleration=(0.1, 0.2), 
                           shape=(20, 20), frame=100)
                )
            
            large_hit_list = []
            for i in range(5):  # 5 hits (stress test)
                large_hit_list.append(
                    HitData(pos=(275+i*15, 200+i*10), shape=(15, 15), 
                           bey_ids=(i, i+1), is_new_hit=True)
                )
            
            # Test high-load message formatting
            start_time = time.perf_counter()
            large_message = adapter._format_tracking_message(9999, large_bey_list, large_hit_list)
            high_load_time = (time.perf_counter() - start_time) * 1000
            
            # Analyze message size
            message_size = len(large_message.encode('utf-8'))
            
            # Bottleneck thresholds
            time_acceptable = high_load_time < 5.0    # Should handle heavy load in <5ms
            size_acceptable = message_size < 1000     # Should stay under 1KB per message
            
            self.results.append(TestResult(
                test_name="High Load Bottleneck Analysis",
                passed=time_acceptable and size_acceptable,
                message=f"Time: {high_load_time:.3f}ms, Size: {message_size} bytes (10 beys, 5 hits)",
                performance_data={
                    'processing_time_ms': high_load_time,
                    'message_size_bytes': message_size,
                    'bey_count': 10,
                    'hit_count': 5
                }
            ))
            
            # Test networking overhead
            network_overhead_test = self._test_network_overhead()
            self.results.append(network_overhead_test)
            
        except Exception as e:
            self.results.append(TestResult(
                test_name="Bottleneck Detection",
                passed=False,
                message=f"Bottleneck detection failed: {e}"
            ))
    
    def _test_network_overhead(self) -> TestResult:
        """Test network overhead and latency characteristics."""
        try:
            # Test localhost UDP round-trip simulation
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            test_socket.bind(('127.0.0.1', 0))  # Bind to available port
            test_port = test_socket.getsockname()[1]
            
            # Test message sending overhead
            test_message = "1234, beys:(1, 250, 180)(2, 300, 220), hits:(275, 200)"
            test_data = test_message.encode('utf-8')
            
            send_times = []
            for _ in range(100):
                start_time = time.perf_counter()
                test_socket.sendto(test_data, ('127.0.0.1', test_port))
                send_time = (time.perf_counter() - start_time) * 1000
                send_times.append(send_time)
            
            test_socket.close()
            
            avg_send_time = statistics.mean(send_times)
            max_send_time = max(send_times)
            
            # Network overhead should be minimal
            overhead_acceptable = avg_send_time < 0.1  # Target <0.1ms average
            
            return TestResult(
                test_name="Network Overhead Analysis",
                passed=overhead_acceptable,
                message=f"UDP send overhead - Avg: {avg_send_time:.4f}ms, Max: {max_send_time:.4f}ms",
                performance_data={
                    'avg_send_time_ms': avg_send_time,
                    'max_send_time_ms': max_send_time,
                    'target_ms': 0.1
                }
            )
            
        except Exception as e:
            return TestResult(
                test_name="Network Overhead Analysis",
                passed=False,
                message=f"Network overhead test failed: {e}"
            )
    
    def _generate_final_report(self) -> bool:
        """Generate final validation report and return overall status."""
        print("\n" + "=" * 60)
        print("📊 FINAL VALIDATION REPORT")
        print("=" * 60)
        
        passed_tests = sum(1 for result in self.results if result.passed)
        total_tests = len(self.results)
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"Overall Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
        print()
        
        # Detailed results
        for result in self.results:
            status_icon = "✅" if result.passed else "❌"
            print(f"{status_icon} {result.test_name}")
            print(f"   {result.message}")
            
            if result.performance_data:
                print(f"   Performance: {result.performance_data}")
            print()
        
        # Performance summary
        self._print_performance_summary()
        
        # Final assessment
        all_tests_passed = all(result.passed for result in self.results)
        critical_performance_met = self._check_critical_performance()
        
        overall_success = all_tests_passed and critical_performance_met
        
        print("=" * 60)
        if overall_success:
            print("🚀 VALIDATION RESULT: ✅ PASS")
            print("   Unity integration ready for production!")
            print("   No bottlenecks detected for 90 FPS special effects.")
        else:
            print("❌ VALIDATION RESULT: ❌ FAIL")
            print("   Issues detected that may impact Unity performance.")
            
        print("=" * 60)
        
        return overall_success
    
    def _print_performance_summary(self) -> None:
        """Print summary of performance metrics."""
        print("🚀 PERFORMANCE SUMMARY:")
        
        performance_results = [r for r in self.results if r.performance_data]
        
        for result in performance_results:
            perf = result.performance_data
            if 'avg_time_ms' in perf:
                target = perf.get('target_ms', perf.get('target_avg_ms', 'N/A'))
                status = "✅ GOOD" if result.passed else "⚠️ CONCERN"
                print(f"   {result.test_name}: {perf['avg_time_ms']:.3f}ms avg (target: {target}ms) {status}")
        
        print()
    
    def _check_critical_performance(self) -> bool:
        """Check if critical performance requirements are met."""
        critical_tests = [
            "90 FPS Message Formatting",
            "High Load Bottleneck Analysis", 
            "Network Overhead Analysis"
        ]
        
        critical_results = [r for r in self.results if r.test_name in critical_tests]
        return all(result.passed for result in critical_results)


def main():
    """Run the Unity integration validation test suite."""
    validator = UnityIntegrationValidator()
    success = validator.run_all_tests()
    
    exit_code = 0 if success else 1
    exit(exit_code)


if __name__ == "__main__":
    main() 