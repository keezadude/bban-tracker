"""
UI Components package for EDA-integrated BBAN-Tracker GUI.

This package contains reusable UI components that integrate with the Event-Driven
Architecture, providing a consistent interface and styling across all GUI pages.
"""

from .base_page import BasePage
from .status_components import StatusBar, NotificationWidget, ToastManager

__all__ = [
    'BasePage',
    'StatusBar', 
    'NotificationWidget',
    'ToastManager'
] 