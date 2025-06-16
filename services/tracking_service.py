"""
TrackingService implementation for BBAN-Tracker Event-Driven Architecture.

This service manages the hardware interface, detection pipeline, and publishes
tracking data events. It operates independently of the GUI and projection
services, communicating only through the event broker.
"""

import time
import threading
from typing import Optional, Dict, Any
from threading import Event

from ..core.interfaces import ITrackingService, ITrackerHardware, IEventBroker
from ..core.events import (
    TrackingDataUpdated, TrackingStarted, TrackingStopped, TrackingError,
    ChangeTrackerSettings, ChangeRealSenseSettings, ChangeCropSettings,
    CalibrateTracker, StartTracking, StopTracking, SystemShutdown,
    PerformanceMetric, BeyData, HitData
)
from ..detector import Detector
from ..registry import Registry
from ..objects import Bey, Hit


class TrackingService(ITrackingService):
    """
    Core tracking service that manages hardware and detection pipeline.
    
    This service:
    - Manages the hardware abstraction layer (camera interface)
    - Runs the detection and tracking algorithms
    - Publishes tracking data events at high frequency
    - Responds to configuration changes via events
    - Provides performance monitoring and health status
    """
    
    def __init__(self, event_broker: IEventBroker, hardware: ITrackerHardware):
        """
        Initialize the tracking service with dependency injection.
        
        Args:
            event_broker: Central event broker for communication
            hardware: Hardware abstraction interface (RealSense, webcam, etc.)
        """
        self._event_broker = event_broker
        self._hardware = hardware
        
        # Tracking components
        self._detector: Optional[Detector] = None
        self._registry: Optional[Registry] = None
        
        # Service state
        self._running = False
        self._stop_event = Event()
        self._tracking_thread: Optional[threading.Thread] = None
        self._frame_count = 0
        
        # Configuration
        self._crop_enabled = True
        self._crop_rect = ((150, 15), (500, 350))  # Default from main.py
        self._invert_ir = False
        
        # Performance monitoring
        self._start_time = 0.0
        self._last_perf_report = 0.0
        self._frame_times = []
        
        # Subscribe to relevant events
        self._setup_event_subscriptions()
    
    def _setup_event_subscriptions(self):
        """Set up subscriptions to events this service handles."""
        self._event_broker.subscribe(StartTracking, self._handle_start_tracking)
        self._event_broker.subscribe(StopTracking, self._handle_stop_tracking)
        self._event_broker.subscribe(ChangeTrackerSettings, self._handle_tracker_settings)
        self._event_broker.subscribe(ChangeRealSenseSettings, self._handle_realsense_settings)
        self._event_broker.subscribe(ChangeCropSettings, self._handle_crop_settings)
        self._event_broker.subscribe(CalibrateTracker, self._handle_calibrate)
        self._event_broker.subscribe(SystemShutdown, self._handle_shutdown)
    
    # ==================== SERVICE INTERFACE ==================== #
    
    def start(self) -> None:
        """Start the tracking service (does not start actual tracking)."""
        if self._running:
            return
            
        self._running = True
        print("[TrackingService] Service started, waiting for tracking commands")
    
    def stop(self) -> None:
        """Stop the tracking service and any active tracking."""
        if not self._running:
            return
            
        self._stop_tracking_internal("service_stop")
        self._running = False
        print("[TrackingService] Service stopped")
    
    def is_running(self) -> bool:
        """Return True if the service is active."""
        return self._running
    
    def get_health_status(self) -> dict:
        """Return health and status information."""
        tracking_active = self._tracking_thread and self._tracking_thread.is_alive()
        
        return {
            'service_running': self._running,
            'tracking_active': tracking_active,
            'hardware_connected': self._hardware.is_connected() if self._hardware else False,
            'frame_count': self._frame_count,
            'uptime_seconds': time.perf_counter() - self._start_time if self._start_time else 0
        }
    
    def get_camera_info(self) -> dict:
        """Return information about the active camera."""
        if not self._hardware:
            return {'status': 'no_hardware'}
            
        try:
            return self._hardware.get_hardware_info()
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def get_current_settings(self) -> dict:
        """Return current tracking and camera settings."""
        settings = {
            'crop_enabled': self._crop_enabled,
            'crop_rect': self._crop_rect,
            'invert_ir': self._invert_ir
        }
        
        if self._detector:
            settings.update({
                'threshold': self._detector.threshold,
                'min_area': self._detector.min_contour_area,
                'max_area': self._detector.large_contour_area
            })
        
        # Add hardware settings if available
        if self._hardware and self._hardware.is_connected():
            try:
                hw_options = self._hardware.get_supported_options()
                hw_current = {}
                for option in hw_options:
                    try:
                        hw_current[option] = self._hardware.get_option(option)
                    except:
                        pass
                settings['hardware'] = hw_current
            except Exception:
                pass
                
        return settings
    
    def get_latest_frame_info(self) -> Optional[dict]:
        """Return metadata about the most recent processed frame."""
        if not self._tracking_thread or not self._tracking_thread.is_alive():
            return None
            
        return {
            'frame_id': self._frame_count,
            'timestamp': time.perf_counter(),
            'average_fps': self._calculate_fps()
        }
    
    # ==================== EVENT HANDLERS ==================== #
    
    def _handle_start_tracking(self, event: StartTracking) -> None:
        """Handle request to start tracking using the monolithic TrackingWorker."""
        if self._tracking_thread and self._tracking_thread.is_alive():
            return  # Already tracking
            
        try:
            # Import and use the monolithic TrackingWorker
            from .tracking_worker import TrackingWorker
            
            # Create the TrackingWorker with the same parameters
            self._stop_event.clear()
            self._tracking_worker = TrackingWorker(
                self._stop_event,
                dev_mode=event.dev_mode,
                src=event.cam_src,
                video_path=event.video_path
            )
            
            # Check for initialization errors
            if self._tracking_worker.error_msg:
                self._event_broker.publish(TrackingError(
                    error_message=self._tracking_worker.error_msg,
                    error_type="hardware_error",
                    recoverable=True
                ))
                return
            
            # Start the tracking worker thread
            self._tracking_worker.start()
            self._tracking_thread = self._tracking_worker  # Reference for lifecycle management
            
            # Start our monitoring loop
            self._monitoring_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True,
                name="TrackingService-Monitor"
            )
            self._start_time = time.perf_counter()
            self._monitoring_thread.start()
            
            # Publish success event
            camera_type = "RealSense" if not event.dev_mode else "Webcam"
            self._event_broker.publish(TrackingStarted(
                camera_type=camera_type,
                resolution=(640, 360)  # Default resolution
            ))
            
        except Exception as e:
            self._event_broker.publish(TrackingError(
                error_message=f"Failed to start tracking: {e}",
                error_type="hardware_error",
                recoverable=True
            ))
    
    def _handle_stop_tracking(self, event: StopTracking) -> None:
        """Handle request to stop tracking."""
        self._stop_tracking_internal("user_request")
    
    def _handle_tracker_settings(self, event: ChangeTrackerSettings) -> None:
        """Handle changes to tracker detection settings."""
        # Update TrackingWorker settings if it exists
        if hasattr(self, '_tracking_worker') and self._tracking_worker:
            try:
                if event.threshold is not None:
                    self._tracking_worker.set_threshold(event.threshold)
                if event.min_area is not None:
                    self._tracking_worker.set_min_area(event.min_area)
                if event.max_area is not None:
                    self._tracking_worker.set_max_area(event.max_area)
                if event.invert_ir is not None:
                    self._tracking_worker.set_invert_ir(event.invert_ir)
                if event.smoothing_alpha is not None:
                    # Apply globally since objects module handles this
                    from ..objects import set_smoothing_alpha
                    set_smoothing_alpha(event.smoothing_alpha)
            except Exception as e:
                print(f"[TrackingService] Error applying tracker settings: {e}")
                
        # Store settings for later use
        if event.invert_ir is not None:
            self._invert_ir = event.invert_ir
    
    def _handle_realsense_settings(self, event: ChangeRealSenseSettings) -> None:
        """Handle changes to RealSense camera settings."""
        if not hasattr(self, '_tracking_worker') or not self._tracking_worker:
            return
            
        try:
            # Apply settings through the TrackingWorker
            if event.emitter_enabled is not None:
                self._tracking_worker.set_emitter_enabled(event.emitter_enabled)
            if event.laser_power is not None:
                self._tracking_worker.set_laser_power(event.laser_power)
            if event.visual_preset is not None:
                self._tracking_worker.set_visual_preset(event.visual_preset)
            if event.exposure is not None:
                self._tracking_worker.set_exposure(event.exposure)
            if event.gain is not None:
                self._tracking_worker.set_gain(event.gain)
            if event.enable_auto_exposure is not None:
                self._tracking_worker.set_auto_exposure(event.enable_auto_exposure)
                
            # Handle filter settings
            if event.postprocessing_enabled is not None:
                self._tracking_worker.set_postprocessing_enabled(event.postprocessing_enabled)
                
        except Exception as e:
            self._event_broker.publish(TrackingError(
                error_message=f"Failed to apply RealSense settings: {e}",
                error_type="hardware_error",
                recoverable=True
            ))
    
    def _handle_crop_settings(self, event: ChangeCropSettings) -> None:
        """Handle changes to crop settings."""
        self._crop_enabled = event.enabled
        self._crop_rect = ((event.x1, event.y1), (event.x2, event.y2))
    
    def _handle_calibrate(self, event: CalibrateTracker) -> None:
        """Handle calibration request."""
        if not hasattr(self, '_tracking_worker') or not self._tracking_worker:
            return
            
        try:
            self._tracking_worker.calibrate()
            print("[TrackingService] Calibration completed")
        except Exception as e:
            self._event_broker.publish(TrackingError(
                error_message=f"Calibration failed: {e}",
                error_type="detection_error",
                recoverable=True
            ))
    
    def _handle_shutdown(self, event: SystemShutdown) -> None:
        """Handle system shutdown."""
        self.stop()
    
    # ==================== MONITORING LOOP ==================== #
    
    def _monitoring_loop(self) -> None:
        """Monitor the TrackingWorker and bridge its data to EDA events."""
        print("[TrackingService] Monitoring loop started")
        
        try:
            while not self._stop_event.is_set() and self._tracking_worker.is_alive():
                loop_start = time.perf_counter()
                
                try:
                    # Get current frame from TrackingWorker
                    current_frame = self._tracking_worker.current_frame
                    beys = self._tracking_worker.beys
                    hits = self._tracking_worker.hits
                    
                    if current_frame is not None and beys is not None:
                        # Convert tracking objects to immutable event data
                        bey_data = [self._bey_to_data(bey) for bey in beys]
                        hit_data = [self._hit_to_data(hit) for hit in hits] if hits else []
                        
                        # Publish tracking data event
                        self._event_broker.publish(TrackingDataUpdated(
                            frame_id=self._frame_count,
                            beys=bey_data,
                            hits=hit_data
                        ))
                        
                        self._frame_count += 1
                    
                    # Performance monitoring
                    frame_time = time.perf_counter() - loop_start
                    self._frame_times.append(frame_time)
                    if len(self._frame_times) > 100:
                        self._frame_times.pop(0)
                    
                    # Publish performance metrics periodically
                    if time.perf_counter() - self._last_perf_report > 5.0:
                        self._publish_performance_metrics()
                        self._last_perf_report = time.perf_counter()
                    
                    # Check for TrackingWorker errors
                    if self._tracking_worker.error_msg:
                        self._event_broker.publish(TrackingError(
                            error_message=self._tracking_worker.error_msg,
                            error_type="detection_error",
                            recoverable=True
                        ))
                    
                    # Small sleep to prevent excessive CPU usage
                    time.sleep(0.01)  # ~100 FPS max monitoring rate
                        
                except Exception as e:
                    self._event_broker.publish(TrackingError(
                        error_message=f"Monitoring loop error: {e}",
                        error_type="detection_error",
                        recoverable=True
                    ))
                    # Brief pause before continuing
                    time.sleep(0.1)
                    
        except Exception as e:
            self._event_broker.publish(TrackingError(
                error_message=f"Fatal monitoring error: {e}",
                error_type="detection_error", 
                recoverable=False
            ))
        finally:
            self._cleanup_tracking()
            print("[TrackingService] Monitoring loop stopped")
    
    # ==================== INTERNAL HELPERS ==================== #
    
    def _stop_tracking_internal(self, reason: str) -> None:
        """Internal method to stop tracking with cleanup."""
        # Signal stop to all threads
        self._stop_event.set()
        
        # Stop the TrackingWorker if it exists
        if hasattr(self, '_tracking_worker') and self._tracking_worker:
            try:
                self._tracking_worker.stop_tracking()
                self._tracking_worker.join(timeout=2.0)
            except Exception as e:
                print(f"[TrackingService] Error stopping TrackingWorker: {e}")
        
        # Stop the monitoring thread
        if hasattr(self, '_monitoring_thread') and self._monitoring_thread and self._monitoring_thread.is_alive():
            try:
                self._monitoring_thread.join(timeout=2.0)
            except Exception:
                pass
            
        self._cleanup_tracking()
        self._event_broker.publish(TrackingStopped(reason=reason))
    
    def _cleanup_tracking(self) -> None:
        """Clean up tracking resources."""
        # Clean up TrackingWorker reference
        if hasattr(self, '_tracking_worker'):
            self._tracking_worker = None
        
        if hasattr(self, '_monitoring_thread'):
            self._monitoring_thread = None
            
        self._tracking_thread = None
        self._frame_count = 0
    
    def _warmup_camera(self) -> None:
        """Warm up the camera by reading several frames."""
        for _ in range(20):
            try:
                self._get_cropped_frame()
            except Exception:
                pass
    
    def _get_cropped_frame(self):
        """Get a cropped frame for calibration/detection."""
        frame = self._hardware.read_next_frame()
        return self._apply_crop(frame)
    
    def _apply_crop(self, frame):
        """Apply crop settings to a frame."""
        if not self._crop_enabled or frame is None:
            return frame
            
        (x1, y1), (x2, y2) = self._crop_rect
        return frame[y1:y2, x1:x2].copy()
    
    def _bey_to_data(self, bey: Bey) -> BeyData:
        """Convert a Bey object to immutable BeyData."""
        return BeyData(
            id=bey.getId(),
            pos=bey.getPos(),
            velocity=bey.getVel(),
            raw_velocity=bey.getRawVel(),
            acceleration=bey.getAcc(),
            shape=bey.getShape(),
            frame=bey.getFrame()
        )
    
    def _hit_to_data(self, hit: Hit) -> HitData:
        """Convert a Hit object to immutable HitData."""
        bey1, bey2 = hit.getBeys()
        return HitData(
            pos=hit.getPos(),
            shape=hit.getShape(),
            bey_ids=(bey1.getId(), bey2.getId()),
            is_new_hit=hit.isNewHit()
        )
    
    def _calculate_fps(self) -> float:
        """Calculate current FPS based on recent frame times."""
        if not self._frame_times:
            return 0.0
        avg_frame_time = sum(self._frame_times) / len(self._frame_times)
        return 1.0 / avg_frame_time if avg_frame_time > 0 else 0.0
    
    def _publish_performance_metrics(self) -> None:
        """Publish performance metrics for monitoring."""
        fps = self._calculate_fps()
        avg_frame_time = sum(self._frame_times) / len(self._frame_times) if self._frame_times else 0
        
        self._event_broker.publish(PerformanceMetric(
            metric_name="tracking_fps",
            value=fps,
            unit="fps",
            source_service="TrackingService"
        ))
        
        self._event_broker.publish(PerformanceMetric(
            metric_name="frame_processing_time", 
            value=avg_frame_time * 1000,  # Convert to ms
            unit="ms",
            source_service="TrackingService"
        ))

