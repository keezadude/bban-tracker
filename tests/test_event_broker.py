"""
Unit tests for the EventBroker implementation.

These tests verify the core functionality of the event-driven architecture,
including publish/subscribe mechanics, thread safety, and performance characteristics.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch
from concurrent.futures import Future

from core.event_broker import EventBroker, DependencyContainer
from core.events import TrackingDataUpdated, ChangeTrackerSettings, BeyData, HitData


class TestEventBroker:
    """Test suite for EventBroker functionality."""
    
    def setup_method(self):
        """Set up fresh EventBroker for each test."""
        self.broker = EventBroker(max_workers=2, max_queue_size=100)
        self.received_events = []
        self.handler_call_count = 0
        
    def teardown_method(self):
        """Clean up EventBroker after each test."""
        if hasattr(self, 'broker'):
            self.broker.shutdown()
    
    def test_basic_publish_subscribe(self):
        """Test basic event publishing and subscription."""
        # Set up handler
        def handler(event):
            self.received_events.append(event)
            self.handler_call_count += 1
        
        # Subscribe and publish
        sub_id = self.broker.subscribe(ChangeTrackerSettings, handler)
        event = ChangeTrackerSettings(threshold=25)
        self.broker.publish(event)
        
        # Wait for delivery
        time.sleep(0.1)
        
        # Verify
        assert len(self.received_events) == 1
        assert self.received_events[0].threshold == 25
        assert self.handler_call_count == 1
        assert isinstance(sub_id, str)
    
    def test_multiple_subscribers_same_event(self):
        """Test multiple subscribers to the same event type."""
        received_1 = []
        received_2 = []
        
        def handler1(event):
            received_1.append(event)
        
        def handler2(event):
            received_2.append(event)
        
        # Subscribe both handlers
        sub1 = self.broker.subscribe(ChangeTrackerSettings, handler1)
        sub2 = self.broker.subscribe(ChangeTrackerSettings, handler2)
        
        # Publish event
        event = ChangeTrackerSettings(threshold=30)
        self.broker.publish(event)
        
        # Wait for delivery
        time.sleep(0.1)
        
        # Verify both received the event
        assert len(received_1) == 1
        assert len(received_2) == 1
        assert received_1[0].threshold == 30
        assert received_2[0].threshold == 30
    
    def test_unsubscribe(self):
        """Test unsubscribing from events."""
        def handler(event):
            self.received_events.append(event)
        
        # Subscribe and verify
        sub_id = self.broker.subscribe(ChangeTrackerSettings, handler)
        assert self.broker.get_subscriber_count(ChangeTrackerSettings) == 1
        
        # Unsubscribe and verify
        result = self.broker.unsubscribe(sub_id)
        assert result is True
        assert self.broker.get_subscriber_count(ChangeTrackerSettings) == 0
        
        # Publish after unsubscribe - should not be received
        event = ChangeTrackerSettings(threshold=40)
        self.broker.publish(event)
        time.sleep(0.1)
        
        assert len(self.received_events) == 0
    
    def test_unsubscribe_invalid_id(self):
        """Test unsubscribing with invalid subscription ID."""
        result = self.broker.unsubscribe("invalid-id")
        assert result is False
    
    def test_publish_no_subscribers(self):
        """Test publishing when no subscribers exist."""
        # Should not raise any exception
        event = ChangeTrackerSettings(threshold=50)
        self.broker.publish(event)
        time.sleep(0.1)
        
        # Verify no errors occurred
        stats = self.broker.get_event_statistics()
        assert stats['error_count'] == 0
    
    def test_event_type_isolation(self):
        """Test that events are only delivered to subscribers of the correct type."""
        tracker_events = []
        tracking_events = []
        
        def tracker_handler(event):
            tracker_events.append(event)
        
        def tracking_handler(event):
            tracking_events.append(event)
        
        # Subscribe to different event types
        self.broker.subscribe(ChangeTrackerSettings, tracker_handler)
        self.broker.subscribe(TrackingDataUpdated, tracking_handler)
        
        # Publish different event types
        tracker_event = ChangeTrackerSettings(threshold=60)
        tracking_event = TrackingDataUpdated(frame_id=1, beys=[], hits=[])
        
        self.broker.publish(tracker_event)
        self.broker.publish(tracking_event)
        
        time.sleep(0.1)
        
        # Verify proper isolation
        assert len(tracker_events) == 1
        assert len(tracking_events) == 1
        assert tracker_events[0].threshold == 60
        assert tracking_events[0].frame_id == 1
    
    def test_thread_safety(self):
        """Test thread safety with concurrent publish/subscribe operations."""
        results = []
        lock = threading.Lock()
        
        def handler(event):
            with lock:
                results.append(event.threshold)
        
        # Subscribe
        self.broker.subscribe(ChangeTrackerSettings, handler)
        
        # Publish from multiple threads
        def publisher(start_value):
            for i in range(10):
                event = ChangeTrackerSettings(threshold=start_value + i)
                self.broker.publish(event)
        
        threads = []
        for start in [0, 100, 200]:
            thread = threading.Thread(target=publisher, args=(start,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Wait for event delivery
        time.sleep(0.5)
        
        # Verify all events were received
        assert len(results) == 30
        # Verify we got the expected values (order may vary due to threading)
        expected_values = set(range(0, 10)) | set(range(100, 110)) | set(range(200, 210))
        assert set(results) == expected_values
    
    def test_error_isolation(self):
        """Test that handler errors don't crash the broker."""
        good_events = []
        
        def failing_handler(event):
            raise ValueError("Handler error")
        
        def good_handler(event):
            good_events.append(event)
        
        # Subscribe both handlers
        self.broker.subscribe(ChangeTrackerSettings, failing_handler)
        self.broker.subscribe(ChangeTrackerSettings, good_handler)
        
        # Publish event
        event = ChangeTrackerSettings(threshold=70)
        self.broker.publish(event)
        
        time.sleep(0.1)
        
        # Verify good handler still worked despite error in other handler
        assert len(good_events) == 1
        assert good_events[0].threshold == 70
        
        # Verify error was tracked
        stats = self.broker.get_event_statistics()
        assert stats['error_count'] > 0
    
    def test_performance_statistics(self):
        """Test performance statistics collection."""
        def handler(event):
            pass
        
        # Subscribe and publish some events
        self.broker.subscribe(ChangeTrackerSettings, handler)
        
        for i in range(5):
            event = ChangeTrackerSettings(threshold=i)
            self.broker.publish(event)
        
        time.sleep(0.2)
        
        # Get stats
        stats = self.broker.get_event_statistics()
        
        # Verify basic statistics
        assert stats['total_events_published'] == 5
        assert stats['active_subscriptions'] == 1
        assert 'events_per_second' in stats
        assert 'average_delivery_time_ms' in stats
        assert 'uptime_seconds' in stats
    
    def test_clear_all_subscriptions(self):
        """Test clearing all subscriptions."""
        def handler(event):
            pass
        
        # Add multiple subscriptions
        self.broker.subscribe(ChangeTrackerSettings, handler)
        self.broker.subscribe(TrackingDataUpdated, handler)
        
        assert self.broker.get_subscriber_count(ChangeTrackerSettings) == 1
        assert self.broker.get_subscriber_count(TrackingDataUpdated) == 1
        
        # Clear all
        self.broker.clear_all_subscriptions()
        
        assert self.broker.get_subscriber_count(ChangeTrackerSettings) == 0
        assert self.broker.get_subscriber_count(TrackingDataUpdated) == 0
    
    def test_shutdown_graceful(self):
        """Test graceful shutdown behavior."""
        def handler(event):
            time.sleep(0.1)  # Simulate some work
        
        self.broker.subscribe(ChangeTrackerSettings, handler)
        
        # Publish event
        event = ChangeTrackerSettings(threshold=80)
        self.broker.publish(event)
        
        # Shutdown should wait for delivery to complete
        start_time = time.perf_counter()
        self.broker.shutdown()
        shutdown_time = time.perf_counter() - start_time
        
        # Should have waited for handler to complete
        assert shutdown_time >= 0.1
        
        # After shutdown, publishing should be ignored
        self.broker.publish(ChangeTrackerSettings(threshold=90))
        # No assertion needed - just verify no exception


