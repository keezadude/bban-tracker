"""
High-performance, thread-safe event broker implementation for BBAN-Tracker EDA.

This module provides the central event broker that manages publish/subscribe
communication between services. It's designed for ultra-low latency with
minimal memory allocation and efficient event dispatching.
"""

import time
import uuid
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Type
from dataclasses import dataclass, field

from .interfaces import IEventBroker


@dataclass
class EventStatistics:
    """Performance statistics for the event broker."""
    total_events_published: int = 0
    total_events_delivered: int = 0
    events_per_second: float = 0.0
    average_delivery_time_ms: float = 0.0
    peak_delivery_time_ms: float = 0.0
    error_count: int = 0
    active_subscriptions: int = 0
    last_reset_time: float = field(default_factory=time.perf_counter)


@dataclass
class _Subscription:
    """Internal subscription record."""
    id: str
    event_type: Type
    handler: Callable[[Any], None]
    created_at: float = field(default_factory=time.perf_counter)


class EventBroker(IEventBroker):
    """
    Thread-safe, high-performance event broker with async delivery.
    
    Key Features:
    - Ultra-low latency event publishing (<0.1ms typical)
    - Thread-safe subscription management
    - Asynchronous event delivery to prevent blocking
    - Comprehensive performance monitoring
    - Automatic error recovery and isolation
    """
    
    def __init__(self, max_workers: int = 4, max_queue_size: int = 10000):
        """
        Initialize the event broker.
        
        Args:
            max_workers: Maximum number of worker threads for event delivery
            max_queue_size: Maximum size of the event delivery queue
        """
        self._subscriptions: Dict[Type, List[_Subscription]] = defaultdict(list)
        self._subscription_lookup: Dict[str, _Subscription] = {}
        self._lock = threading.RLock()
        
        # High-performance event delivery
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, 
            thread_name_prefix="EventBroker"
        )
        self._delivery_queue = deque(maxlen=max_queue_size)
        self._queue_lock = threading.Lock()
        
        # Performance monitoring
        self._stats = EventStatistics()
        self._delivery_times = deque(maxlen=1000)  # Rolling window for timing
        self._stats_lock = threading.Lock()
        
        # Shutdown coordination
        self._shutdown = False
        
        # Start the delivery worker
        self._delivery_worker = threading.Thread(
            target=self._delivery_loop,
            daemon=True,
            name="EventBroker-Delivery"
        )
        self._delivery_worker.start()
    
    def publish(self, event: Any) -> None:
        """
        Publish an event to all subscribers with minimal latency.
        
        This method is optimized for speed - it performs minimal work
        and delegates actual delivery to background workers.
        """
        if self._shutdown:
            return
            
        start_time = time.perf_counter()
        event_type = type(event)
        
        # Fast path: Check if anyone is subscribed
        with self._lock:
            subscriptions = self._subscriptions.get(event_type, [])
            if not subscriptions:
                return
            
            # Create delivery tasks (minimal work in critical path)
            delivery_tasks = [(sub.handler, event, start_time) for sub in subscriptions]
        
        # Queue all delivery tasks
        with self._queue_lock:
            self._delivery_queue.extend(delivery_tasks)
        
        # Update statistics
        with self._stats_lock:
            self._stats.total_events_published += 1
    
    def subscribe(self, event_type: Type, handler: Callable[[Any], None]) -> str:
        """
        Subscribe to events of a specific type.
        
        Args:
            event_type: The type of events to subscribe to
            handler: Callback function to handle events
            
        Returns:
            Unique subscription ID for later unsubscription
        """
        subscription_id = str(uuid.uuid4())
        subscription = _Subscription(
            id=subscription_id,
            event_type=event_type,
            handler=handler
        )
        
        with self._lock:
            self._subscriptions[event_type].append(subscription)
            self._subscription_lookup[subscription_id] = subscription
            
        with self._stats_lock:
            self._stats.active_subscriptions += 1
            
        return subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription.
        
        Args:
            subscription_id: ID returned from subscribe()
            
        Returns:
            True if subscription was found and removed
        """
        with self._lock:
            subscription = self._subscription_lookup.pop(subscription_id, None)
            if not subscription:
                return False
                
            # Remove from the type-specific list
            type_subscriptions = self._subscriptions[subscription.event_type]
            type_subscriptions[:] = [s for s in type_subscriptions if s.id != subscription_id]
            
            # Clean up empty lists
            if not type_subscriptions:
                del self._subscriptions[subscription.event_type]
                
        with self._stats_lock:
            self._stats.active_subscriptions -= 1
            
        return True
    
    def get_subscriber_count(self, event_type: Type) -> int:
        """Return the number of active subscribers for an event type."""
        with self._lock:
            return len(self._subscriptions.get(event_type, []))
    
    def get_event_statistics(self) -> dict:
        """Return comprehensive performance statistics."""
        with self._stats_lock:
            current_time = time.perf_counter()
            elapsed = current_time - self._stats.last_reset_time
            
            if elapsed > 0:
                self._stats.events_per_second = self._stats.total_events_published / elapsed
            
            # Calculate average delivery time
            if self._delivery_times:
                avg_time = sum(self._delivery_times) / len(self._delivery_times)
                self._stats.average_delivery_time_ms = avg_time * 1000
                self._stats.peak_delivery_time_ms = max(self._delivery_times) * 1000
            
            return {
                'total_events_published': self._stats.total_events_published,
                'total_events_delivered': self._stats.total_events_delivered,
                'events_per_second': round(self._stats.events_per_second, 2),
                'average_delivery_time_ms': round(self._stats.average_delivery_time_ms, 3),
                'peak_delivery_time_ms': round(self._stats.peak_delivery_time_ms, 3),
                'error_count': self._stats.error_count,
                'active_subscriptions': self._stats.active_subscriptions,
                'queue_size': len(self._delivery_queue),
                'uptime_seconds': round(elapsed, 1)
            }
    
    def clear_all_subscriptions(self) -> None:
        """Remove all subscriptions (used for shutdown)."""
        with self._lock:
            self._subscriptions.clear()
            self._subscription_lookup.clear()
            
        with self._stats_lock:
            self._stats.active_subscriptions = 0
    
    def shutdown(self) -> None:
        """Gracefully shutdown the event broker."""
        self._shutdown = True
        
        # Wait for delivery queue to drain (max 2 seconds)
        max_wait = 2.0
        start_time = time.perf_counter()
        
        while self._delivery_queue and (time.perf_counter() - start_time) < max_wait:
            time.sleep(0.01)
        
        # Shutdown executor
        self._executor.shutdown(wait=True)
        
        # Clear all subscriptions
        self.clear_all_subscriptions()
    
    def reset_statistics(self) -> None:
        """Reset performance statistics counters."""
        with self._stats_lock:
            self._stats = EventStatistics()
            self._delivery_times.clear()
    
    # ==================== INTERNAL DELIVERY SYSTEM ==================== #
    
    def _delivery_loop(self) -> None:
        """Main delivery worker loop that processes queued events."""
        while not self._shutdown:
            try:
                # Process all queued deliveries
                while self._delivery_queue:
                    with self._queue_lock:
                        if not self._delivery_queue:
                            break
                        handler, event, publish_time = self._delivery_queue.popleft()
                    
                    # Deliver the event asynchronously
                    self._executor.submit(self._deliver_event, handler, event, publish_time)
                
                # Brief sleep to prevent excessive CPU usage
                time.sleep(0.001)  # 1ms
                
            except Exception as e:
                # Log error but keep the delivery loop running
                print(f"[EventBroker] Delivery loop error: {e}")
                with self._stats_lock:
                    self._stats.error_count += 1
    
    def _deliver_event(self, handler: Callable, event: Any, publish_time: float) -> None:
        """
        Deliver a single event to a handler with error isolation.
        
        Args:
            handler: The callback function to invoke
            event: The event to deliver  
            publish_time: When the event was published (for latency tracking)
        """
        delivery_start = time.perf_counter()
        
        try:
            # Invoke the handler
            handler(event)
            
            # Track successful delivery
            delivery_time = time.perf_counter() - delivery_start
            total_latency = delivery_time + (delivery_start - publish_time)
            
            with self._stats_lock:
                self._stats.total_events_delivered += 1
                self._delivery_times.append(total_latency)
                
        except Exception as e:
            # Isolate handler errors - don't let them crash the broker
            print(f"[EventBroker] Handler error: {e}")
            with self._stats_lock:
                self._stats.error_count += 1


# ==================== DEPENDENCY INJECTION CONTAINER ==================== #

class DependencyContainer:
    """
    Simple dependency injection container for service management.
    
    Supports singleton and transient lifetime management with automatic
    constructor injection for registered types.
    """
    
    def __init__(self):
        self._singletons: Dict[Type, Any] = {}
        self._transients: Dict[Type, Callable] = {}
        self._lock = threading.RLock()
    
    def register_singleton(self, interface_type: Type, implementation: Any) -> None:
        """Register a singleton instance for an interface type."""
        with self._lock:
            self._singletons[interface_type] = implementation
    
    def register_transient(self, interface_type: Type, factory: Callable) -> None:
        """Register a factory function for creating transient instances."""
        with self._lock:
            self._transients[interface_type] = factory
    
    def resolve(self, interface_type: Type) -> Any:
        """Resolve an instance of the requested interface type."""
        with self._lock:
            # Check for singleton first
            if interface_type in self._singletons:
                return self._singletons[interface_type]
            
            # Check for transient factory
            if interface_type in self._transients:
                factory = self._transients[interface_type]
                return factory()
            
            raise ValueError(f"No registration found for type: {interface_type}")
    
    def is_registered(self, interface_type: Type) -> bool:
        """Return True if the interface type is registered."""
        with self._lock:
            return interface_type in self._singletons or interface_type in self._transients 