class MockTrackingService(TrackingService):
    """
    Mock tracking service that generates realistic simulated tracking data.
    
    This service provides the same interface as TrackingService but generates
    simulated bey and hit data for GUI testing without requiring real hardware.
    Useful for development, testing, and demonstration purposes.
    """
    
    def __init__(self, event_broker: IEventBroker):
        """
        Initialize the mock tracking service.
        
        Args:
            event_broker: Central event broker for communication
        """
        # Initialize with a mock hardware interface
        from ..hardware.mock_hardware import MockTrackerHardware
        mock_hardware = MockTrackerHardware()
        
        super().__init__(event_broker, mock_hardware)
        
        # Mock-specific state
        self._mock_beys = []
        self._mock_frame_id = 0
        self._simulation_time = 0.0
        self._last_hit_time = 0.0
        
        # Arena bounds for realistic movement
        self._arena_width = 500
        self._arena_height = 350
        
        print("[MockTrackingService] Mock tracking service initialized")
    
    def _handle_start_tracking(self, event: StartTracking) -> None:
        """Handle request to start mock tracking."""
        if self._tracking_thread and self._tracking_thread.is_alive():
            return  # Already tracking
            
        try:
            # Initialize mock tracking components
            self._detector = Detector()
            self._registry = Registry()
            
            # Create initial mock beys
            self._create_initial_beys()
            
            # Start tracking thread
            self._stop_event.clear()
            self._tracking_thread = threading.Thread(
                target=self._mock_tracking_loop,
                daemon=True,
                name="MockTrackingService-Main"
            )
            self._start_time = time.perf_counter()
            self._tracking_thread.start()
            
            # Publish success event
            self._event_broker.publish(TrackingStarted(
                camera_type="Mock Camera",
                resolution=(640, 360)
            ))
            
            print("[MockTrackingService] Mock tracking started")
            
        except Exception as e:
            self._event_broker.publish(TrackingError(
                error_message=f"Failed to start mock tracking: {e}",
                error_type="mock_error",
                recoverable=True
            ))
    
    def _mock_tracking_loop(self) -> None:
        """Mock tracking loop that generates simulated data."""
        print("[MockTrackingService] Mock tracking loop started")
        
        target_fps = 60.0  # Target 60 FPS for smooth simulation
        frame_interval = 1.0 / target_fps
        
        try:
            while not self._stop_event.is_set():
                loop_start = time.perf_counter()
                
                try:
                    # Update simulation time
                    self._simulation_time += frame_interval
                    
                    # Update mock bey positions and behaviors
                    self._update_mock_beys()
                    
                    # Detect mock hits
                    mock_hits = self._detect_mock_hits()
                    
                    # Convert to event data
                    bey_data = [self._mock_bey_to_data(bey) for bey in self._mock_beys]
                    hit_data = [self._mock_hit_to_data(hit) for hit in mock_hits]
                    
                    # Publish tracking data event
                    self._event_broker.publish(TrackingDataUpdated(
                        frame_id=self._mock_frame_id,
                        beys=bey_data,
                        hits=hit_data
                    ))
                    
                    self._mock_frame_id += 1
                    
                    # Performance monitoring
                    frame_time = time.perf_counter() - loop_start
                    self._frame_times.append(frame_time)
                    if len(self._frame_times) > 100:
                        self._frame_times.pop(0)
                    
                    # Publish performance metrics periodically
                    if time.perf_counter() - self._last_perf_report > 5.0:
                        self._publish_performance_metrics()
                        self._last_perf_report = time.perf_counter()
                    
                    # Sleep to maintain target FPS
                    elapsed = time.perf_counter() - loop_start
                    sleep_time = max(0, frame_interval - elapsed)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                        
                except Exception as e:
                    self._event_broker.publish(TrackingError(
                        error_message=f"Mock tracking loop error: {e}",
                        error_type="mock_error",
                        recoverable=True
                    ))
                    time.sleep(0.1)
                    
        except Exception as e:
            self._event_broker.publish(TrackingError(
                error_message=f"Fatal mock tracking error: {e}",
                error_type="mock_error",
                recoverable=False
            ))
        finally:
            print("[MockTrackingService] Mock tracking loop stopped")
    
    def _create_initial_beys(self) -> None:
        """Create initial mock beys with realistic starting positions."""
        import random
        import math
        
        # Create 2-4 beys with different starting positions and velocities
        num_beys = random.randint(2, 4)
        
        for i in range(num_beys):
            # Random starting position within arena bounds
            x = random.uniform(50, self._arena_width - 50)
            y = random.uniform(50, self._arena_height - 50)
            
            # Random initial velocity
            vel_x = random.uniform(-50, 50)
            vel_y = random.uniform(-50, 50)
            
            # Random angular velocity for spinning motion
            angular_vel = random.uniform(-math.pi, math.pi)
            
            mock_bey = {
                'id': i + 1,
                'pos': [x, y],
                'velocity': [vel_x, vel_y],
                'angular_velocity': angular_vel,
                'spin_decay': random.uniform(0.98, 0.995),  # Gradual slowdown
                'last_hit_time': 0.0,
                'size': random.uniform(15, 25)
            }
            
            self._mock_beys.append(mock_bey)
    
    def _update_mock_beys(self) -> None:
        """Update mock bey positions with realistic physics simulation."""
        import math
        import random
        
        dt = 1.0 / 60.0  # 60 FPS time step
        
        for bey in self._mock_beys:
            # Update position based on velocity
            bey['pos'][0] += bey['velocity'][0] * dt
            bey['pos'][1] += bey['velocity'][1] * dt
            
            # Apply spin decay (gradual slowdown)
            bey['velocity'][0] *= bey['spin_decay']
            bey['velocity'][1] *= bey['spin_decay']
            bey['angular_velocity'] *= bey['spin_decay']
            
            # Bounce off walls with energy loss
            bounce_damping = 0.8
            
            if bey['pos'][0] <= bey['size'] or bey['pos'][0] >= self._arena_width - bey['size']:
                bey['velocity'][0] *= -bounce_damping
                bey['pos'][0] = max(bey['size'], min(self._arena_width - bey['size'], bey['pos'][0]))
            
            if bey['pos'][1] <= bey['size'] or bey['pos'][1] >= self._arena_height - bey['size']:
                bey['velocity'][1] *= -bounce_damping
                bey['pos'][1] = max(bey['size'], min(self._arena_height - bey['size'], bey['pos'][1]))
            
            # Add small random perturbations for realistic movement
            if self._simulation_time - bey['last_hit_time'] > 1.0:  # Only if not recently hit
                bey['velocity'][0] += random.uniform(-2, 2)
                bey['velocity'][1] += random.uniform(-2, 2)
            
            # Ensure minimum velocity to keep beys moving
            vel_magnitude = math.sqrt(bey['velocity'][0]**2 + bey['velocity'][1]**2)
            if vel_magnitude < 5.0:
                # Add random impulse
                angle = random.uniform(0, 2 * math.pi)
                impulse = 10.0
                bey['velocity'][0] += impulse * math.cos(angle)
                bey['velocity'][1] += impulse * math.sin(angle)
    
    def _detect_mock_hits(self) -> list:
        """Detect collisions between mock beys."""
        import math
        
        hits = []
        
        for i, bey1 in enumerate(self._mock_beys):
            for j, bey2 in enumerate(self._mock_beys[i+1:], i+1):
                # Calculate distance between beys
                dx = bey1['pos'][0] - bey2['pos'][0]
                dy = bey1['pos'][1] - bey2['pos'][1]
                distance = math.sqrt(dx*dx + dy*dy)
                
                # Check for collision
                collision_distance = bey1['size'] + bey2['size']
                if distance < collision_distance:
                    # Create hit if enough time has passed since last hit
                    current_time = self._simulation_time
                    if current_time - self._last_hit_time > 0.5:  # Minimum 0.5s between hits
                        
                        # Calculate hit position (midpoint)
                        hit_x = (bey1['pos'][0] + bey2['pos'][0]) / 2
                        hit_y = (bey1['pos'][1] + bey2['pos'][1]) / 2
                        
                        # Apply collision physics
                        self._apply_collision_physics(bey1, bey2, dx, dy, distance)
                        
                        # Create hit data
                        hit = {
                            'pos': (hit_x, hit_y),
                            'bey_ids': (bey1['id'], bey2['id']),
                            'shape': (10, 10),  # Hit effect size
                            'is_new_hit': True
                        }
                        
                        hits.append(hit)
                        self._last_hit_time = current_time
                        
                        # Update last hit time for both beys
                        bey1['last_hit_time'] = current_time
                        bey2['last_hit_time'] = current_time
                        
                        print(f"[MockTrackingService] Hit detected between bey {bey1['id']} and {bey2['id']}")
        
        return hits
    
    def _apply_collision_physics(self, bey1: dict, bey2: dict, dx: float, dy: float, distance: float) -> None:
        """Apply realistic collision physics between two beys."""
        import math
        
        if distance == 0:
            return
        
        # Normalize collision vector
        dx /= distance
        dy /= distance
        
        # Calculate relative velocity
        dvx = bey1['velocity'][0] - bey2['velocity'][0]
        dvy = bey1['velocity'][1] - bey2['velocity'][1]
        
        # Calculate relative velocity along collision normal
        dvn = dvx * dx + dvy * dy
        
        # Only resolve if objects are approaching
        if dvn > 0:
            return
        
        # Calculate collision impulse (assuming equal masses)
        impulse = 2 * dvn / 2  # For equal masses
        impulse_x = impulse * dx
        impulse_y = impulse * dy
        
        # Apply impulse to velocities
        bey1['velocity'][0] -= impulse_x
        bey1['velocity'][1] -= impulse_y
        bey2['velocity'][0] += impulse_x
        bey2['velocity'][1] += impulse_y
        
        # Add some energy to make hits more dramatic
        energy_boost = 1.2
        bey1['velocity'][0] *= energy_boost
        bey1['velocity'][1] *= energy_boost
        bey2['velocity'][0] *= energy_boost
        bey2['velocity'][1] *= energy_boost
        
        # Separate overlapping beys
        overlap = (bey1['size'] + bey2['size']) - distance
        if overlap > 0:
            separation = overlap / 2
            bey1['pos'][0] += dx * separation
            bey1['pos'][1] += dy * separation
            bey2['pos'][0] -= dx * separation
            bey2['pos'][1] -= dy * separation
    
    def _mock_bey_to_data(self, mock_bey: dict) -> BeyData:
        """Convert a mock bey to BeyData."""
        return BeyData(
            id=mock_bey['id'],
            pos=tuple(mock_bey['pos']),
            velocity=tuple(mock_bey['velocity']),
            raw_velocity=tuple(mock_bey['velocity']),
            acceleration=(0.0, 0.0),  # Could calculate if needed
            shape=(int(mock_bey['size']), int(mock_bey['size'])),
            frame=self._mock_frame_id
        )
    
    def _mock_hit_to_data(self, mock_hit: dict) -> HitData:
        """Convert a mock hit to HitData."""
        return HitData(
            pos=mock_hit['pos'],
            shape=mock_hit['shape'],
            bey_ids=mock_hit['bey_ids'],
            is_new_hit=mock_hit['is_new_hit']
        )
    
    def get_camera_info(self) -> dict:
        """Return mock camera information."""
        return {
            'model': 'Mock RealSense D435',
            'serial': 'MOCK123456',
            'status': 'connected',
            'resolution': (640, 360),
            'fps': 60.0,
            'depth_scale': 0.001
        }
    
    def get_current_settings(self) -> dict:
        """Return mock current settings."""
        return {
            'crop_enabled': self._crop_enabled,
            'crop_rect': self._crop_rect,
            'invert_ir': self._invert_ir,
            'threshold': 20,
            'min_area': 150,
            'max_area': 2500,
            'hardware': {
                'emitter_enabled': 1.0,
                'laser_power': 150.0,
                'exposure': 1000.0,
                'gain': 16.0
            }
        } 