"""
Core architecture module for the BBAN-Tracker Event-Driven Architecture.

This package contains the foundational components for the enterprise-grade
tracking system, including the event broker, service interfaces, and
event payload definitions.
"""

from .event_broker import EventBroker
from .events import *
from .interfaces import *

__all__ = [
    'EventBroker',
    'ITrackingService', 
    'IGUIService',
    'IProjectionService',
    'TrackingDataUpdated',
    'ChangeTrackerSettings', 
    'ProjectionConfigUpdated',
    'CalibrateTracker'
] 