class TestDependencyContainer:
    """Test suite for DependencyContainer functionality."""
    
    def setup_method(self):
        """Set up fresh container for each test."""
        self.container = DependencyContainer()
    
    def test_register_and_resolve_singleton(self):
        """Test registering and resolving singleton instances."""
        # Create mock instance
        mock_service = Mock()
        
        # Register as singleton
        self.container.register_singleton(type(mock_service), mock_service)
        
        # Resolve and verify same instance returned
        resolved1 = self.container.resolve(type(mock_service))
        resolved2 = self.container.resolve(type(mock_service))
        
        assert resolved1 is mock_service
        assert resolved2 is mock_service
        assert resolved1 is resolved2
    
    def test_register_and_resolve_transient(self):
        """Test registering and resolving transient instances."""
        # Create factory function
        def factory():
            return Mock()
        
        # Register as transient
        self.container.register_transient(Mock, factory)
        
        # Resolve and verify different instances returned
        resolved1 = self.container.resolve(Mock)
        resolved2 = self.container.resolve(Mock)
        
        assert resolved1 is not resolved2
        assert type(resolved1) == type(Mock())
        assert type(resolved2) == type(Mock())
    
    def test_is_registered(self):
        """Test checking if types are registered."""
        # Initially not registered
        assert not self.container.is_registered(Mock)
        
        # Register and check
        self.container.register_singleton(Mock, Mock())
        assert self.container.is_registered(Mock)
    
    def test_resolve_unregistered_type(self):
        """Test resolving unregistered type raises error."""
        with pytest.raises(ValueError, match="No registration found"):
            self.container.resolve(Mock)
    
    def test_thread_safety(self):
        """Test thread safety of dependency container."""
        instances = []
        lock = threading.Lock()
        
        def factory():
            return Mock()
        
        def register_and_resolve():
            # Register in each thread
            self.container.register_transient(Mock, factory)
            instance = self.container.resolve(Mock)
            with lock:
                instances.append(instance)
        
        # Run from multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=register_and_resolve)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify all threads got instances
        assert len(instances) == 5
        # All should be different instances due to transient registration
        assert len(set(id(i) for i in instances)) == 5


