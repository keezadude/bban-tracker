"""
Mock hardware implementation for BBAN-Tracker testing.

This module provides a mock implementation of the ITrackerHardware interface
for testing and development purposes when real hardware is not available.
"""

import time
import numpy as np
from typing import Dict, Any, Optional

from ..core.interfaces import ITrackerHardware


class MockTrackerHardware(ITrackerHardware):
    """
    Mock implementation of the tracker hardware interface.
    
    This class simulates a hardware device for testing purposes,
    providing mock data and responses without requiring actual hardware.
    """
    
    def __init__(self):
        """Initialize the mock hardware."""
        self._connected = False
        self._streaming = False
        self._frame_count = 0
        self._start_time = 0.0
        
        # Mock hardware configuration
        self._options = {
            'emitter_enabled': 1.0,
            'laser_power': 150.0,
            'visual_preset': 0.0,
            'exposure': 1000.0,
            'gain': 16.0,
            'enable_auto_exposure': 0.0
        }
        
        # Mock frame dimensions
        self._width = 640
        self._height = 360
        
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the mock hardware.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if initialization successful
        """
        try:
            # Simulate initialization delay
            time.sleep(0.1)
            
            self._connected = True
            print(f"[MockTrackerHardware] Mock hardware initialized with config: {config}")
            return True
            
        except Exception as e:
            print(f"[MockTrackerHardware] Initialization failed: {e}")
            return False
    
    def start_stream(self) -> bool:
        """
        Start the mock data stream.
        
        Returns:
            True if stream started successfully
        """
        if not self._connected:
            return False
            
        self._streaming = True
        self._start_time = time.perf_counter()
        self._frame_count = 0
        
        print("[MockTrackerHardware] Mock stream started")
        return True
    
    def stop_stream(self) -> None:
        """Stop the mock data stream."""
        self._streaming = False
        print("[MockTrackerHardware] Mock stream stopped")
    
    def read_next_frame(self) -> Optional[np.ndarray]:
        """
        Read the next mock frame.
        
        Returns:
            Mock frame data as numpy array
        """
        if not self._streaming:
            return None
            
        # Generate mock frame data
        # Create a simple gradient pattern that changes over time
        frame = np.zeros((self._height, self._width), dtype=np.uint8)
        
        # Add time-based pattern for visual feedback
        time_factor = (self._frame_count % 100) / 100.0
        
        for y in range(self._height):
            for x in range(self._width):
                # Create a moving pattern
                value = int(128 + 127 * np.sin((x + y + time_factor * 50) * 0.02))
                frame[y, x] = max(0, min(255, value))
        
        # Add some mock "objects" that move around
        self._add_mock_objects(frame)
        
        self._frame_count += 1
        return frame
    
    def _add_mock_objects(self, frame: np.ndarray) -> None:
        """Add mock moving objects to the frame."""
        import cv2
        
        # Create 2-3 moving circular objects
        num_objects = 2
        time_factor = self._frame_count * 0.05
        
        for i in range(num_objects):
            # Calculate moving position
            center_x = int(self._width * 0.3 + 0.4 * self._width * np.sin(time_factor + i * 2))
            center_y = int(self._height * 0.3 + 0.4 * self._height * np.cos(time_factor * 0.7 + i * 1.5))
            
            # Ensure objects stay within frame bounds
            center_x = max(20, min(self._width - 20, center_x))
            center_y = max(20, min(self._height - 20, center_y))
            
            # Draw circular object
            radius = 15 + int(5 * np.sin(time_factor * 2 + i))
            cv2.circle(frame, (center_x, center_y), radius, 255, -1)
    
    def is_connected(self) -> bool:
        """
        Check if the mock hardware is connected.
        
        Returns:
            True if connected
        """
        return self._connected
    
    def get_hardware_info(self) -> Dict[str, Any]:
        """
        Get mock hardware information.
        
        Returns:
            Dictionary with hardware information
        """
        if not self._connected:
            return {'status': 'disconnected'}
            
        return {
            'model': 'Mock RealSense D435',
            'serial_number': 'MOCK123456789',
            'firmware_version': '5.12.7.100',
            'status': 'connected',
            'resolution': (self._width, self._height),
            'fps': 60.0,
            'depth_scale': 0.001,
            'supports_depth': True,
            'supports_color': False
        }
    
    def get_supported_options(self) -> list:
        """
        Get list of supported mock options.
        
        Returns:
            List of option names
        """
        return list(self._options.keys())
    
    def get_option(self, option_name: str) -> float:
        """
        Get mock option value.
        
        Args:
            option_name: Name of the option
            
        Returns:
            Option value
        """
        if option_name not in self._options:
            raise ValueError(f"Unknown option: {option_name}")
            
        return self._options[option_name]
    
    def set_option(self, option_name: str, value: float) -> None:
        """
        Set mock option value.
        
        Args:
            option_name: Name of the option
            value: New value for the option
        """
        if option_name not in self._options:
            raise ValueError(f"Unknown option: {option_name}")
            
        # Validate value ranges for realism
        if option_name == 'laser_power':
            value = max(0.0, min(360.0, value))
        elif option_name == 'exposure':
            value = max(1.0, min(10000.0, value))
        elif option_name == 'gain':
            value = max(16.0, min(248.0, value))
        elif option_name in ['emitter_enabled', 'enable_auto_exposure']:
            value = 1.0 if value > 0.5 else 0.0
        
        self._options[option_name] = value
        print(f"[MockTrackerHardware] Set {option_name} = {value}")
    
    def get_frame_rate(self) -> float:
        """
        Get current mock frame rate.
        
        Returns:
            Frame rate in FPS
        """
        return 60.0  # Fixed mock frame rate
    
    def set_frame_rate(self, fps: float) -> None:
        """
        Set mock frame rate (ignored for mock).
        
        Args:
            fps: Desired frame rate
        """
        print(f"[MockTrackerHardware] Mock frame rate set to {fps} (simulated)")
    
    def get_resolution(self) -> tuple:
        """
        Get current mock resolution.
        
        Returns:
            Tuple of (width, height)
        """
        return (self._width, self._height)
    
    def set_resolution(self, width: int, height: int) -> None:
        """
        Set mock resolution.
        
        Args:
            width: Frame width
            height: Frame height
        """
        self._width = width
        self._height = height
        print(f"[MockTrackerHardware] Mock resolution set to {width}×{height}")
    
    def close(self) -> None:
        """Close the mock hardware connection."""
        self.stop_stream()
        self._connected = False
        print("[MockTrackerHardware] Mock hardware closed")
    
    def __del__(self):
        """Cleanup on destruction."""
        self.close() 