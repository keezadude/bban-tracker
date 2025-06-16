"""
Intel RealSense D400 Hardware Abstraction Layer implementation.

This module provides a concrete implementation of ITrackerHardware that wraps
the existing camera functionality and provides hardware abstraction with
graceful fallback capabilities for development environments.
"""

import time
import numpy as np
from typing import Optional, Dict, Any
from pathlib import Path

from ..core.interfaces import ITrackerHardware
from ..camera import RealsenseStream, WebcamVideoStream, VideoFileStream
import pyrealsense2 as rs


class RealSenseD400_HAL(ITrackerHardware):
    """
    Hardware Abstraction Layer for Intel RealSense D400 series cameras.
    
    This class encapsulates all Intel RealSense SDK interactions and provides
    a generic hardware interface. It supports graceful fallback to webcam or
    video file sources for development environments where RealSense hardware
    is not available.
    
    Key Features:
    - Automatic fallback to webcam/video in dev environments
    - Real-time performance monitoring
    - Comprehensive error handling and recovery
    - Thread-safe operation
    """
    
    def __init__(self):
        """Initialize the HAL without connecting to hardware."""
        self._camera = None
        self._config = {}
        self._connected = False
        self._hardware_type = "unknown"  # "realsense", "webcam", "video"
        self._initialization_time = 0.0
        self._performance_metrics = {
            'frame_read_times': [],
            'option_set_times': [],
            'total_frames_read': 0
        }
    
    def initialize(self, config: dict) -> bool:
        """
        Initialize the hardware with the given configuration.
        
        Supports multiple initialization modes:
        - RealSense camera (default)
        - Webcam fallback (dev_mode=True)
        - Video file playback (video_path provided)
        
        Args:
            config: Configuration dictionary containing:
                - dev_mode (bool): Use webcam instead of RealSense
                - cam_src (int): Camera index for webcam mode
                - video_path (str): Path to video file for playback
                
        Returns:
            True if hardware was successfully initialized
        """
        start_time = time.perf_counter()
        self._config = config.copy()
        
        try:
            # Determine hardware type and initialize accordingly
            if config.get('video_path'):
                self._hardware_type = "video"
                video_path = config['video_path']
                if not Path(video_path).exists():
                    raise FileNotFoundError(f"Video file not found: {video_path}")
                self._camera = VideoFileStream(video_path).start()
                
            elif config.get('dev_mode', False):
                self._hardware_type = "webcam"
                cam_src = config.get('cam_src', 0)
                self._camera = WebcamVideoStream(src=cam_src).start()
                
            else:
                # Try RealSense first, fallback to webcam if unavailable
                try:
                    self._hardware_type = "realsense"
                    self._camera = RealsenseStream().start()
                except Exception as rs_error:
                    print(f"[RealSenseD400_HAL] RealSense initialization failed: {rs_error}")
                    print("[RealSenseD400_HAL] Falling back to webcam")
                    self._hardware_type = "webcam"
                    self._camera = WebcamVideoStream(src=0).start()
            
            # Verify camera is working by reading a test frame
            if self._camera:
                test_frame = self._camera.readNext()
                if test_frame is not None:
                    self._connected = True
                    self._initialization_time = time.perf_counter() - start_time
                    print(f"[RealSenseD400_HAL] Initialized {self._hardware_type} in {self._initialization_time*1000:.1f}ms")
                    return True
            
            raise RuntimeError("Camera initialization failed - no valid frames")
            
        except Exception as e:
            print(f"[RealSenseD400_HAL] Initialization failed: {e}")
            self._connected = False
            return False
    
    def start_stream(self) -> bool:
        """
        Start the camera stream.
        
        Note: For the current camera implementations, streaming is started
        during initialization. This method verifies the stream is active.
        
        Returns:
            True if stream is active and producing frames
        """
        if not self._camera:
            return False
            
        try:
            # Verify stream is working by attempting to read a frame
            frame = self._camera.read()
            return frame is not None
        except Exception:
            return False
    
    def stop_stream(self) -> None:
        """Stop the camera stream and clean up resources."""
        if self._camera:
            try:
                self._camera.close()
            except Exception as e:
                print(f"[RealSenseD400_HAL] Error stopping stream: {e}")
            finally:
                self._camera = None
                self._connected = False
    
    def read_next_frame(self) -> Optional[np.ndarray]:
        """
        Read the next available frame (blocking).
        
        This method blocks until a new frame is available. It includes
        performance monitoring and error handling.
        
        Returns:
            Frame data as numpy array, or None if read failed
        """
        if not self._camera or not self._connected:
            return None
            
        try:
            start_time = time.perf_counter()
            frame = self._camera.readNext()
            read_time = time.perf_counter() - start_time
            
            # Track performance metrics
            self._performance_metrics['frame_read_times'].append(read_time)
            if len(self._performance_metrics['frame_read_times']) > 100:
                self._performance_metrics['frame_read_times'].pop(0)
            self._performance_metrics['total_frames_read'] += 1
            
            return frame
            
        except Exception as e:
            print(f"[RealSenseD400_HAL] Frame read error: {e}")
            return None
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """
        Get the latest available frame (non-blocking).
        
        Returns:
            Most recent frame data, or None if not available
        """
        if not self._camera or not self._connected:
            return None
            
        try:
            return self._camera.read()
        except Exception as e:
            print(f"[RealSenseD400_HAL] Latest frame read error: {e}")
            return None
    
    def set_option(self, option_name: str, value: Any) -> bool:
        """
        Set a hardware-specific option.
        
        This method provides a generic interface for setting camera options
        while hiding the specific SDK calls. For RealSense cameras, it maps
        to rs.option values. For other camera types, it provides best-effort
        compatibility.
        
        Args:
            option_name: Generic option name (e.g., "emitter_enabled", "exposure")
            value: Option value to set
            
        Returns:
            True if option was successfully set
        """
        if not self._camera or not self._connected:
            return False
            
        start_time = time.perf_counter()
        
        try:
            if self._hardware_type == "realsense" and hasattr(self._camera, 'set_option'):
                # Map generic option names to RealSense SDK options
                option_mapping = {
                    'emitter_enabled': rs.option.emitter_enabled,
                    'laser_power': rs.option.laser_power,
                    'exposure': rs.option.exposure,
                    'gain': rs.option.gain,
                    'enable_auto_exposure': rs.option.enable_auto_exposure,
                    'visual_preset': rs.option.visual_preset
                }
                
                if option_name in option_mapping:
                    rs_option = option_mapping[option_name]
                    self._camera.set_option(rs_option, float(value))
                    
                    # Track performance
                    set_time = time.perf_counter() - start_time
                    self._performance_metrics['option_set_times'].append(set_time)
                    if len(self._performance_metrics['option_set_times']) > 50:
                        self._performance_metrics['option_set_times'].pop(0)
                    
                    return True
                else:
                    print(f"[RealSenseD400_HAL] Unsupported option: {option_name}")
                    return False
            else:
                # For webcam/video, most options are not applicable
                print(f"[RealSenseD400_HAL] Option '{option_name}' not available for {self._hardware_type}")
                return False
                
        except Exception as e:
            print(f"[RealSenseD400_HAL] Error setting option {option_name}: {e}")
            return False
    
    def get_option(self, option_name: str) -> Any:
        """
        Get the current value of a hardware option.
        
        Args:
            option_name: Generic option name
            
        Returns:
            Current option value, or None if not available
        """
        if not self._camera or not self._connected:
            return None
            
        try:
            if self._hardware_type == "realsense" and hasattr(self._camera, 'get_option'):
                option_mapping = {
                    'emitter_enabled': rs.option.emitter_enabled,
                    'laser_power': rs.option.laser_power,
                    'exposure': rs.option.exposure,
                    'gain': rs.option.gain,
                    'enable_auto_exposure': rs.option.enable_auto_exposure,
                    'visual_preset': rs.option.visual_preset
                }
                
                if option_name in option_mapping:
                    rs_option = option_mapping[option_name]
                    return self._camera.get_option(rs_option)
            
            return None
            
        except Exception as e:
            print(f"[RealSenseD400_HAL] Error getting option {option_name}: {e}")
            return None
    
    def get_supported_options(self) -> dict:
        """
        Get a dictionary of supported options and their valid ranges.
        
        Returns:
            Dictionary mapping option names to their specifications
        """
        base_options = {
            'emitter_enabled': {'type': 'bool', 'range': [0, 1]},
            'laser_power': {'type': 'int', 'range': [0, 360]},
            'exposure': {'type': 'int', 'range': [1, 33000]},
            'gain': {'type': 'int', 'range': [0, 16]},
            'enable_auto_exposure': {'type': 'bool', 'range': [0, 1]},
            'visual_preset': {'type': 'int', 'range': [0, 10]}
        }
        
        if self._hardware_type == "realsense":
            return base_options
        else:
            # For non-RealSense hardware, return limited options
            return {
                'hardware_type': {'type': 'str', 'range': [self._hardware_type]}
            }
    
    def get_hardware_info(self) -> dict:
        """
        Get comprehensive information about the hardware.
        
        Returns:
            Dictionary containing hardware metadata
        """
        info = {
            'hardware_type': self._hardware_type,
            'connected': self._connected,
            'initialization_time_ms': self._initialization_time * 1000,
            'total_frames_read': self._performance_metrics['total_frames_read']
        }
        
        # Add performance metrics
        if self._performance_metrics['frame_read_times']:
            avg_read_time = sum(self._performance_metrics['frame_read_times']) / len(self._performance_metrics['frame_read_times'])
            info['average_frame_read_time_ms'] = avg_read_time * 1000
            info['max_frame_read_time_ms'] = max(self._performance_metrics['frame_read_times']) * 1000
        
        if self._performance_metrics['option_set_times']:
            avg_option_time = sum(self._performance_metrics['option_set_times']) / len(self._performance_metrics['option_set_times'])
            info['average_option_set_time_ms'] = avg_option_time * 1000
        
        # Add camera-specific info if available
        if self._hardware_type == "realsense" and hasattr(self._camera, 'get_camera_info'):
            try:
                camera_info = self._camera.get_camera_info()
                info.update(camera_info)
            except Exception:
                pass
        
        return info
    
    def is_connected(self) -> bool:
        """
        Check if the hardware is currently connected and responsive.
        
        Returns:
            True if hardware is connected and can produce frames
        """
        if not self._connected or not self._camera:
            return False
            
        try:
            # Verify connection by attempting a non-blocking frame read
            frame = self.get_latest_frame()
            return frame is not None
        except Exception:
            self._connected = False
            return False
    
    # ==================== PERFORMANCE MONITORING ==================== #
    
    def get_performance_metrics(self) -> dict:
        """
        Get detailed performance metrics for monitoring and optimization.
        
        Returns:
            Dictionary containing performance data
        """
        metrics = self._performance_metrics.copy()
        
        if metrics['frame_read_times']:
            times = metrics['frame_read_times']
            metrics['frame_read_stats'] = {
                'count': len(times),
                'average_ms': (sum(times) / len(times)) * 1000,
                'min_ms': min(times) * 1000,
                'max_ms': max(times) * 1000
            }
        
        if metrics['option_set_times']:
            times = metrics['option_set_times']
            metrics['option_set_stats'] = {
                'count': len(times),
                'average_ms': (sum(times) / len(times)) * 1000,
                'min_ms': min(times) * 1000,
                'max_ms': max(times) * 1000
            }
        
        return metrics
    
    def reset_performance_metrics(self) -> None:
        """Reset performance tracking counters."""
        self._performance_metrics = {
            'frame_read_times': [],
            'option_set_times': [],
            'total_frames_read': 0
        } 