# ==================== PERFORMANCE TESTS ==================== #

class TestEventBrokerPerformance:
    """Performance-focused tests for EventBroker."""
    
    def setup_method(self):
        """Set up EventBroker for performance testing."""
        self.broker = EventBroker(max_workers=4, max_queue_size=10000)
        
    def teardown_method(self):
        """Clean up EventBroker."""
        if hasattr(self, 'broker'):
            self.broker.shutdown()
    
    def test_high_throughput_publishing(self):
        """Test high-throughput event publishing performance."""
        received_count = 0
        lock = threading.Lock()
        
        def handler(event):
            nonlocal received_count
            with lock:
                received_count += 1
        
        self.broker.subscribe(ChangeTrackerSettings, handler)
        
        # Publish many events quickly
        start_time = time.perf_counter()
        num_events = 1000
        
        for i in range(num_events):
            event = ChangeTrackerSettings(threshold=i % 100)
            self.broker.publish(event)
        
        publish_time = time.perf_counter() - start_time
        
        # Wait for all events to be delivered
        time.sleep(1.0)
        
        # Verify performance
        assert received_count == num_events
        events_per_second = num_events / publish_time
        print(f"Publishing rate: {events_per_second:.0f} events/second")
        
        # Should be able to publish at least 10,000 events per second
        assert events_per_second > 10000
    
    def test_latency_measurement(self):
        """Test end-to-end event delivery latency."""
        latencies = []
        
        def handler(event):
            receive_time = time.perf_counter()
            latency = receive_time - event.timestamp
            latencies.append(latency * 1000)  # Convert to milliseconds
        
        self.broker.subscribe(TrackingDataUpdated, handler)
        
        # Send events and measure latency
        for i in range(100):
            event = TrackingDataUpdated(frame_id=i, beys=[], hits=[])
            self.broker.publish(event)
            time.sleep(0.01)  # Small gap between events
        
        # Wait for all deliveries
        time.sleep(0.5)
        
        # Analyze latency
        assert len(latencies) == 100
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        
        print(f"Average latency: {avg_latency:.2f}ms, Max latency: {max_latency:.2f}ms")
        
        # Latency should be reasonable for real-time system
        assert avg_latency < 1.0  # Average under 1ms
        assert max_latency < 10.0  # Max under 10ms 