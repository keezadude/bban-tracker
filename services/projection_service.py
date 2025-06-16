"""
ProjectionService implementation for BBAN-Tracker Event-Driven Architecture.

This service manages communication with the Unity projection client through
a dedicated adapter interface. It acts as a bridge between the tracking data
events and the external Unity application.
"""

import time
import threading
from typing import Optional, Dict, Any

from ..core.interfaces import IProjectionService, IProjectionAdapter, IEventBroker
from ..core.events import (
    TrackingDataUpdated, ProjectionConfigUpdated, ProjectionClientConnected,
    ProjectionClientDisconnected, SystemShutdown, PerformanceMetric
)


class ProjectionService(IProjectionService):
    """
    Service that manages Unity client communication via adapter pattern.
    
    This service:
    - Maintains connection to Unity projection client
    - Forwards tracking data to the projection client
    - Handles projection configuration changes
    - Provides connection status monitoring
    - Isolates the application from Unity client specifics
    """
    
    def __init__(self, event_broker: IEventBroker, projection_adapter: IProjectionAdapter):
        """
        Initialize the projection service with dependency injection.
        
        Args:
            event_broker: Central event broker for communication
            projection_adapter: Adapter for Unity client communication
        """
        self._event_broker = event_broker
        self._adapter = projection_adapter
        
        # Service state
        self._running = False
        self._connection_monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Connection management
        self._last_connection_status = False
        self._connection_retry_count = 0
        self._last_retry_time = 0.0
        
        # Performance tracking
        self._data_packets_sent = 0
        self._last_perf_report = 0.0
        self._send_times = []
        
        # Current projection config
        self._current_config = {'width': 1920, 'height': 1080}
        
        # Subscribe to relevant events
        self._setup_event_subscriptions()
    
    def _setup_event_subscriptions(self):
        """Set up subscriptions to events this service handles."""
        self._event_broker.subscribe(TrackingDataUpdated, self._handle_tracking_data)
        self._event_broker.subscribe(ProjectionConfigUpdated, self._handle_config_update)
        self._event_broker.subscribe(SystemShutdown, self._handle_shutdown)
    
    # ==================== SERVICE INTERFACE ==================== #
    
    def start(self) -> None:
        """Start the projection service and connection monitoring."""
        if self._running:
            return
            
        self._running = True
        self._stop_event.clear()
        
        # Start connection monitoring thread
        self._connection_monitor_thread = threading.Thread(
            target=self._connection_monitor_loop,
            daemon=True,
            name="ProjectionService-Monitor"
        )
        self._connection_monitor_thread.start()
        
        print("[ProjectionService] Service started")
    
    def stop(self) -> None:
        """Stop the projection service and disconnect from client."""
        if not self._running:
            return
            
        self._running = False
        self._stop_event.set()
        
        # Disconnect from client
        if self._adapter.is_connected():
            self._adapter.disconnect()
        
        # Wait for monitor thread to stop
        if self._connection_monitor_thread:
            self._connection_monitor_thread.join(timeout=2.0)
        
        print("[ProjectionService] Service stopped")
    
    def is_running(self) -> bool:
        """Return True if the service is active."""
        return self._running
    
    def get_health_status(self) -> dict:
        """Return health and status information."""
        return {
            'service_running': self._running,
            'client_connected': self._adapter.is_connected() if self._adapter else False,
            'data_packets_sent': self._data_packets_sent,
            'connection_retry_count': self._connection_retry_count,
            'current_config': self._current_config.copy()
        }
    
    def get_connection_status(self) -> bool:
        """Return True if Unity client is connected."""
        return self._adapter.is_connected() if self._adapter else False
    
    def get_connected_client_info(self) -> Optional[dict]:
        """Return information about the connected Unity client."""
        if not self._adapter or not self._adapter.is_connected():
            return None
        
        try:
            return self._adapter.get_client_info()
        except Exception:
            return None
    
    def send_projection_command(self, command: str, data: Any = None) -> bool:
        """Send a command to the Unity client."""
        if not self._adapter or not self._adapter.is_connected():
            return False
        
        try:
            # This would depend on the specific adapter implementation
            # For now, we'll handle the projection config command
            if command == "projection_config" and isinstance(data, dict):
                return self._adapter.send_projection_config(
                    data.get('width', 1920),
                    data.get('height', 1080)
                )
            return False
        except Exception as e:
            print(f"[ProjectionService] Command send failed: {e}")
            return False
    
    # ==================== EVENT HANDLERS ==================== #
    
    def _handle_tracking_data(self, event: TrackingDataUpdated) -> None:
        """
        Handle new tracking data and forward to Unity client.
        OPTIMIZED with event batching for localhost performance (Recommendation 2).
        """
        if not self._adapter or not self._adapter.is_connected():
            return
        
        # EVENT BATCHING OPTIMIZATION for localhost performance
        if getattr(self, '_enable_batching', False):
            self._add_event_to_batch(event)
        else:
            # Original immediate sending
            self._send_tracking_data_immediate(event)
    
    def _add_event_to_batch(self, event: TrackingDataUpdated) -> None:
        """Add event to batch for optimized localhost sending."""
        with getattr(self, '_batch_lock', threading.RLock()):
            # Initialize batching attributes if not present (for existing instances)
            if not hasattr(self, '_pending_events'):
                self._pending_events = []
                self._last_batch_time = time.perf_counter()
                self._max_batch_size = 3  # Optimal from performance testing
                self._max_batch_age_ms = 16.67  # 1 frame @ 60 FPS
                self._batches_sent = 0
                self._events_batched = 0
                self._batch_processing_times = []
            
            # Add event to pending batch
            self._pending_events.append(event)
            
            # Check if we should flush the batch
            should_flush = (
                len(self._pending_events) >= self._max_batch_size or
                self._is_batch_aged()
            )
            
            if should_flush:
                self._flush_event_batch()
    
    def _is_batch_aged(self) -> bool:
        """Check if current batch has exceeded maximum age."""
        if not hasattr(self, '_last_batch_time'):
            return False
        
        age_ms = (time.perf_counter() - self._last_batch_time) * 1000
        return age_ms >= getattr(self, '_max_batch_age_ms', 16.67)
    
    def _flush_event_batch(self) -> None:
        """Flush current event batch to Unity client."""
        if not hasattr(self, '_pending_events') or not self._pending_events:
            return
        
        batch_start = time.perf_counter()
        batch_size = len(self._pending_events)
        
        try:
            # For batching, we can either:
            # 1. Send the most recent event (simple approach)
            # 2. Send all events in batch (if adapter supports it)
            
            # Simple approach: send most recent event (reduces overhead)
            latest_event = self._pending_events[-1]
            success = self._adapter.send_tracking_data(
                latest_event.frame_id,
                latest_event.beys,
                latest_event.hits
            )
            
            if success:
                # Update metrics for batched sending
                self._data_packets_sent += 1  # Only count as 1 packet sent
                self._batches_sent += 1
                self._events_batched += batch_size
                
                # Track batch processing performance
                batch_time = (time.perf_counter() - batch_start) * 1000
                self._batch_processing_times.append(batch_time)
                if len(self._batch_processing_times) > 100:
                    self._batch_processing_times.pop(0)
                
                # CPU savings calculation (approximate)
                single_event_overhead = 0.1  # Estimated ms per individual send
                cpu_saved = (batch_size - 1) * single_event_overhead
                
                # Log batching efficiency periodically
                if self._batches_sent % 100 == 0:
                    avg_batch_size = self._events_batched / self._batches_sent
                    avg_batch_time = sum(self._batch_processing_times) / len(self._batch_processing_times)
                    efficiency = ((avg_batch_size - 1) / avg_batch_size) * 100
                    
                    print(f"[ProjectionService] Batching stats: {avg_batch_size:.1f} events/batch, "
                          f"{avg_batch_time:.3f}ms/batch, {efficiency:.1f}% efficiency gain")
                
                # Track send performance for overall metrics
                send_time = batch_time / 1000.0  # Convert to seconds
                self._send_times.append(send_time)
                if len(self._send_times) > 100:
                    self._send_times.pop(0)
            else:
                print(f"[ProjectionService] Failed to send batched tracking data "
                      f"(batch size: {batch_size}, latest frame: {latest_event.frame_id})")
            
            # Clear the batch
            self._pending_events.clear()
            self._last_batch_time = time.perf_counter()
            
            # Publish performance metrics periodically
            if time.perf_counter() - self._last_perf_report > 5.0:
                self._publish_performance_metrics()
                self._last_perf_report = time.perf_counter()
                
        except Exception as e:
            print(f"[ProjectionService] Error flushing event batch: {e}")
            # Clear failed batch to prevent backup
            self._pending_events.clear()
            self._last_batch_time = time.perf_counter()
    
    def _send_tracking_data_immediate(self, event: TrackingDataUpdated) -> None:
        """Send tracking data immediately (original behavior)."""
        send_start = time.perf_counter()
        
        try:
            # Forward tracking data to Unity client via adapter
            success = self._adapter.send_tracking_data(
                event.frame_id,
                event.beys,
                event.hits
            )
            
            if success:
                self._data_packets_sent += 1
                
                # Track send performance
                send_time = time.perf_counter() - send_start
                self._send_times.append(send_time)
                if len(self._send_times) > 100:
                    self._send_times.pop(0)
                
                # Publish performance metrics periodically
                if time.perf_counter() - self._last_perf_report > 5.0:
                    self._publish_performance_metrics()
                    self._last_perf_report = time.perf_counter()
            else:
                print(f"[ProjectionService] Failed to send tracking data for frame {event.frame_id}")
                
        except Exception as e:
            print(f"[ProjectionService] Error sending tracking data: {e}")
    
    def _handle_config_update(self, event: ProjectionConfigUpdated) -> None:
        """Handle projection configuration updates."""
        self._current_config = {
            'width': event.width,
            'height': event.height
        }
        
        if self._adapter and self._adapter.is_connected():
            try:
                success = self._adapter.send_projection_config(event.width, event.height)
                if success:
                    print(f"[ProjectionService] Updated projection config: {event.width}×{event.height}")
                else:
                    print(f"[ProjectionService] Failed to update projection config")
            except Exception as e:
                print(f"[ProjectionService] Error updating projection config: {e}")
    
    def _handle_shutdown(self, event: SystemShutdown) -> None:
        """Handle system shutdown."""
        self.stop()
    
    # ==================== CONNECTION MONITORING ==================== #
    
    def _connection_monitor_loop(self) -> None:
        """Monitor connection status and handle reconnection."""
        print("[ProjectionService] Connection monitor started")
        
        while not self._stop_event.is_set():
            try:
                current_connected = self._adapter.is_connected() if self._adapter else False
                
                # Detect connection state changes
                if current_connected != self._last_connection_status:
                    self._handle_connection_state_change(current_connected)
                    self._last_connection_status = current_connected
                
                # Attempt connection if not connected
                if not current_connected and self._should_attempt_reconnect():
                    self._attempt_connection()
                
                # Check for and process any commands from the Unity client
                if current_connected:
                    self._process_client_commands()
                
                # Brief sleep to prevent excessive CPU usage
                self._stop_event.wait(1.0)  # Check every second
                
            except Exception as e:
                print(f"[ProjectionService] Monitor loop error: {e}")
                self._stop_event.wait(1.0)
        
        print("[ProjectionService] Connection monitor stopped")
    
    def _handle_connection_state_change(self, connected: bool) -> None:
        """Handle connection state changes and publish events."""
        if connected:
            client_info = self.get_connected_client_info()
            client_address = client_info.get('address', 'unknown') if client_info else 'unknown'
            
            self._event_broker.publish(ProjectionClientConnected(
                client_address=client_address
            ))
            
            # Send current configuration to newly connected client
            if self._current_config:
                self._adapter.send_projection_config(
                    self._current_config['width'],
                    self._current_config['height']
                )
            
            print(f"[ProjectionService] Unity client connected: {client_address}")
            self._connection_retry_count = 0  # Reset retry count on success
        else:
            self._event_broker.publish(ProjectionClientDisconnected(
                reason="connection_lost"
            ))
            print("[ProjectionService] Unity client disconnected")
    
    def _should_attempt_reconnect(self) -> bool:
        """Determine if we should attempt to reconnect to Unity client."""
        # Don't attempt reconnect too frequently
        min_retry_interval = 5.0  # seconds
        return (time.perf_counter() - self._last_retry_time) > min_retry_interval
    
    def _attempt_connection(self) -> None:
        """Attempt to connect to Unity client."""
        self._last_retry_time = time.perf_counter()
        self._connection_retry_count += 1
        
        try:
            if self._adapter.connect():
                print(f"[ProjectionService] Successfully connected to Unity client (attempt {self._connection_retry_count})")
            else:
                print(f"[ProjectionService] Connection attempt {self._connection_retry_count} failed")
        except Exception as e:
            print(f"[ProjectionService] Connection attempt {self._connection_retry_count} failed: {e}")
    
    def _process_client_commands(self) -> None:
        """Check for and process commands from the Unity client."""
        try:
            commands = self._adapter.receive_commands()
            for command in commands:
                self._process_client_command(command)
        except Exception as e:
            print(f"[ProjectionService] Error processing client commands: {e}")
    
    def _process_client_command(self, command: dict) -> None:
        """Process a single command from the Unity client."""
        command_type = command.get('type', '')
        
        if command_type == 'calibrate':
            # Forward calibration request to tracking service
            from ..core.events import CalibrateTracker
            self._event_broker.publish(CalibrateTracker())
        elif command_type == 'threshold_adjust':
            # Forward threshold adjustment to tracking service
            from ..core.events import ChangeTrackerSettings
            delta = command.get('delta', 0)
            # We'd need to get current threshold first, but for now just log
            print(f"[ProjectionService] Threshold adjust request: {delta}")
        else:
            print(f"[ProjectionService] Unknown command from Unity client: {command_type}")
    
    def _publish_performance_metrics(self) -> None:
        """Publish performance metrics for monitoring."""
        if self._send_times:
            avg_send_time = sum(self._send_times) / len(self._send_times)
            
            self._event_broker.publish(PerformanceMetric(
                metric_name="projection_send_time",
                value=avg_send_time * 1000,  # Convert to ms
                unit="ms",
                source_service="ProjectionService"
            ))
        
        # Calculate packets per second
        elapsed = time.perf_counter() - self._last_perf_report
        if elapsed > 0:
            pps = self._data_packets_sent / elapsed
            self._event_broker.publish(PerformanceMetric(
                metric_name="projection_packets_per_second",
                value=pps,
                unit="pps",
                source_service="ProjectionService"
            )) 