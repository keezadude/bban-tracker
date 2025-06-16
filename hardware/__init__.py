"""
Hardware Abstraction Layer (HAL) package for BBAN-Tracker.

This package provides hardware abstraction interfaces and implementations
that isolate the application from specific sensor SDKs and hardware details.
"""

from .realsense_d400_hal import RealSenseD400_HAL

__all__ = [
    'RealSenseD400_HAL'
] 