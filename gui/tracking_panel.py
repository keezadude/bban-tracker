"""
TrackerSetupPage for BBAN-Tracker Event-Driven Architecture.

This module contains the tracker setup UI panel extracted from the monolithic GUI.
It will be integrated with the GUIService to provide event-driven updates.
"""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event
from typing import Optional

import cv2
import numpy as np
import pyrealsense2 as rs
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QGridLayout, QSlider, QComboBox, QCheckBox, QSpinBox, QMessageBox,
    QTableWidget, QTableWidgetItem
)

from ..camera import RealsenseStream, VideoFileStream
from ..services.tracking_worker import TrackingWorker
from ..gui.calibration_wizard import CalibrationWizard, CALIB_PROFILE_FILE, _load_json, _save_json


class TrackerSetupPage(QWidget):
    """Main tracker setup interface with comprehensive controls."""
    
    def __init__(self, status_cb, *, dev_mode: bool = False, cam_src: int = 0):
        super().__init__()
        self._status_cb = status_cb
        self._dev_mode = dev_mode
        self._cam_src = cam_src
        
        # Worker thread (lazy-started when page is shown)
        self._stop_event: Optional[Event] = None
        self._worker: Optional[TrackingWorker] = None
        
        # EDA integration attributes
        self.event_broker = None
        self._eda_callback = None
        self._tracking_active = False
        
        self._setup_ui()
        self._setup_timer()
    
    def set_eda_integration(self, event_broker=None, eda_callback=None):
        """Set EDA integration for event publishing."""
        self.event_broker = event_broker
        self._eda_callback = eda_callback
        print("[TrackerSetupPage] EDA integration configured")
    
    def update_tracking_status(self, active: bool):
        """Update tracking status from EDA events."""
        self._tracking_active = active
        # Update UI elements based on tracking status
        if hasattr(self, 'btn_pointcloud'):
            self.btn_pointcloud.setEnabled(active)
        
    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_row = QHBoxLayout()
        layout.addLayout(header_row)

        header = QLabel("TRACKER SETUP V2.1")
        header.setStyleSheet("font-size:24px;font-weight:bold;color:#baffc2;")
        header_row.addWidget(header, alignment=Qt.AlignLeft)

        header_row.addStretch(1)

        self.btn_recalibrate = QPushButton("Recalibrate")
        header_row.addWidget(self.btn_recalibrate)
        self.btn_recalibrate.clicked.connect(self._open_calibration_wizard)

        # Video feeds
        feeds_layout = QGridLayout()
        layout.addLayout(feeds_layout, stretch=1)

        self.live_feed_lbl = QLabel()
        self.live_feed_lbl.setStyleSheet("background:#000;border:1px solid #aaa;")
        self.live_feed_lbl.setAlignment(Qt.AlignCenter)
        feeds_layout.addWidget(self.live_feed_lbl, 0, 0)

        self.debug_feed_lbl = QLabel()
        self.debug_feed_lbl.setStyleSheet("background:#000;border:1px solid #aaa;")
        self.debug_feed_lbl.setAlignment(Qt.AlignCenter)
        feeds_layout.addWidget(self.debug_feed_lbl, 0, 1)

        # Control panel
        self._setup_control_panel(layout)
        
    def _setup_control_panel(self, layout):
        """Setup the control panel with all the tracking controls."""
        self.ctrl_group = QGroupBox("Control & Status")
        ctrl_layout = QVBoxLayout(self.ctrl_group)

        # Status indicators
        self.lbl_rs_detected = QLabel("Intel RealSense Detected: UNKNOWN")
        ctrl_layout.addWidget(self.lbl_rs_detected)

        # Invert IR toggle
        invert_layout = QHBoxLayout()
        self.chk_invert = QPushButton("Invert IR Feed")
        self.chk_invert.setCheckable(True)
        self.chk_invert.toggled.connect(self._on_invert_toggled)
        invert_layout.addWidget(self.chk_invert)
        ctrl_layout.addLayout(invert_layout)

        self.lbl_fps = QLabel("FPS: --")
        ctrl_layout.addWidget(self.lbl_fps)

        # Detection parameters
        self._setup_detection_parameters(ctrl_layout)
        
        # RealSense controls  
        self._setup_realsense_controls(ctrl_layout)
        
        # Crop settings
        self._setup_crop_controls(ctrl_layout)
        
        # Action buttons
        self._setup_action_buttons(ctrl_layout)
        
        # Detected objects table
        self.tbl_objects = QTableWidget(0, 4)
        self.tbl_objects.setHorizontalHeaderLabels(["ID", "Pos (X,Y)", "Velocity", "Status"])
        self.tbl_objects.verticalHeader().setVisible(False)
        ctrl_layout.addWidget(self.tbl_objects)

        layout.addWidget(self.ctrl_group)
        
    def _setup_detection_parameters(self, ctrl_layout):
        """Setup detection parameter controls."""
        param_group = QGroupBox("Detection Parameters")
        param_layout = QGridLayout(param_group)

        # Threshold slider
        param_layout.addWidget(QLabel("Threshold"), 0, 0)
        self.sld_threshold = QSlider(Qt.Horizontal)
        self.sld_threshold.setRange(5, 40)
        self.sld_threshold.valueChanged.connect(self._on_threshold_changed)
        param_layout.addWidget(self.sld_threshold, 0, 1)
        self.lbl_threshold_val = QLabel("--")
        param_layout.addWidget(self.lbl_threshold_val, 0, 2)

        # Min contour area
        param_layout.addWidget(QLabel("Min Area"), 1, 0)
        self.sld_min_area = QSlider(Qt.Horizontal)
        self.sld_min_area.setRange(50, 500)
        self.sld_min_area.valueChanged.connect(self._on_min_area_changed)
        param_layout.addWidget(self.sld_min_area, 1, 1)
        self.lbl_min_area_val = QLabel("--")
        param_layout.addWidget(self.lbl_min_area_val, 1, 2)

        # Max contour area
        param_layout.addWidget(QLabel("Max Area"), 2, 0)
        self.sld_max_area = QSlider(Qt.Horizontal)
        self.sld_max_area.setRange(1000, 5000)
        self.sld_max_area.valueChanged.connect(self._on_max_area_changed)
        param_layout.addWidget(self.sld_max_area, 2, 1)
        self.lbl_max_area_val = QLabel("--")
        param_layout.addWidget(self.lbl_max_area_val, 2, 2)

        # Position smoothing
        param_layout.addWidget(QLabel("Pos Smooth %"), 3, 0)
        self.sld_smooth = QSlider(Qt.Horizontal)
        self.sld_smooth.setRange(0, 100)
        self.sld_smooth.valueChanged.connect(self._on_smooth_changed)
        param_layout.addWidget(self.sld_smooth, 3, 1)
        self.lbl_smooth_val = QLabel("--")
        param_layout.addWidget(self.lbl_smooth_val, 3, 2)

        ctrl_layout.addWidget(param_group)
        
    def _setup_realsense_controls(self, ctrl_layout):
        """Setup RealSense camera controls."""
        self.rs_group = QGroupBox("RealSense Settings")
        rs_layout = QGridLayout(self.rs_group)

        # Emitter toggle
        rs_layout.addWidget(QLabel("Emitter"), 0, 0)
        self.chk_emitter_on = QPushButton("IR Emitter ON/OFF")
        self.chk_emitter_on.setCheckable(True)
        self.chk_emitter_on.toggled.connect(self._on_emitter_toggled)
        rs_layout.addWidget(self.chk_emitter_on, 0, 1)

        # Laser power slider
        rs_layout.addWidget(QLabel("Laser Power"), 1, 0)
        self.sld_laser_power = QSlider(Qt.Horizontal)
        self.sld_laser_power.setRange(0, 360)
        self.sld_laser_power.valueChanged.connect(self._on_laser_power_changed)
        rs_layout.addWidget(self.sld_laser_power, 1, 1)
        self.lbl_laser_val = QLabel("--")
        rs_layout.addWidget(self.lbl_laser_val, 1, 2)

        # Visual preset dropdown
        rs_layout.addWidget(QLabel("Visual Preset"), 2, 0)
        self.cmb_preset = QComboBox()
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        rs_layout.addWidget(self.cmb_preset, 2, 1, 1, 2)

        # Auto-Exposure toggle
        rs_layout.addWidget(QLabel("AE"), 3, 0)
        self.chk_auto_exposure = QPushButton("Auto Exposure")
        self.chk_auto_exposure.setCheckable(True)
        self.chk_auto_exposure.toggled.connect(self._on_ae_toggled)
        rs_layout.addWidget(self.chk_auto_exposure, 3, 1)

        # Manual Exposure slider
        rs_layout.addWidget(QLabel("Exposure µs"), 4, 0)
        self.sld_exposure = QSlider(Qt.Horizontal)
        self.sld_exposure.setRange(1, 33000)
        self.sld_exposure.valueChanged.connect(self._on_exposure_changed)
        rs_layout.addWidget(self.sld_exposure, 4, 1)
        self.lbl_exp_val = QLabel("--")
        rs_layout.addWidget(self.lbl_exp_val, 4, 2)

        # Gain slider
        rs_layout.addWidget(QLabel("Gain"), 5, 0)
        self.sld_gain = QSlider(Qt.Horizontal)
        self.sld_gain.setRange(0, 16)
        self.sld_gain.valueChanged.connect(self._on_gain_changed)
        rs_layout.addWidget(self.sld_gain, 5, 1)
        self.lbl_gain_val = QLabel("--")
        rs_layout.addWidget(self.lbl_gain_val, 5, 2)

        ctrl_layout.addWidget(self.rs_group)
        self.rs_group.setVisible(False)  # Hide until RealSense detected
        
    def _setup_crop_controls(self, ctrl_layout):
        """Setup crop configuration controls."""
        crop_group = QGroupBox("Crop Settings")
        crop_layout = QGridLayout(crop_group)
        
        crop_layout.addWidget(QLabel("Enable Crop"), 0, 0)
        self.chk_crop_enable = QCheckBox()
        self.chk_crop_enable.setChecked(True)
        crop_layout.addWidget(self.chk_crop_enable, 0, 1)

        crop_layout.addWidget(QLabel("x1"), 1, 0)
        self.spin_x1 = QSpinBox(maximum=640)
        crop_layout.addWidget(self.spin_x1, 1, 1)

        crop_layout.addWidget(QLabel("y1"), 1, 2)
        self.spin_y1 = QSpinBox(maximum=480)
        crop_layout.addWidget(self.spin_y1, 1, 3)

        crop_layout.addWidget(QLabel("x2"), 2, 0)
        self.spin_x2 = QSpinBox(maximum=640)
        crop_layout.addWidget(self.spin_x2, 2, 1)

        crop_layout.addWidget(QLabel("y2"), 2, 2)
        self.spin_y2 = QSpinBox(maximum=480)
        crop_layout.addWidget(self.spin_y2, 2, 3)

        self.btn_apply_crop = QPushButton("Apply Crop")
        self.btn_apply_crop.clicked.connect(self._on_apply_crop)
        crop_layout.addWidget(self.btn_apply_crop, 3, 0, 1, 4)

        ctrl_layout.addWidget(crop_group)
        
    def _setup_action_buttons(self, ctrl_layout):
        """Setup action buttons."""
        # Auto-threshold helper
        self.btn_auto_thresh = QPushButton("Auto Threshold")
        self.btn_auto_thresh.setToolTip("Analyze the current frame and suggest a detection threshold")
        self.btn_auto_thresh.clicked.connect(self._on_auto_threshold)
        ctrl_layout.addWidget(self.btn_auto_thresh)

        # Adaptive threshold toggle
        self.chk_adapt_thresh = QPushButton("Adaptive Threshold")
        self.chk_adapt_thresh.setCheckable(True)
        self.chk_adapt_thresh.setToolTip("Continuously tune threshold to keep foreground pixel ratio in optimal range")
        self.chk_adapt_thresh.toggled.connect(self._on_adapt_toggled)
        ctrl_layout.addWidget(self.chk_adapt_thresh)

        # Save buttons
        self.btn_save_rs = QPushButton("Save Camera Settings")
        self.btn_save_rs.clicked.connect(self._on_save_rs_settings)
        ctrl_layout.addWidget(self.btn_save_rs)

        self.btn_save_detection = QPushButton("Save Detection Settings")
        self.btn_save_detection.clicked.connect(self._on_save_detection_settings)
        ctrl_layout.addWidget(self.btn_save_detection)

        self.btn_reset_detection = QPushButton("Reset Detection Params")
        self.btn_reset_detection.setToolTip("Restore threshold and contour area parameters to factory defaults")
        self.btn_reset_detection.clicked.connect(self._on_reset_detection)
        ctrl_layout.addWidget(self.btn_reset_detection)

        # Point cloud preview
        self.btn_pointcloud = QPushButton("Point Cloud Preview")
        self.btn_pointcloud.setToolTip("Open real-time 3-D point cloud window (RealSense)")
        self.btn_pointcloud.setEnabled(False)
        self.btn_pointcloud.clicked.connect(self._on_pointcloud_clicked)
        ctrl_layout.addWidget(self.btn_pointcloud)
        
    def _setup_timer(self):
        """Setup the refresh timer."""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_frames)
        self._timer.start(30)
        self._fps_last_ts = time.perf_counter()
        self._fps_frame_count = 0
        
    # Event handlers - EDA COMPLIANT
    def _on_threshold_changed(self, val: int):
        """Handle threshold slider change - publishes EDA event."""
        self.lbl_threshold_val.setText(str(val))
        if hasattr(self, 'event_broker') and self.event_broker:
            # EDA PATTERN: Publish event instead of direct worker access
            from ..core.events import ChangeTrackerSettings
            self.event_broker.publish(ChangeTrackerSettings(threshold=val))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            # Callback for EDA integration during transition
            self._eda_callback('update_tracker_settings', threshold=val)
    
    def _update_detector_param(self, attr: str, value: int):
        """DEPRECATED: Direct detector access - replaced by EDA events."""
        # This method is deprecated and should not be used in EDA mode
        print(f"[WARNING] Direct detector param update deprecated: {attr}={value}")
        print("[WARNING] Use EDA event publishing instead")
            
    # All event handlers - EDA COMPLIANT
    def _on_min_area_changed(self, val: int):
        """Handle min area change - publishes EDA event."""
        self.lbl_min_area_val.setText(str(val))
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeTrackerSettings
            self.event_broker.publish(ChangeTrackerSettings(min_area=val))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_tracker_settings', min_area=val)
        
    def _on_max_area_changed(self, val: int):
        """Handle max area change - publishes EDA event."""
        self.lbl_max_area_val.setText(str(val))
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeTrackerSettings
            self.event_broker.publish(ChangeTrackerSettings(max_area=val))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_tracker_settings', max_area=val)
        
    def _on_smooth_changed(self, val: int):
        """Handle smoothing change - publishes EDA event."""
        self.lbl_smooth_val.setText(str(val))
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeTrackerSettings
            self.event_broker.publish(ChangeTrackerSettings(smoothing_alpha=val / 100.0))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_tracker_settings', smoothing_alpha=val / 100.0)
            
    def _on_invert_toggled(self, checked: bool):
        """Handle IR invert toggle - publishes EDA event."""
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeTrackerSettings
            self.event_broker.publish(ChangeTrackerSettings(invert_ir=checked))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_tracker_settings', invert_ir=checked)
            
    def _on_emitter_toggled(self, checked: bool):
        """Handle emitter toggle - publishes EDA event."""
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeRealSenseSettings
            self.event_broker.publish(ChangeRealSenseSettings(emitter_enabled=checked))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_realsense_settings', emitter_enabled=checked)
            
    def _on_laser_power_changed(self, val: int):
        """Handle laser power change - publishes EDA event."""
        self.lbl_laser_val.setText(str(val))
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeRealSenseSettings
            self.event_broker.publish(ChangeRealSenseSettings(laser_power=val))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_realsense_settings', laser_power=val)
            
    def _on_preset_changed(self, idx: int):
        """Handle visual preset change - publishes EDA event."""
        if idx < 0:
            return
        val = self.cmb_preset.itemData(idx)
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeRealSenseSettings
            self.event_broker.publish(ChangeRealSenseSettings(visual_preset=int(val)))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_realsense_settings', visual_preset=int(val))
            
    def _on_ae_toggled(self, checked: bool):
        """Handle auto-exposure toggle - publishes EDA event."""
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeRealSenseSettings
            self.event_broker.publish(ChangeRealSenseSettings(enable_auto_exposure=checked))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_realsense_settings', enable_auto_exposure=checked)
            
    def _on_exposure_changed(self, val: int):
        """Handle exposure change - publishes EDA event."""
        self.lbl_exp_val.setText(str(val))
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeRealSenseSettings
            self.event_broker.publish(ChangeRealSenseSettings(exposure=val))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_realsense_settings', exposure=val)
            
    def _on_gain_changed(self, val: int):
        """Handle gain change - publishes EDA event."""
        self.lbl_gain_val.setText(str(val))
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeRealSenseSettings
            self.event_broker.publish(ChangeRealSenseSettings(gain=val))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_realsense_settings', gain=val)
            
    def _on_save_rs_settings(self):
        if self._worker and self._worker.is_alive():
            ok = self._worker.save_current_rs_settings()
            QMessageBox.information(self, "Save Settings", "Settings saved." if ok else "Unable to save settings.")
            
    def _on_save_detection_settings(self):
        if not (self._worker and self._worker.is_alive()):
            QMessageBox.warning(self, "Save Error", "Tracker must be running to read current detector settings.")
            return
        # Implementation here...
        
    def _on_reset_detection(self):
        defaults = {"threshold": 15, "min_contour_area": 100, "large_contour_area": 2000}
        self.sld_threshold.setValue(defaults["threshold"])
        self.sld_min_area.setValue(defaults["min_contour_area"])
        self.sld_max_area.setValue(defaults["large_contour_area"])
        QMessageBox.information(self, "Detection", "Detection parameters reset to defaults.")
        
    def _on_apply_crop(self):
        """Apply crop settings - publishes EDA event."""
        x1, y1 = self.spin_x1.value(), self.spin_y1.value()
        x2, y2 = self.spin_x2.value(), self.spin_y2.value()
        if x2 <= x1 + 10 or y2 <= y1 + 10:
            QMessageBox.warning(self, "Crop", "Invalid crop rectangle dimensions.")
            return
        enabled = self.chk_crop_enable.isChecked()
        
        if hasattr(self, 'event_broker') and self.event_broker:
            # EDA PATTERN: Publish crop settings event
            from ..core.events import ChangeCropSettings
            self.event_broker.publish(ChangeCropSettings(
                enabled=enabled, x1=x1, y1=y1, x2=x2, y2=y2
            ))
            QMessageBox.information(self, "Crop", "Crop settings applied via EDA.")
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_crop_settings', 
                             enabled=enabled, x1=x1, y1=y1, x2=x2, y2=y2)
            QMessageBox.information(self, "Crop", "Crop settings applied via EDA.")
        else:
            # Legacy fallback
            if not (self._worker and self._worker.is_alive()):
                QMessageBox.warning(self, "Crop", "Tracker must be running to apply crop.")
                return
            self._worker.set_crop(x1, y1, x2, y2, enabled)
            QMessageBox.information(self, "Crop", "Crop updated and saved (legacy mode).")
        
    def _on_auto_threshold(self):
        if not (self._worker and self._worker.is_alive()):
            QMessageBox.warning(self, "Auto Threshold", "Tracker must be running to analyze frame.")
            return
        # Implementation here...
        
    def _on_adapt_toggled(self, checked: bool):
        """Handle adaptive threshold toggle - publishes EDA event."""
        if hasattr(self, 'event_broker') and self.event_broker:
            from ..core.events import ChangeTrackerSettings
            self.event_broker.publish(ChangeTrackerSettings(adaptive_threshold=checked))
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            self._eda_callback('update_tracker_settings', adaptive_threshold=checked)
        else:
            # Legacy fallback
            if self._worker and self._worker.is_alive():
                self._worker.set_adaptive_threshold(checked)
            
    def _on_pointcloud_clicked(self):
        if not (self._worker and self._worker.is_alive() and isinstance(self._worker._camera, RealsenseStream)):
            QMessageBox.information(self, "Point Cloud", "RealSense camera not active.")
            return
        # Point cloud implementation here...
        
    def _open_calibration_wizard(self):
        wizard = CalibrationWizard(self._get_worker)
        wizard.exec()
        
    def _get_worker(self):
        return self._worker
        
    # EDA LIFECYCLE MANAGEMENT - CRITICAL FIX
    def _start_tracking(self):
        """DEPRECATED: Direct worker creation replaced by EDA events."""
        print("[WARNING] _start_tracking() deprecated - use EDA events")
        if hasattr(self, 'event_broker') and self.event_broker:
            # EDA PATTERN: Publish event instead of direct worker creation
            from ..core.events import StartTracking
            self.event_broker.publish(StartTracking(
                dev_mode=self._dev_mode,
                cam_src=self._cam_src
            ))
            self._status_cb("Tracker Setup: tracking start requested via EDA")
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            # Callback for EDA integration during transition
            self._eda_callback('request_start_tracking', 
                             dev_mode=self._dev_mode, cam_src=self._cam_src)
        else:
            # Legacy fallback for testing only
            print("[WARNING] Using legacy tracking start - EDA not available")
            self._legacy_start_tracking()
    
    def _legacy_start_tracking(self):
        """Legacy worker creation for compatibility."""
        if self._worker and self._worker.is_alive():
            return
        self._stop_event = Event()
        self._worker = TrackingWorker(self._stop_event, dev_mode=self._dev_mode, src=self._cam_src)
        self._worker.start()
        
        if self._worker.error_msg:
            QMessageBox.warning(self, "Camera Warning", self._worker.error_msg)
        self._status_cb("Tracker Setup: tracking active (legacy mode)")
        
        # Initialize UI with worker values
        self._initialize_ui_from_worker()
        
    def _initialize_ui_from_worker(self):
        """Initialize UI controls from worker state (legacy compatibility)."""
        if not self._worker:
            return
            
        det = self._worker._detector
        self.sld_threshold.setValue(det.threshold)
        self.lbl_threshold_val.setText(str(det.threshold))
        self.sld_min_area.setValue(det.min_contour_area)
        self.lbl_min_area_val.setText(str(det.min_contour_area))
        self.sld_max_area.setValue(det.large_contour_area)
        self.lbl_max_area_val.setText(str(det.large_contour_area))

        # Populate crop UI
        crop_enabled = self._worker._crop_enabled
        (x1, y1), (x2, y2) = self._worker._crop_rect
        self.chk_crop_enable.setChecked(crop_enabled)
        self.spin_x1.setValue(x1)
        self.spin_y1.setValue(y1)
        self.spin_x2.setValue(x2)
        self.spin_y2.setValue(y2)
        
    def stop_tracking(self):
        """DEPRECATED: Direct worker stop replaced by EDA events."""
        print("[WARNING] stop_tracking() deprecated - use EDA events")
        if hasattr(self, 'event_broker') and self.event_broker:
            # EDA PATTERN: Publish event instead of direct worker stop
            from ..core.events import StopTracking
            self.event_broker.publish(StopTracking())
            self._status_cb("Tracker Setup: tracking stop requested via EDA")
        elif hasattr(self, '_eda_callback') and self._eda_callback:
            # Callback for EDA integration during transition
            self._eda_callback('request_stop_tracking')
        else:
            # Legacy fallback
            print("[WARNING] Using legacy tracking stop - EDA not available")
            if self._worker:
                self._worker.stop()
                self._worker = None
            self.btn_pointcloud.setEnabled(False)
        
    def _refresh_frames(self):
        """Refresh the video feed displays."""
        # Detect worker thread failures
        if self._worker and not self._worker.is_alive():
            if self._worker.error_msg:
                msg = self._worker.error_msg
                self._worker.error_msg = None
                QMessageBox.critical(self, "Camera Error", f"Tracking stopped: {msg}")
            self.stop_tracking()
            return

        if not (self._worker and self._worker.latest_display is not None):
            return
            
        frame = self._worker.latest_display
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt_main = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.live_feed_lbl.setPixmap(QPixmap.fromImage(qt_main.scaled(self.live_feed_lbl.size(), Qt.KeepAspectRatio)))

        dbg = self._worker.latest_thresh if self._worker.latest_thresh is not None else frame
        dbg_rgb = cv2.cvtColor(dbg, cv2.COLOR_BGR2RGB)
        qt_dbg = QImage(dbg_rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.debug_feed_lbl.setPixmap(QPixmap.fromImage(qt_dbg.scaled(self.debug_feed_lbl.size(), Qt.KeepAspectRatio)))

        # Update FPS
        self._fps_frame_count += 1
        now = time.perf_counter()
        if now - self._fps_last_ts >= 1.0:
            fps_val = self._fps_frame_count / (now - self._fps_last_ts)
            self.lbl_fps.setText(f"FPS: {fps_val:.1f}")
            self._fps_last_ts = now
            self._fps_frame_count = 0

        # Update camera status
        if isinstance(self._worker._camera, RealsenseStream):
            cam_name = "RealSense"
            self.btn_pointcloud.setEnabled(True)
        elif isinstance(self._worker._camera, VideoFileStream):
            cam_name = "VideoFile"
        else:
            cam_name = "Webcam"
            
        self.lbl_rs_detected.setText(f"Intel RealSense Detected: {'YES' if cam_name=='RealSense' else 'NO'}")
        self.rs_group.setVisible(cam_name == "RealSense")
        
    # Qt lifecycle methods
    def showEvent(self, event):
        """Start tracking when page becomes visible."""
        super().showEvent(event)
        self._start_tracking()

    def hideEvent(self, event):
        """Stop tracking when page is hidden."""
        self.stop_tracking()
        super().hideEvent(event)

    def closeEvent(self, event):
        """Stop tracking when page is closed."""
        self.stop_tracking()
        super().closeEvent(event) 