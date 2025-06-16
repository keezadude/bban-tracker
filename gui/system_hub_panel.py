"""
SystemHubPage for BBAN-Tracker Event-Driven Architecture.

This module contains the system hub UI panel extracted from the monolithic GUI.
It will be integrated with the GUIService to provide the main navigation hub.
"""

from __future__ import annotations

from typing import Optional, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class SystemHubPage(QWidget):
    """Simple hub routing to various setup screens."""

    def __init__(self):
        super().__init__()
        self._setup_ui()
        
        # Callbacks for navigation (will be wired externally)
        self.cb_open_calibration: Optional[Callable] = None
        self.cb_open_options: Optional[Callable] = None
        self.cb_open_projection: Optional[Callable] = None
        self.cb_open_tracker: Optional[Callable] = None
        self.cb_open_free_play: Optional[Callable] = None

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("BeysionXR Kiosk – System Hub")
        title.setStyleSheet("font-size:36px;font-weight:bold;color:#90EE90; padding: 10px;")
        layout.addWidget(title, alignment=Qt.AlignLeft)

        # Button row
        btn_row = QHBoxLayout()
        layout.addLayout(btn_row, stretch=1)

        # Create navigation buttons
        self.btn_calibrate = self._create_main_menu_button("Calibrate")
        btn_row.addWidget(self.btn_calibrate)

        self.btn_options = self._create_main_menu_button("Options") 
        btn_row.addWidget(self.btn_options)

        self.btn_projection = self._create_main_menu_button("Projection")
        btn_row.addWidget(self.btn_projection)

        self.btn_tracker = self._create_main_menu_button("Tracker")
        btn_row.addWidget(self.btn_tracker)

        # Direct navigation to Free Play from System Hub
        self.btn_free_play = self._create_main_menu_button("Free Play")
        btn_row.addWidget(self.btn_free_play)

        # Connect button signals
        self._connect_signals()

    def _create_main_menu_button(self, text: str) -> QPushButton:
        """Create a styled main menu button."""
        btn = QPushButton(text)
        btn.setFixedWidth(220)
        btn.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                font-weight: bold;
                padding: 12px;
                background-color: #38414F;
                color: #E0E0E0;
                border: 1px solid #56637A;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #4A5469;
            }
            QPushButton:pressed {
                background-color: #2E3644;
            }
        """)
        return btn

    def _connect_signals(self):
        """Connect button signals to navigation callbacks."""
        self.btn_calibrate.clicked.connect(self._on_calibrate_clicked)
        self.btn_options.clicked.connect(self._on_options_clicked)
        self.btn_projection.clicked.connect(self._on_projection_clicked)
        self.btn_tracker.clicked.connect(self._on_tracker_clicked)
        self.btn_free_play.clicked.connect(self._on_free_play_clicked)

    def _on_calibrate_clicked(self):
        """Handle calibrate button click."""
        if self.cb_open_calibration:
            self.cb_open_calibration()

    def _on_options_clicked(self):
        """Handle options button click.""" 
        if self.cb_open_options:
            self.cb_open_options()

    def _on_projection_clicked(self):
        """Handle projection button click."""
        if self.cb_open_projection:
            self.cb_open_projection()

    def _on_tracker_clicked(self):
        """Handle tracker button click."""
        if self.cb_open_tracker:
            self.cb_open_tracker()

    def _on_free_play_clicked(self):
        """Handle free play button click."""
        if self.cb_open_free_play:
            self.cb_open_free_play()

    # Navigation callback setters
    def set_calibration_callback(self, callback: Callable):
        """Set the calibration navigation callback."""
        self.cb_open_calibration = callback

    def set_options_callback(self, callback: Callable):
        """Set the options navigation callback."""
        self.cb_open_options = callback

    def set_projection_callback(self, callback: Callable):
        """Set the projection navigation callback."""
        self.cb_open_projection = callback

    def set_tracker_callback(self, callback: Callable):
        """Set the tracker navigation callback.""" 
        self.cb_open_tracker = callback

    def set_free_play_callback(self, callback: Callable):
        """Set the free play navigation callback."""
        self.cb_open_free_play = callback 