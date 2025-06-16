"""
Services package for the BBAN-Tracker Event-Driven Architecture.

This package contains the three core services that implement the EDA pattern:
- TrackingService: Hardware management and tracking pipeline
- GUIService: User interface and interaction management  
- ProjectionService: Unity client communication and projection control

All services communicate exclusively through the event broker, ensuring
proper decoupling and maintainability.
"""

from .tracking_service import TrackingService
from .gui_service import GUIService
from .projection_service import ProjectionService

__all__ = [
    'TrackingService',
    'GUIService', 
    'ProjectionService'
] 