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
        """Handle request to start tracking."""
        if self._tracking_thread and self._tracking_thread.is_alive():
            return  # Already tracking
            
        try:
            # Initialize hardware
            hw_config = {
                'dev_mode': event.dev_mode,
                'cam_src': event.cam_src,
                'video_path': event.video_path
            }
            
            if not self._hardware.initialize(hw_config):
                self._event_broker.publish(TrackingError(
                    error_message="Failed to initialize hardware",
                    error_type="hardware_error",
                    recoverable=True
                ))
                return
            
            if not self._hardware.start_stream():
                self._event_broker.publish(TrackingError(
                    error_message="Failed to start camera stream",
                    error_type="hardware_error", 
                    recoverable=True
                ))
                return
            
            # Initialize tracking components
            self._detector = Detector()
            self._registry = Registry()
            
            # Warm up the camera and calibrate
            self._warmup_camera()
            self._detector.calibrate(self._get_cropped_frame)
            
            # Start tracking thread
            self._stop_event.clear()
            self._tracking_thread = threading.Thread(
                target=self._tracking_loop,
                daemon=True,
                name="TrackingService-Main"
            )
            self._start_time = time.perf_counter()
            self._tracking_thread.start()
            
            # Publish success event
            hw_info = self._hardware.get_hardware_info()
            self._event_broker.publish(TrackingStarted(
                camera_type=hw_info.get('model', 'Unknown'),
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
        if not self._detector:
            return
            
        if event.threshold is not None:
            self._detector.threshold = event.threshold
        if event.min_area is not None:
            self._detector.min_contour_area = event.min_area
        if event.max_area is not None:
            self._detector.large_contour_area = event.max_area
        if event.invert_ir is not None:
            self._invert_ir = event.invert_ir
        if event.smoothing_alpha is not None:
            from ..objects import set_smoothing_alpha
            set_smoothing_alpha(event.smoothing_alpha)
    
    def _handle_realsense_settings(self, event: ChangeRealSenseSettings) -> None:
        """Handle changes to RealSense camera settings."""
        if not self._hardware or not self._hardware.is_connected():
            return
            
        try:
            # Apply each setting that was provided
            if event.emitter_enabled is not None:
                self._hardware.set_option('emitter_enabled', 1.0 if event.emitter_enabled else 0.0)
            if event.laser_power is not None:
                self._hardware.set_option('laser_power', float(event.laser_power))
            if event.visual_preset is not None:
                self._hardware.set_option('visual_preset', float(event.visual_preset))
            if event.exposure is not None:
                self._hardware.set_option('exposure', float(event.exposure))
            if event.gain is not None:
                self._hardware.set_option('gain', float(event.gain))
            if event.enable_auto_exposure is not None:
                self._hardware.set_option('enable_auto_exposure', 1.0 if event.enable_auto_exposure else 0.0)
                
            # Handle filter settings (these would need to be implemented in the hardware interface)
            # For now, we'll just log that they were received
            if event.postprocessing_enabled is not None:
                print(f"[TrackingService] Post-processing: {event.postprocessing_enabled}")
                
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
        if not self._detector:
            return
            
        try:
            self._detector.calibrate(self._get_cropped_frame)
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
    
    # ==================== TRACKING LOOP ==================== #
    
    def _tracking_loop(self) -> None:
        """Main tracking loop that processes frames and publishes events."""
        print("[TrackingService] Tracking loop started")
        
        try:
            while not self._stop_event.is_set():
                loop_start = time.perf_counter()
                
                try:
                    # Get frame from hardware
                    frame_data = self._hardware.read_next_frame()
                    if frame_data is None:
                        continue
                    
                    # Apply crop and processing
                    frame = self._apply_crop(frame_data)
                    if self._invert_ir:
                        import cv2
                        frame = cv2.bitwise_not(frame)
                    
                    # Run detection
                    beys, hits = self._detector.detect(frame)
                    
                    # Update registry with tracking
                    self._registry.register(beys, hits)
                    
                    # Convert to immutable event data
                    bey_data = [self._bey_to_data(bey) for bey in beys]
                    hit_data = [self._hit_to_data(hit) for hit in hits]
                    
                    # Publish tracking data event
                    self._event_broker.publish(TrackingDataUpdated(
                        frame_id=self._frame_count,
                        beys=bey_data,
                        hits=hit_data
                    ))
                    
                    # Move to next frame
                    self._registry.nextFrame()
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
                        
                except Exception as e:
                    self._event_broker.publish(TrackingError(
                        error_message=f"Tracking loop error: {e}",
                        error_type="detection_error",
                        recoverable=True
                    ))
                    # Brief pause before continuing
                    time.sleep(0.1)
                    
        except Exception as e:
            self._event_broker.publish(TrackingError(
                error_message=f"Fatal tracking error: {e}",
                error_type="detection_error", 
                recoverable=False
            ))
        finally:
            self._cleanup_tracking()
            print("[TrackingService] Tracking loop stopped")
    
    # ==================== INTERNAL HELPERS ==================== #
    
    def _stop_tracking_internal(self, reason: str) -> None:
        """Internal method to stop tracking with cleanup."""
        if self._tracking_thread and self._tracking_thread.is_alive():
            self._stop_event.set()
            self._tracking_thread.join(timeout=2.0)
            
        self._cleanup_tracking()
        
        self._event_broker.publish(TrackingStopped(reason=reason))
    
    def _cleanup_tracking(self) -> None:
        """Clean up tracking resources."""
        if self._hardware:
            try:
                self._hardware.stop_stream()
            except Exception:
                pass
        
        self._detector = None
        self._registry = None
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