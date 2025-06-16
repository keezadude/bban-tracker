"""
ProjectionSetupPage for BBAN-Tracker Event-Driven Architecture.

This module contains the projection setup UI panel extracted from the monolithic GUI.
It will be integrated with the GUIService to provide event-driven updates.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QGridLayout, QSpinBox, QCheckBox, QMessageBox, QApplication
)

from ..gui.calibration_wizard import LAYOUT_FILE, _load_json, _save_json


class ProjectionSetupPage(QWidget):
    """Projection configuration screen for Unity client display."""

    def __init__(self, status_cb):
        super().__init__()
        self._status_cb = status_cb
        self._last_worker = None  # Store reference to last active worker for TCP communication
        
        # EDA integration attributes
        self.event_broker = None
        self._eda_callback = None
        self._projection_connected = False
        
        self._setup_ui()
        self._setup_timer()
        self._load_profile()
    
    def set_eda_integration(self, event_broker=None, eda_callback=None):
        """Set EDA integration for event publishing."""
        self.event_broker = event_broker
        self._eda_callback = eda_callback
        print("[ProjectionSetupPage] EDA integration configured")
    
    def update_projection_status(self, connected: bool):
        """Update projection connection status from EDA events."""
        self._projection_connected = connected
        self._update_connection_status()

    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_row = QHBoxLayout()
        layout.addLayout(header_row)

        header = QLabel("PROJECTION SETUP")
        header.setStyleSheet("font-size:24px;font-weight:bold;color:#90EE90;")
        header_row.addWidget(header, alignment=Qt.AlignLeft)

        self.connection_status = QLabel("Status: Not Connected")
        self.connection_status.setStyleSheet("font-size:14px;color:#FF8888;")
        header_row.addWidget(self.connection_status, alignment=Qt.AlignRight)

        # Main content area with preview
        main_layout = QHBoxLayout()
        layout.addLayout(main_layout, stretch=1)

        # Left side - preview
        self._setup_preview_panel(main_layout)
        
        # Right side - controls
        self._setup_controls_panel(main_layout)

    def _setup_preview_panel(self, main_layout):
        """Setup the projection preview panel."""
        preview_group = QGroupBox("Projection Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_widget = QWidget()
        self.preview_widget.setMinimumSize(320, 240)
        self.preview_widget.setStyleSheet("background-color:#111;border:1px solid #444;")
        self.preview_widget.paintEvent = self._draw_preview
        preview_layout.addWidget(self.preview_widget)
        
        main_layout.addWidget(preview_group)

    def _setup_controls_panel(self, main_layout):
        """Setup the projection controls panel."""
        controls_group = QGroupBox("Projection Settings")
        controls_layout = QGridLayout(controls_group)
        
        # Width/Height controls
        controls_layout.addWidget(QLabel("Width (pixels):"), 0, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 7680)
        self.width_spin.setValue(1920)
        self.width_spin.setSingleStep(10)
        self.width_spin.valueChanged.connect(self._update_preview)
        controls_layout.addWidget(self.width_spin, 0, 1)
        
        controls_layout.addWidget(QLabel("Height (pixels):"), 1, 0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 4320)
        self.height_spin.setValue(1080)
        self.height_spin.setSingleStep(10)
        self.height_spin.valueChanged.connect(self._update_preview)
        controls_layout.addWidget(self.height_spin, 1, 1)
        
        # Presets section
        self._setup_presets(controls_layout)
        
        # Action buttons
        self._setup_action_buttons(controls_layout)
        
        # Unity connection section
        self._setup_unity_connection(controls_layout)
        
        main_layout.addWidget(controls_group)

    def _setup_presets(self, controls_layout):
        """Setup preset resolution buttons."""
        controls_layout.addWidget(QLabel("Common Presets:"), 2, 0)
        preset_layout = QHBoxLayout()
        
        self.preset_hd = QPushButton("HD (1280×720)")
        self.preset_hd.clicked.connect(lambda: self._apply_preset(1280, 720))
        preset_layout.addWidget(self.preset_hd)
        
        self.preset_fhd = QPushButton("FHD (1920×1080)")
        self.preset_fhd.clicked.connect(lambda: self._apply_preset(1920, 1080))
        preset_layout.addWidget(self.preset_fhd)
        
        self.preset_4k = QPushButton("4K (3840×2160)")
        self.preset_4k.clicked.connect(lambda: self._apply_preset(3840, 2160))
        preset_layout.addWidget(self.preset_4k)
        
        controls_layout.addLayout(preset_layout, 2, 1)

    def _setup_action_buttons(self, controls_layout):
        """Setup action buttons."""
        button_layout = QHBoxLayout()
        
        self.detect_btn = QPushButton("Auto Detect")
        self.detect_btn.setToolTip("Attempt to detect connected displays and set dimensions")
        self.detect_btn.clicked.connect(self._auto_detect_resolution)
        button_layout.addWidget(self.detect_btn)
        
        self.apply_btn = QPushButton("Apply Projection Settings")
        self.apply_btn.setStyleSheet("font-weight:bold;background-color:#38814F;")
        self.apply_btn.clicked.connect(self._apply_projection)
        button_layout.addWidget(self.apply_btn)
        
        controls_layout.addLayout(button_layout, 3, 0, 1, 2)
        
        # Save as default checkbox
        self.save_default_cb = QCheckBox("Save as default profile")
        self.save_default_cb.setChecked(True)
        controls_layout.addWidget(self.save_default_cb, 4, 0, 1, 2)

    def _setup_unity_connection(self, controls_layout):
        """Setup Unity connection controls."""
        unity_group = QGroupBox("Unity Connection")
        unity_layout = QVBoxLayout(unity_group)
        
        self.connection_info = QLabel(
            "The Unity client must be running and connected to this tracker.\n"
            "Changes will apply immediately when you click 'Apply Projection Settings'.\n"
            "Connection status is shown at the top of this page."
        )
        self.connection_info.setWordWrap(True)
        unity_layout.addWidget(self.connection_info)
        
        # Unity restart button
        self.restart_unity_btn = QPushButton("Restart Unity Client")
        self.restart_unity_btn.setToolTip("Attempt to launch/restart the Unity client application")
        self.restart_unity_btn.clicked.connect(self._restart_unity)
        unity_layout.addWidget(self.restart_unity_btn)
        
        controls_layout.addWidget(unity_group, 5, 0, 1, 2)

    def _setup_timer(self):
        """Setup status update timer."""
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_connection_status)
        self._status_timer.start(1000)  # Check once per second

    def _apply_preset(self, width: int, height: int):
        """Apply a preset resolution."""
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        self._update_preview()

    def _update_preview(self):
        """Update the projection preview."""
        if hasattr(self, 'preview_widget'):
            self.preview_widget.update()

    def _auto_detect_resolution(self):
        """Attempt to detect connected displays and set dimensions."""
        try:
            screen = QApplication.primaryScreen()
            if screen:
                geometry = screen.geometry()
                detected_width = geometry.width()
                detected_height = geometry.height()
                
                # Look for secondary screens that might be projectors
                screens = QApplication.screens()
                if len(screens) > 1:
                    # Use the largest secondary screen
                    largest_screen = max(screens[1:], key=lambda s: s.geometry().width() * s.geometry().height())
                    geometry = largest_screen.geometry()
                    detected_width = geometry.width()
                    detected_height = geometry.height()
                
                # Ask user if they want to use detected resolution
                msg = QMessageBox.question(
                    self,
                    "Auto-Detect Resolution",
                    f"Detected resolution: {detected_width}×{detected_height}\n\nApply this resolution?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if msg == QMessageBox.Yes:
                    self.width_spin.setValue(detected_width)
                    self.height_spin.setValue(detected_height)
                    self._update_preview()
                    self._status_cb(f"Resolution set to {detected_width}×{detected_height}")
                    
        except Exception as e:
            QMessageBox.warning(self, "Auto-Detect Error", f"Failed to detect displays: {e}")

    def _apply_projection(self):
        """Apply the current projection settings - publishes EDA event."""
        width = self.width_spin.value()
        height = self.height_spin.value()
        
        # Save profile if requested
        if self.save_default_cb.isChecked():
            self._save_profile(width, height)
        
        # EDA PATTERN: Publish projection config event instead of direct worker access
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ProjectionConfigUpdated
            self.event_broker.publish(ProjectionConfigUpdated(width=width, height=height))
            self._status_cb(f"Projection settings applied via EDA: {width}×{height}")
            
            # Update connection status immediately
            self.connection_status.setText("Status: Settings Applied")
            self.connection_status.setStyleSheet("font-size:14px;color:#88FF88;")
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            # Callback for EDA integration during transition
            self._eda_callback('update_projection_config', width=width, height=height)
            self._status_cb(f"Projection settings applied via EDA: {width}×{height}")
            
            # Update connection status immediately
            self.connection_status.setText("Status: Settings Applied")
            self.connection_status.setStyleSheet("font-size:14px;color:#88FF88;")
        else:
            # Legacy fallback - find worker for TCP communication
            worker = self._find_worker()
            if worker:
                worker.send_projection_update(width, height)
                self._status_cb(f"Projection settings applied (legacy): {width}×{height}")
                
                # Update connection status immediately
                self.connection_status.setText("Status: Settings Applied")
                self.connection_status.setStyleSheet("font-size:14px;color:#88FF88;")
            else:
                QMessageBox.warning(
                    self, 
                    "Connection Error", 
                    "No active tracker connection found. Please start tracking first."
                )

    def _save_profile(self, width: int, height: int):
        """Save projection profile to file."""
        try:
            data = _load_json(LAYOUT_FILE, {})
            data["default"] = {"width": width, "height": height}
            _save_json(LAYOUT_FILE, data)
            self._status_cb("Projection profile saved as default")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save profile: {e}")

    def _load_profile(self):
        """Load saved projection profile."""
        try:
            data = _load_json(LAYOUT_FILE, {})
            default = data.get("default", {})
            
            width = default.get("width", 1920)
            height = default.get("height", 1080)
            
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)
            self._update_preview()
            
        except Exception:
            # Use defaults if loading fails
            pass

    def _find_worker(self):
        """DEPRECATED: Direct worker access replaced by EDA events."""
        print("[WARNING] _find_worker() deprecated - use EDA projection events")
        # Look for worker in parent windows (legacy compatibility only)
        parent = self.parent()
        while parent:
            if hasattr(parent, '_worker') and parent._worker:
                self._last_worker = parent._worker
                return parent._worker
            if hasattr(parent, 'get_active_worker'):
                worker = parent.get_active_worker()
                if worker:
                    self._last_worker = worker
                    return worker
            parent = parent.parent()
        
        # Use last known worker if available
        if self._last_worker and self._last_worker.is_alive():
            return self._last_worker
            
        return None

    def _update_connection_status(self):
        """Update the Unity connection status - transitioning to EDA status."""
        # EDA PATTERN: Status should come from service events, not direct worker access
        if hasattr(self, '_projection_connected'):
            # Use EDA-provided status if available
            if self._projection_connected:
                self.connection_status.setText("Status: Unity Connected")
                self.connection_status.setStyleSheet("font-size:14px;color:#88FF88;")
            else:
                self.connection_status.setText("Status: Not Connected")
                self.connection_status.setStyleSheet("font-size:14px;color:#FF8888;")
        else:
            # Legacy fallback - check worker directly
            worker = self._find_worker()
            if worker and hasattr(worker, '_tcp_client_socket') and worker._tcp_client_socket:
                self.connection_status.setText("Status: Unity Connected (legacy)")
                self.connection_status.setStyleSheet("font-size:14px;color:#88FF88;")
            else:
                self.connection_status.setText("Status: Not Connected")
                self.connection_status.setStyleSheet("font-size:14px;color:#FF8888;")

    def _restart_unity(self):
        """Attempt to restart the Unity client."""
        try:
            import subprocess
            import sys
            from pathlib import Path
            
            # Try to find Unity executable in common locations
            unity_paths = [
                "unity_client.exe",
                "../unity_client/unity_client.exe",
                "beysion-unity-DO_NOT_MODIFY/unity_client.exe"
            ]
            
            unity_exe = None
            for path in unity_paths:
                if Path(path).exists():
                    unity_exe = path
                    break
            
            if unity_exe:
                subprocess.Popen([unity_exe], shell=True)
                QMessageBox.information(self, "Unity Client", "Unity client launch initiated.")
                self._status_cb("Unity client restart requested")
            else:
                QMessageBox.warning(
                    self, 
                    "Unity Client", 
                    "Unity client executable not found. Please launch it manually."
                )
                
        except Exception as e:
            QMessageBox.warning(self, "Unity Client", f"Failed to restart Unity client: {e}")

    def _draw_preview(self, event):
        """Draw the projection preview."""
        painter = QPainter(self.preview_widget)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get widget dimensions
        widget_rect = self.preview_widget.rect()
        widget_width = widget_rect.width()
        widget_height = widget_rect.height()
        
        # Get projection dimensions
        proj_width = self.width_spin.value()
        proj_height = self.height_spin.value()
        
        # Calculate aspect ratios
        widget_aspect = widget_width / widget_height if widget_height > 0 else 1
        proj_aspect = proj_width / proj_height if proj_height > 0 else 1
        
        # Calculate preview rectangle (centered, maintaining aspect ratio)
        if proj_aspect > widget_aspect:
            # Projection is wider
            preview_width = widget_width - 20
            preview_height = preview_width / proj_aspect
        else:
            # Projection is taller
            preview_height = widget_height - 20
            preview_width = preview_height * proj_aspect
        
        # Center the preview
        x = (widget_width - preview_width) / 2
        y = (widget_height - preview_height) / 2
        
        # Draw preview background
        painter.fillRect(int(x), int(y), int(preview_width), int(preview_height), QColor(40, 40, 40))
        
        # Draw border
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        painter.drawRect(int(x), int(y), int(preview_width), int(preview_height))
        
        # Draw grid lines to show projection area
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        grid_size = 10
        for i in range(1, grid_size):
            # Vertical lines
            x_pos = x + (preview_width * i / grid_size)
            painter.drawLine(int(x_pos), int(y), int(x_pos), int(y + preview_height))
            
            # Horizontal lines
            y_pos = y + (preview_height * i / grid_size)
            painter.drawLine(int(x), int(y_pos), int(x + preview_width), int(y_pos))
        
        # Draw resolution text
        painter.setPen(QPen(QColor(200, 200, 200)))
        painter.drawText(
            widget_rect,
            Qt.AlignCenter,
            f"{proj_width} × {proj_height}\nProjection Preview"
        )

    def showEvent(self, event):
        """Handle show event."""
        super().showEvent(event)
        self._update_preview()
        
        # Update timer more frequently when visible
        if hasattr(self, '_status_timer'):
            self._status_timer.start(500)

    def hideEvent(self, event):
        """Handle hide event."""
        super().hideEvent(event)
        
        # Slow down timer when not visible
        if hasattr(self, '_status_timer'):
            self._status_timer.start(2000) 