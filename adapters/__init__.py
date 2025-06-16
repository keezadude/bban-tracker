"""
Projection client adapters package for BBAN-Tracker.

This package contains adapter implementations that enable communication
with external projection clients through various protocols.
"""

from .beysion_unity_adapter import BeysionUnityAdapter
from .beysion_unity_adapter_corrected import BeysionUnityAdapterCorrected
from .shared_memory_protocol import SharedMemoryFrame, UnityCommand, ProjectionConfig

__all__ = [
    'BeysionUnityAdapter',
    'BeysionUnityAdapterCorrected',
    'SharedMemoryFrame', 
    'UnityCommand',
    'ProjectionConfig'
] 