"""
Event payload definitions for the BBAN-Tracker Event-Driven Architecture.

This module defines all event types that flow through the system's event broker.
Events are immutable data structures that carry information between services
without creating coupling between producers and consumers.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Any
import time


@dataclass(frozen=True)
class BeyData:
    """Immutable representation of a tracked Beyblade."""
    id: int
    pos: Tuple[int, int]
    velocity: Tuple[float, float] 
    raw_velocity: Tuple[float, float]
    acceleration: Tuple[float, float]
    shape: Tuple[int, int]
    frame: int


@dataclass(frozen=True) 
class HitData:
    """Immutable representation of a collision event."""
    pos: Tuple[int, int]
    shape: Tuple[int, int]
    bey_ids: Tuple[int, int]
    is_new_hit: bool


# ==================== TRACKING SERVICE EVENTS ==================== #

@dataclass(frozen=True)
class TrackingDataUpdated:
    """Published by TrackingService when new frame data is available."""
    frame_id: int
    beys: List[BeyData]
    hits: List[HitData] 
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class TrackingStarted:
    """Published when tracking service successfully starts."""
    camera_type: str  # "RealSense", "Webcam", "VideoFile"
    resolution: Tuple[int, int]
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class TrackingStopped:
    """Published when tracking service stops."""
    reason: str  # "user_request", "error", "camera_lost"
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class TrackingError:
    """Published when tracking encounters an error."""
    error_message: str
    error_type: str  # "camera_error", "detection_error", "hardware_error"
    recoverable: bool
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


# ==================== GUI SERVICE EVENTS ==================== #

@dataclass(frozen=True)
class ChangeTrackerSettings:
    """Published by GUI when user changes detection parameters."""
    threshold: Optional[int] = None
    min_area: Optional[int] = None
    max_area: Optional[int] = None
    smoothing_alpha: Optional[float] = None
    invert_ir: Optional[bool] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class ChangeRealSenseSettings:
    """Published by GUI when user changes RealSense camera settings."""
    emitter_enabled: Optional[bool] = None
    laser_power: Optional[int] = None
    visual_preset: Optional[int] = None
    exposure: Optional[int] = None
    gain: Optional[int] = None
    enable_auto_exposure: Optional[bool] = None
    # Depth processing filters
    postprocessing_enabled: Optional[bool] = None
    decimation_enabled: Optional[bool] = None
    decimation_magnitude: Optional[int] = None
    spatial_filter_enabled: Optional[bool] = None
    spatial_alpha: Optional[float] = None
    spatial_delta: Optional[float] = None
    temporal_filter_enabled: Optional[bool] = None
    temporal_alpha: Optional[float] = None
    temporal_delta: Optional[float] = None
    hole_filling_enabled: Optional[bool] = None
    hole_filling_mode: Optional[int] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class ChangeCropSettings:
    """Published by GUI when user changes crop settings."""
    enabled: bool
    x1: int
    y1: int
    x2: int
    y2: int
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class CalibrateTracker:
    """Published by GUI to request tracker calibration."""
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class StartTracking:
    """Published by GUI to start tracking service."""
    dev_mode: bool = False
    cam_src: int = 0
    video_path: Optional[str] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class StopTracking:
    """Published by GUI to stop tracking service."""
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


# ==================== PROJECTION SERVICE EVENTS ==================== #

@dataclass(frozen=True)
class ProjectionConfigUpdated:
    """Published by GUI when projection settings change."""
    width: int
    height: int
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class ProjectionClientConnected:
    """Published when Unity client connects to projection service."""
    client_address: str
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class ProjectionClientDisconnected:
    """Published when Unity client disconnects."""
    reason: str  # "client_disconnect", "network_error", "timeout"
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


# ==================== SYSTEM EVENTS ==================== #

@dataclass(frozen=True)
class SystemShutdown:
    """Published to signal all services to gracefully shutdown."""
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter())


@dataclass(frozen=True)
class PerformanceMetric:
    """Published for performance monitoring and optimization."""
    metric_name: str
    value: float
    unit: str  # "ms", "fps", "mb", etc.
    source_service: str
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            object.__setattr__(self, 'timestamp', time.perf_counter()) 