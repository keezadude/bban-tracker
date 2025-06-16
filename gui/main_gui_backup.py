from __future__ import annotations

import sys
from pathlib import Path
from threading import Thread, Event
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QImage, QPixmap, QPalette, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolBar,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QGroupBox,
    QGridLayout,
    QGraphicsOpacityEffect,
    QSlider,
    QComboBox,
    QCheckBox,
    QSpinBox,
)

from ..camera import RealsenseStream, WebcamVideoStream
from ..camera import VideoFileStream
from ..detector import Detector
from ..registry import Registry
from .calibration_wizard import CalibrationWizard, LAYOUT_FILE, _load_json, _save_json
import pyrealsense2 as rs


# -------------------- Global config paths -------------------- #
_CONFIG_DIR = Path.home() / ".beytracker"
_CONFIG_DIR.mkdir(exist_ok=True)
RS_SETTINGS_FILE = _CONFIG_DIR / "rs_settings.json"
CROP_SETTINGS_FILE = _CONFIG_DIR / "crop_settings.json"
GUI_PREFS_FILE = _CONFIG_DIR / "gui_prefs.json"


class TrackingWorker(Thread):
    """Background thread that runs the core tracking loop and exposes latest frames/results."""

    def __init__(self, stop_event: Event, *, dev_mode: bool = False, src: int = 0, video_path: str | None = None):
        super().__init__(daemon=True)
        self._stop_event = stop_event
        # Placeholder for error propagation to UI; will be set if initialisation or
        # runtime failures occur.
        self.error_msg: Optional[str] = None
        # Attempt to initialise the requested camera source.  If a RealSense device is not
        # available (common during development on laptops without the hardware attached)
        # we transparently fall back to a standard webcam so that the GUI remains usable.
        try:
            if video_path:
                self._camera = VideoFileStream(video_path).start()
            elif dev_mode:
                self._camera = WebcamVideoStream(src=src).start()
            else:
                self._camera = RealsenseStream().start()
            # Apply persisted RealSense settings if available
            self._apply_saved_rs_settings()
        except Exception as cam_exc:
            # Graceful degradation – log and fall back to webcam while surfacing the
            # issue to the GUI thread via `error_msg` so the user is aware of the
            # degraded mode.
            self.error_msg = (
                "RealSense initialisation failed ({}). Falling back to default webcam. "
                "Tracking performance may be reduced.".format(cam_exc)
            )
            self._camera = WebcamVideoStream(src=src).start()
        # warm-up
        for _ in range(20):
            self._get_cropped_frame()
        self._detector = Detector()
        # Calibrate on cropped frames to ensure consistent background modelling
        self._detector.calibrate(lambda: self._get_cropped_frame())
        self._registry = Registry()
        self.latest_display: Optional[np.ndarray] = None
        self.latest_thresh: Optional[np.ndarray] = None

        # User-controllable flags
        self.invert_ir: bool = False  # if True, apply cv2.bitwise_not before detection
        # --- NEW: adaptive threshold tuning (optional) --- #
        self._adapt_thresh_enabled: bool = False  # runtime toggle
        self._is_video_file = video_path is not None

        # ---------------- Crop settings (match legacy tracker) ---------------- #
        # Crop is applied to every frame before calibration/detection so that the
        # GUI-based tracker mirrors the behaviour of the original CLI version
        # defined in `main.py::CROP_SIZE`.
        self._crop_enabled: bool = True
        self._crop_rect: tuple[tuple[int, int], tuple[int, int]] = ((150, 15), (500, 350))

        # Try load persisted crop settings
        try:
            crop_cfg, _ = _load_json(CROP_SETTINGS_FILE, {})
            if crop_cfg and all(k in crop_cfg for k in ("x1", "y1", "x2", "y2")):
                self._crop_rect = ((int(crop_cfg["x1"]), int(crop_cfg["y1"])), (int(crop_cfg["x2"]), int(crop_cfg["y2"])) )
                self._crop_enabled = bool(crop_cfg.get("enabled", True))
        except Exception:
            pass

        # ---------------- Load persisted smoothing factor (Better Tracking) ---------------- #
        try:
            from .calibration_wizard import CALIB_PROFILE_FILE, _load_json  # type: ignore
            from objects import set_smoothing_alpha  # global helper

            prof, _ = _load_json(CALIB_PROFILE_FILE, {}) if callable(_load_json) else ({}, None)
            smooth_pct = int(prof.get("last", {}).get("smooth", 20))
            set_smoothing_alpha(smooth_pct / 100.0)
        except Exception:
            # On any failure fall back to default (20 %)
            pass

        # ----------------------- Networking Setup (UDP + TCP) ----------------------- #
        import socket
        self._HOST = "127.0.0.1"
        self._UDP_PORT = 50007
        self._TCP_PORT = 50008

        # UDP – fire-and-forget client (Unity listens)
        self._udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # TCP – tracker acts **server**, Unity connects once at startup
        self._tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._tcp_server.bind((self._HOST, self._TCP_PORT))
            self._tcp_server.listen(1)
            self._tcp_server.setblocking(False)
        except OSError as e:
            # Non-fatal – another tracker instance may already be listening (CLI)
            self.error_msg = (
                f"Networking disabled – unable to bind port {self._TCP_PORT}: {e}. "
                "Unity integration will not be available."
            )
            self._tcp_server = None
        self._tcp_client_socket = None

    def run(self) -> None:  # noqa: D401
        """Infinite tracking loop that updates `latest_display`."""
        while not self._stop_event.is_set():
            try:
                frame_full = self._camera.readNext()
                frame = self._apply_crop(frame_full)
                if frame is None:
                    raise RuntimeError("Camera returned None frame")
                if self.invert_ir:
                    frame = cv2.bitwise_not(frame)
            except Exception:
                # Attempt reconnection; break loop if fails
                if not self._reconnect_camera():
                    # final failure: hand off message and exit
                    self.latest_display = None
                    self.latest_thresh = None
                    return
                else:
                    # Successfully reconnected; continue loop
                    continue

            # Normal processing path
            beys, hits = self._detector.detect(frame)
            self._registry.register(beys, hits)
            result_img, thresh_img = self._draw_overlay(frame.copy(), beys, hits)
            self.latest_display = result_img
            self.latest_thresh = thresh_img if thresh_img is not None else None
            self._registry.nextFrame()

            # ---------------- Adaptive Threshold Logic ---------------- #
            if self._adapt_thresh_enabled and thresh_img is not None:
                try:
                    mask = cv2.cvtColor(thresh_img, cv2.COLOR_BGR2GRAY) if len(thresh_img.shape) == 3 else thresh_img
                    total = mask.size
                    fg_px = int(np.count_nonzero(mask))
                    ratio = fg_px / total if total else 0.0
                    # simple proportional control: keep ratio within 0.001 – 0.01 (~0.1–1 %)
                    if ratio > 0.015 and self._detector.threshold < 40:
                        self._detector.threshold += 1
                    elif ratio < 0.0005 and self._detector.threshold > 5:
                        self._detector.threshold -= 1
                except Exception:
                    pass

            # ----------------------- Networking: send & receive ----------------------- #
            self._broadcast_frame()
            self._process_tcp_messages()

        self.latest_thresh = None

        # Close networking resources
        try:
            if hasattr(self, "_udp_client") and self._udp_client:
                self._udp_client.close()
        except Exception:
            pass
        if self._tcp_client_socket:
            try:
                self._tcp_client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._tcp_client_socket.close()
            except Exception:
                pass
        if self._tcp_server:
            try:
                self._tcp_server.close()
            except Exception:
                pass

    def _draw_overlay(self, ir_img: np.ndarray, beys, hits):
        # Use existing drawResults function for consistency
        from ..main import drawResults  # local import to avoid circular at top

        result, _ = drawResults(ir_img, beys, hits, self._registry)
        # Also create a simple threshold debug view (binary mask visualisation)
        gray = ir_img if len(ir_img.shape) == 2 else cv2.cvtColor(ir_img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, int(self._detector.threshold * 5), 255, cv2.THRESH_BINARY)
        thresh_rgb = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
        return result, thresh_rgb

    def stop(self):
        self._stop_event.set()
        self.join(timeout=2)
        # Ensure underlying camera threads/pipelines are released to prevent resource leaks
        try:
            if hasattr(self, "_camera") and self._camera is not None:
                self._camera.close()
        except Exception:
            # Suppress any errors during shutdown to avoid secondary exceptions on exit
            pass

    # ----------------------- Internal helpers ----------------------- #
    def _reconnect_camera(self):
        """Attempt to reopen RealSense; fall back to webcam if unavailable.

        Sets an informative error message for the UI thread. Returns True if a new
        camera stream was opened successfully, else False (thread should stop)."""
        import time

        # Close old camera if possible
        try:
            if hasattr(self, "_camera") and self._camera is not None:
                self._camera.close()
        except Exception:
            pass

        # Try RealSense first (unless already webcam-only)
        try:
            self._camera = RealsenseStream().start()
            self.error_msg = "Camera link re-established with Intel RealSense."  # info only
            # quick warm-up
            for _ in range(10):
                self._get_cropped_frame()
            # Apply persisted RealSense settings if available
            self._apply_saved_rs_settings()
            return True
        except Exception as rs_exc:
            # Fallback to webcam
            try:
                self._camera = WebcamVideoStream(src=0).start()
                self.error_msg = (
                    f"RealSense lost ({rs_exc}). Switched to default webcam." )
                for _ in range(10):
                    self._get_cropped_frame()
                return True
            except Exception as cam_exc:
                self.error_msg = f"Unable to reopen any camera: {cam_exc}"
                return False

    # ======================= Networking helpers ======================= #

    def _broadcast_frame(self):
        """Send the latest registry snapshot to Unity via UDP."""
        if not hasattr(self, "_udp_client") or self._udp_client is None:
            return
        try:
            msg = self._registry.getMessage()
            self._udp_client.sendto(msg.encode("utf-8"), (self._HOST, self._UDP_PORT))
        except Exception:
            # UDP is best-effort; swallow any errors silently
            pass

    def _accept_client_if_needed(self):
        if self._tcp_server is None or self._tcp_client_socket is not None:
            return
        import socket
        try:
            client, _addr = self._tcp_server.accept()
            client.setblocking(False)
            self._tcp_client_socket = client
            print("Unity connected via TCP command channel.")

            # ---------------- Projection auto-sync ---------------- #
            # Send currently active projection layout so Unity instantly
            # aligns its render target without requiring the operator to
            # re-apply the settings manually.
            self._send_current_projection()
        except BlockingIOError:
            pass  # no pending connection
        except Exception as e:
            self.error_msg = f"TCP accept failed: {e}"

    def _process_tcp_messages(self):
        """Handle inbound calibration / threshold commands from Unity."""
        # First accept a client if none
        self._accept_client_if_needed()
        if self._tcp_client_socket is None:
            return
        try:
            data = self._tcp_client_socket.recv(1024)
            if not data:
                # disconnected
                self._tcp_client_socket.close()
                self._tcp_client_socket = None
                return
            message = data.decode().strip()
            if message == "calibrate":
                self._detector.calibrate(lambda: self._get_cropped_frame())
                self._tcp_client_socket.send(b"calibrated")
            elif message == "threshold_up":
                self._detector.threshold += 1
                reply = f"threshold:{self._detector.threshold}".encode("utf-8")
                self._tcp_client_socket.send(reply)
            elif message == "threshold_down":
                self._detector.threshold -= 1
                reply = f"threshold:{self._detector.threshold}".encode("utf-8")
                self._tcp_client_socket.send(reply)
            elif message.startswith("projection:"):
                # For completeness – Unity should not send this, but ignore gracefully
                pass
        except BlockingIOError:
            pass  # no data to read – normal
        except ConnectionResetError:
            self._tcp_client_socket.close()
            self._tcp_client_socket = None
        except Exception as e:
            # Log & drop connection on any other error
            print(f"TCP channel error: {e}")
            try:
                self._tcp_client_socket.close()
            finally:
                self._tcp_client_socket = None

    # ---------------- Public API ---------------- #

    def send_projection_update(self, width: int, height: int):
        """Transmit a projection update command to Unity if a TCP client is connected."""
        if self._tcp_client_socket:
            try:
                cmd = f"projection:{width},{height}"
                self._tcp_client_socket.send(cmd.encode("utf-8"))
            except Exception:
                pass

    # ---------------- Internal helpers ---------------- #
    def _send_current_projection(self):
        """Load persisted layout profile and transmit to Unity (best-effort)."""
        if not self._tcp_client_socket:
            return
        try:
            cfg = _load_json(LAYOUT_FILE, {}).get("default", {})
            w = int(cfg.get("width", 0))
            h = int(cfg.get("height", 0))
            if w and h:
                cmd = f"projection:{w},{h}"
                self._tcp_client_socket.send(cmd.encode("utf-8"))
        except Exception:
            pass

    # ---------------- User-facing toggles ---------------- #

    def set_invert_ir(self, enable: bool):
        """Enable/disable IR inversion (single channel)."""
        self.invert_ir = bool(enable)

    # ---------------- Adaptive Thresh public API ---------------- #
    def set_adaptive_threshold(self, enable: bool):
        self._adapt_thresh_enabled = bool(enable)

    # ---------------- RealSense settings persistence ---------------- #
    def _apply_saved_rs_settings(self):
        if not isinstance(self._camera, RealsenseStream):
            return
        try:
            cfg, _ = _load_json(RS_SETTINGS_FILE, {})
            if not cfg:
                return
            cam = self._camera
            # Individual options – ignore errors silently
            if "emitter_enabled" in cfg:
                cam.set_option(rs.option.emitter_enabled, float(cfg["emitter_enabled"]))
            if "laser_power" in cfg:
                cam.set_option(rs.option.laser_power, float(cfg["laser_power"]))
            if "visual_preset" in cfg:
                cam.set_visual_preset(int(cfg["visual_preset"]))
            if "enable_auto_exposure" in cfg:
                cam.set_option(rs.option.enable_auto_exposure, float(cfg["enable_auto_exposure"]))
            if "exposure" in cfg:
                cam.set_option(rs.option.exposure, float(cfg["exposure"]))
            if "gain" in cfg:
                cam.set_option(rs.option.gain, float(cfg["gain"]))
                
            # Apply saved depth processing filter settings
            if "filters" in cfg:
                filters = cfg["filters"]
                
                # Master toggle
                if "master_enabled" in filters:
                    cam.set_postprocessing_enabled(bool(filters["master_enabled"]))
                
                # Decimation filter
                if "decimation" in filters:
                    dec = filters["decimation"]
                    if "enabled" in dec:
                        cam.set_decimation_enabled(bool(dec["enabled"]))
                    if "magnitude" in dec:
                        cam.set_decimation_magnitude(int(dec["magnitude"]))
                
                # Spatial filter
                if "spatial" in filters:
                    sp = filters["spatial"]
                    if "enabled" in sp:
                        cam.set_spatial_filter_enabled(bool(sp["enabled"]))
                    if "smooth_alpha" in sp and "smooth_delta" in sp:
                        cam.set_spatial_filter_params(
                            float(sp["smooth_alpha"]),
                            float(sp["smooth_delta"]),
                            float(sp.get("magnitude", 2.0))
                        )
                
                # Temporal filter
                if "temporal" in filters:
                    temp = filters["temporal"]
                    if "enabled" in temp:
                        cam.set_temporal_filter_enabled(bool(temp["enabled"]))
                    if "smooth_alpha" in temp and "smooth_delta" in temp:
                        cam.set_temporal_filter_params(
                            float(temp["smooth_alpha"]),
                            float(temp["smooth_delta"])
                        )
                
                # Hole filling filter
                if "hole_filling" in filters:
                    hole = filters["hole_filling"]
                    if "enabled" in hole:
                        cam.set_hole_filling_enabled(bool(hole["enabled"]))
                    if "mode" in hole:
                        cam.set_hole_filling_mode(int(hole["mode"]))
        except Exception:
            pass

    def save_current_rs_settings(self):
        """Capture current RealSense option values and persist to JSON."""
        if not isinstance(self._camera, RealsenseStream):
            return False
        try:
            cam = self._camera
            data = {
                "emitter_enabled": cam.get_option(rs.option.emitter_enabled),
                "laser_power": cam.get_option(rs.option.laser_power),
                "visual_preset": cam.get_visual_preset(),
                "enable_auto_exposure": cam.get_option(rs.option.enable_auto_exposure),
                "exposure": cam.get_option(rs.option.exposure),
                "gain": cam.get_option(rs.option.gain),
                # Add depth processing filter settings
                "filters": cam.get_filter_status()
            }
            _save_json(RS_SETTINGS_FILE, data)
            return True
        except Exception:
            return False

    def _apply_crop(self, frame: np.ndarray) -> np.ndarray:
        """Return cropped sub-image if cropping is enabled; otherwise the original."""
        if not self._crop_enabled:
            return frame
        (x1, y1), (x2, y2) = self._crop_rect
        return frame[y1:y2, x1:x2].copy()

    def _get_cropped_frame(self):
        """Helper compatible with Detector.calibrate() signature."""
        full = self._camera.readNext()
        return self._apply_crop(full)

    # ---------------- Crop configuration API ---------------- #
    def set_crop(self, x1: int, y1: int, x2: int, y2: int, enabled: bool = True, persist: bool = True):
        """Update crop rectangle and optionally persist to JSON."""
        self._crop_rect = ((x1, y1), (x2, y2))
        self._crop_enabled = enabled
        if persist:
            cfg = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "enabled": bool(enabled)}
            _save_json(CROP_SETTINGS_FILE, cfg)


class FreePlayPage(QWidget):
    """Free Play mode with minimal controls; uses TrackingWorker internally."""

    def __init__(self, status_cb, *, dev_mode: bool = False, cam_src: int = 0):
        super().__init__()
        self._status_cb = status_cb  # callable(str)
        self._dev_mode = dev_mode
        self._cam_src = cam_src

        # Layout hierarchy
        main_layout = QVBoxLayout(self)

        # --- Image preview --- #
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.image_label, stretch=1)

        # --- Tracker setup controls --- #
        setup_group = QGroupBox("Tracker Setup")
        grp_layout = QHBoxLayout(setup_group)
        main_layout.addWidget(setup_group)

        self.start_btn = QPushButton("Start Tracking")
        grp_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Tracking")
        self.stop_btn.setEnabled(False)
        grp_layout.addWidget(self.stop_btn)

        self.calibrate_btn = QPushButton("Re-calibrate")
        self.calibrate_btn.setEnabled(False)
        grp_layout.addWidget(self.calibrate_btn)

        # Invert IR toggle (useful for RealSense emitter-off scenarios)
        self.invert_btn = QPushButton("Invert IR Feed")
        self.invert_btn.setCheckable(True)
        self.invert_btn.setEnabled(False)
        grp_layout.addWidget(self.invert_btn)

        # Auto-threshold helper for quick tuning in Free Play
        self.btn_auto_thresh = QPushButton("Auto Threshold")
        self.btn_auto_thresh.setToolTip("Analyze current frame and suggest a detection threshold (mean+N*std) and apply if accepted.")
        self.btn_auto_thresh.setEnabled(False)
        grp_layout.addWidget(self.btn_auto_thresh)

        # Adaptive threshold toggle (mirrors Tracker Setup functionality)
        self.chk_adapt_thresh = QPushButton("Adaptive Threshold")
        self.chk_adapt_thresh.setCheckable(True)
        self.chk_adapt_thresh.setToolTip("Continuously tune threshold to keep foreground pixel ratio in optimal range.")
        self.chk_adapt_thresh.setEnabled(False)
        grp_layout.addWidget(self.chk_adapt_thresh)

        # Connect adaptive toggle
        self.chk_adapt_thresh.toggled.connect(self._on_adapt_toggled)

        # ---------------- Smoothing Control ---------------- #
        self.smooth_group = QGroupBox("Position Smoothing")
        smooth_layout = QHBoxLayout(self.smooth_group)
        self.sld_smooth = QSlider(Qt.Horizontal)
        self.sld_smooth.setRange(0, 100)
        smooth_layout.addWidget(self.sld_smooth)
        self.lbl_smooth_val = QLabel("--")
        smooth_layout.addWidget(self.lbl_smooth_val)
        main_layout.addWidget(self.smooth_group)

        # Connect smoothing slider after instantiation
        self.sld_smooth.valueChanged.connect(self._on_smooth_changed)

        # --- Navigation controls (to replicate Free Play Mode actions) --- #
        nav_group = QGroupBox()
        nav_layout = QHBoxLayout(nav_group)
        main_layout.addWidget(nav_group)

        self.btn_tracker_setup = QPushButton("Tracker Setup")
        nav_layout.addWidget(self.btn_tracker_setup)

        # External navigation callback (to be set by controller)
        self._open_tracker_setup_cb: Optional[callable] = None

        # Timer for refreshing display
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_frame)
        self._timer.start(30)

        # Worker thread (lazy-started when page is shown)
        self._stop_event: Optional[Event] = None
        self._worker: Optional[TrackingWorker] = None

        # Connect buttons after member init
        self.start_btn.clicked.connect(self.start_tracking)
        self.stop_btn.clicked.connect(self.stop_tracking)
        self.calibrate_btn.clicked.connect(self.open_calibration_wizard)
        self.invert_btn.toggled.connect(self._on_invert_toggled)
        self.btn_tracker_setup.clicked.connect(self._open_tracker_setup)
        self.btn_auto_thresh.clicked.connect(self._on_auto_threshold)
        self.chk_adapt_thresh.toggled.connect(self._on_adapt_toggled)

        # --- Video source info --- #
        self._video_path: Optional[str] = None  # currently loaded video (if any)

        # At end of __init__, no change

        # Add System Hub nav button
        self.btn_system_hub = QPushButton("System Hub")
        nav_layout.addWidget(self.btn_system_hub)
        # External callback stub
        self._open_system_hub_cb: Optional[callable] = None
        self.btn_system_hub.clicked.connect(self._open_system_hub)

    # add method
    def set_open_system_hub_cb(self, cb):
        self._open_system_hub_cb = cb

    def _open_system_hub(self):
        if self._open_system_hub_cb:
            self._open_system_hub_cb()

    # ----------------------- Worker control ----------------------- #
    def start_tracking(self):
        if self._worker and self._worker.is_alive():
            return
        self._stop_event = Event()
        self._worker = TrackingWorker(self._stop_event, dev_mode=self._dev_mode, src=self._cam_src, video_path=self._video_path)
        self._worker.start()
        # Notify user of any fallback or initialisation warnings
        if self._worker.error_msg:
            QMessageBox.warning(self, "Camera Warning", self._worker.error_msg)
        self._status_cb("Tracking started")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.calibrate_btn.setEnabled(True)
        self.invert_btn.setEnabled(True)
        self.btn_auto_thresh.setEnabled(True)
        self.chk_adapt_thresh.setEnabled(True)

        # Ensure invert state forwarded to worker on (re)start
        self._on_invert_toggled(self.invert_btn.isChecked())

        # Ensure smoothing slider reflects current global value on (re)start
        from objects import SMOOTH_ALPHA
        self.sld_smooth.blockSignals(True)
        self.sld_smooth.setValue(int(SMOOTH_ALPHA * 100))
        self.lbl_smooth_val.setText(str(int(SMOOTH_ALPHA * 100)))
        self.sld_smooth.blockSignals(False)

    def stop_tracking(self):
        if self._worker:
            self._worker.stop()
            self._worker = None
            self._status_cb("Tracking stopped")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.calibrate_btn.setEnabled(False)
        self.invert_btn.setEnabled(False)
        self.btn_auto_thresh.setEnabled(False)
        self.chk_adapt_thresh.setEnabled(False)
        self.invert_btn.setChecked(False)
        self.image_label.clear()
        self._video_path = None  # reset

    # Called by MainWindow to wire navigation
    def set_open_tracker_setup_cb(self, cb):
        self._open_tracker_setup_cb = cb

    def _open_tracker_setup(self):
        if self._open_tracker_setup_cb:
            self._open_tracker_setup_cb()

    # ----------------------- Utilities ----------------------- #
    def _refresh_frame(self):
        # Detect worker failure
        if self._worker and not self._worker.is_alive():
            # if died with error, show dialog once
            if self._worker.error_msg:
                msg = self._worker.error_msg
                # Reset to avoid duplicate dialogs
                self._worker.error_msg = None
                QMessageBox.critical(self, "Camera Error", f"Tracking stopped: {msg}")
                self.stop_tracking()

        if not (self._worker and self._worker.latest_display is not None):
            return
        frame = self._worker.latest_display
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        scaled = qt_image.scaled(QSize(self.image_label.width(), self.image_label.height()), Qt.KeepAspectRatio)
        self.image_label.setPixmap(QPixmap.fromImage(scaled))

        thresh_frame = self._worker.latest_thresh if self._worker.latest_thresh is not None else frame
        thresh_rgb = cv2.cvtColor(thresh_frame, cv2.COLOR_BGR2RGB)
        qt_thresh = QImage(thresh_rgb.data, w, h, 3 * w, QImage.Format_RGB888)

    # Calibration wizard access
    def _get_worker(self):
        return self._worker

    def open_calibration_wizard(self):
        wizard = CalibrationWizard(self._get_worker)
        wizard.exec()
        # Apply new layout immediately if saved
        main_win = self.window()
        if hasattr(main_win, "apply_saved_layout"):
            main_win.apply_saved_layout()

    # ----------------------- Invert IR ----------------------- #
    def _on_invert_toggled(self, checked: bool):
        if self._worker and self._worker.is_alive():
            self._worker.set_invert_ir(checked)

    # ----------------------- External video start ----------------------- #
    def start_video(self, path: str):
        """Start tracking worker using a prerecorded video instead of live camera."""
        self._video_path = path
        if self._worker and self._worker.is_alive():
            self.stop_tracking()
        self.start_tracking()

    # ---------------- Auto-threshold logic ---------------- #
    def _on_auto_threshold(self):
        if not (self._worker and self._worker.is_alive()):
            QMessageBox.warning(self, "Auto Threshold", "Tracker must be running to analyze frame.")
            return
        try:
            gray = self._worker._get_cropped_frame().astype(np.float32)
            mu, sigma = gray.mean(), gray.std() + 1e-6
            z = (gray - mu) / sigma
            import numpy as np
            target = float(np.percentile(z, 99.5))
            suggested = int(max(5, min(40, round(target))))
            ret = QMessageBox.question(
                self,
                "Auto Threshold",
                f"Suggested threshold: {suggested}. Apply?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ret == QMessageBox.Yes:
                self._worker._detector.threshold = suggested
                self._status_cb(f"Threshold set to {suggested}")
        except Exception as exc:
            QMessageBox.warning(self, "Auto Threshold", f"Unable to compute suggestion: {exc}")

    # ----------------------- Smoothing Handler ----------------------- #
    def _on_smooth_changed(self, val: int):
        self.lbl_smooth_val.setText(str(val))
        try:
            from objects import set_smoothing_alpha
            set_smoothing_alpha(val / 100.0)

            # --- Persist smoothing factor to calibration profile ('last') --- #
            try:
                from .calibration_wizard import CALIB_PROFILE_FILE, _load_json, _save_json  # type: ignore
                prof, _ = _load_json(CALIB_PROFILE_FILE, {}) if callable(_load_json) else ({}, None)
                last = prof.get("last", {})
                last["smooth"] = int(val)
                prof["last"] = last
                _save_json(CALIB_PROFILE_FILE, prof)
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- Adaptive threshold handler ---------------- #
    def _on_adapt_toggled(self, checked: bool):
        if self._worker and self._worker.is_alive():
            self._worker.set_adaptive_threshold(checked)


# ----------------------------- System Hub Page ---------------------------- #


class SystemHubPage(QWidget):
    """Simple hub routing to various setup screens."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("BeysionXR Kiosk – System Hub")
        title.setStyleSheet("font-size:36px;font-weight:bold;color:#90EE90; padding: 10px;")
        layout.addWidget(title, alignment=Qt.AlignLeft)

        btn_row = QHBoxLayout()
        layout.addLayout(btn_row, stretch=1)

        self.btn_calibrate = QPushButton("Calibrate")
        btn_row.addWidget(self.btn_calibrate)

        self.btn_options = QPushButton("Options")
        btn_row.addWidget(self.btn_options)

        self.btn_projection = QPushButton("Projection")
        btn_row.addWidget(self.btn_projection)

        self.btn_tracker = QPushButton("Tracker")
        btn_row.addWidget(self.btn_tracker)

        # New: direct navigation to Free Play from System Hub
        self.btn_free_play = QPushButton("Free Play")
        btn_row.addWidget(self.btn_free_play)

        # Callbacks wired externally
        self.cb_open_tracker: Optional[callable] = None
        self.cb_open_free_play: Optional[callable] = None
        self.btn_tracker.clicked.connect(lambda: self.cb_open_tracker() if self.cb_open_tracker else None)
        self.btn_free_play.clicked.connect(lambda: self.cb_open_free_play() if self.cb_open_free_play else None)

    def _create_main_menu_button(self, text: str) -> QPushButton:
        # Match the main menu style
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


# --------------------------- Tracker Setup Page --------------------------- #


class TrackerSetupPage(QWidget):
    def __init__(self, status_cb, *, dev_mode: bool = False, cam_src: int = 0):
        super().__init__()
        self._status_cb = status_cb
        self._dev_mode = dev_mode
        self._cam_src = cam_src

        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()
        layout.addLayout(header_row)

        header = QLabel("TRACKER SETUP V2.1")
        header.setStyleSheet("font-size:24px;font-weight:bold;color:#baffc2;")
        header_row.addWidget(header, alignment=Qt.AlignLeft)

        header_row.addStretch(1)

        self.btn_recalibrate = QPushButton("Recalibrate")
        header_row.addWidget(self.btn_recalibrate)
        self.btn_recalibrate.clicked.connect(self._open_calibration_wizard)

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

        # ----- Control & Status ----- #
        self.ctrl_group = QGroupBox("Control & Status")
        ctrl_layout = QVBoxLayout(self.ctrl_group)

        self.lbl_rs_detected = QLabel("Intel RealSense Detected: UNKNOWN")
        ctrl_layout.addWidget(self.lbl_rs_detected)

        invert_layout = QHBoxLayout()
        self.chk_invert = QPushButton("Invert IR Feed")
        self.chk_invert.setCheckable(True)
        self.chk_invert.toggled.connect(self._on_invert_toggled)
        invert_layout.addWidget(self.chk_invert)
        ctrl_layout.addLayout(invert_layout)

        self.lbl_fps = QLabel("FPS: --")
        ctrl_layout.addWidget(self.lbl_fps)

        # ---------------- Detection Parameters (LIVE) ---------------- #
        param_group = QGroupBox("Detection Parameters")
        param_layout = QGridLayout(param_group)

        # Threshold slider
        param_layout.addWidget(QLabel("Threshold"), 0, 0)
        self.sld_threshold = QSlider(Qt.Horizontal)
        self.sld_threshold.setRange(5, 40)
        param_layout.addWidget(self.sld_threshold, 0, 1)
        self.lbl_threshold_val = QLabel("--")
        param_layout.addWidget(self.lbl_threshold_val, 0, 2)

        # Min contour area
        param_layout.addWidget(QLabel("Min Area"), 1, 0)
        self.sld_min_area = QSlider(Qt.Horizontal)
        self.sld_min_area.setRange(50, 500)
        param_layout.addWidget(self.sld_min_area, 1, 1)
        self.lbl_min_area_val = QLabel("--")
        param_layout.addWidget(self.lbl_min_area_val, 1, 2)

        # Max contour area
        param_layout.addWidget(QLabel("Max Area"), 2, 0)
        self.sld_max_area = QSlider(Qt.Horizontal)
        self.sld_max_area.setRange(1000, 5000)
        param_layout.addWidget(self.sld_max_area, 2, 1)
        self.lbl_max_area_val = QLabel("--")
        param_layout.addWidget(self.lbl_max_area_val, 2, 2)

        # ---------------- Position Smoothing ---------------- #
        param_layout.addWidget(QLabel("Pos Smooth %"), 3, 0)
        self.sld_smooth = QSlider(Qt.Horizontal)
        self.sld_smooth.setRange(0, 100)
        param_layout.addWidget(self.sld_smooth, 3, 1)
        self.lbl_smooth_val = QLabel("--")
        param_layout.addWidget(self.lbl_smooth_val, 3, 2)

        ctrl_layout.addWidget(param_group)

        # ---------------- RealSense Camera Controls ---------------- #
        self.rs_group = QGroupBox("RealSense Settings")
        rs_layout = QGridLayout(self.rs_group)

        # Emitter toggle
        self.chk_emitter_on = QPushButton("IR Emitter ON/OFF")
        self.chk_emitter_on.setCheckable(True)
        rs_layout.addWidget(QLabel("Emitter"), 0, 0)
        rs_layout.addWidget(self.chk_emitter_on, 0, 1)

        # Laser power slider
        rs_layout.addWidget(QLabel("Laser Power"), 1, 0)
        self.sld_laser_power = QSlider(Qt.Horizontal)
        self.sld_laser_power.setRange(0, 360)
        rs_layout.addWidget(self.sld_laser_power, 1, 1)
        self.lbl_laser_val = QLabel("--")
        rs_layout.addWidget(self.lbl_laser_val, 1, 2)

        # Visual Preset dropdown
        rs_layout.addWidget(QLabel("Visual Preset"), 2, 0)
        self.cmb_preset = QComboBox()
        rs_layout.addWidget(self.cmb_preset, 2, 1, 1, 2)

        # Auto-Exposure toggle
        self.chk_auto_exposure = QPushButton("Auto Exposure")
        self.chk_auto_exposure.setCheckable(True)
        rs_layout.addWidget(QLabel("AE"), 3, 0)
        rs_layout.addWidget(self.chk_auto_exposure, 3, 1)

        # Manual Exposure slider (µs)
        rs_layout.addWidget(QLabel("Exposure µs"), 4, 0)
        self.sld_exposure = QSlider(Qt.Horizontal)
        self.sld_exposure.setRange(1, 33000)  # RealSense typical range
        rs_layout.addWidget(self.sld_exposure, 4, 1)
        self.lbl_exp_val = QLabel("--")
        rs_layout.addWidget(self.lbl_exp_val, 4, 2)

        # Gain slider
        rs_layout.addWidget(QLabel("Gain"), 5, 0)
        self.sld_gain = QSlider(Qt.Horizontal)
        self.sld_gain.setRange(0, 16)
        rs_layout.addWidget(self.sld_gain, 5, 1)
        self.lbl_gain_val = QLabel("--")
        rs_layout.addWidget(self.lbl_gain_val, 5, 2)

        ctrl_layout.addWidget(self.rs_group)

        # ---------------- Depth Processing Controls for RealSense ---------------- #
        self.depth_proc_group = QGroupBox("Depth Processing")
        depth_proc_layout = QGridLayout(self.depth_proc_group)
        
        # Master toggle for all post-processing
        depth_proc_layout.addWidget(QLabel("Enable Processing"), 0, 0)
        self.chk_postproc_master = QPushButton("Post-Processing")
        self.chk_postproc_master.setCheckable(True)
        self.chk_postproc_master.setChecked(True)
        self.chk_postproc_master.clicked.connect(self._on_postproc_master_toggled)
        depth_proc_layout.addWidget(self.chk_postproc_master, 0, 1, 1, 2)
        
        # Decimation filter controls
        depth_proc_layout.addWidget(QLabel("Decimation Filter"), 1, 0)
        self.chk_decimate = QPushButton("Enable")
        self.chk_decimate.setCheckable(True)
        self.chk_decimate.setChecked(True)
        self.chk_decimate.clicked.connect(self._on_decimate_toggled)
        depth_proc_layout.addWidget(self.chk_decimate, 1, 1)
        
        depth_proc_layout.addWidget(QLabel("Magnitude:"), 2, 0)
        self.cmb_decimate_mag = QComboBox()
        for i in range(1, 9):
            self.cmb_decimate_mag.addItem(f"{i}×", i)
        self.cmb_decimate_mag.setCurrentIndex(1)  # Default to 2×
        self.cmb_decimate_mag.currentIndexChanged.connect(self._on_decimate_mag_changed)
        depth_proc_layout.addWidget(self.cmb_decimate_mag, 2, 1)
        
        # Spatial filter controls
        depth_proc_layout.addWidget(QLabel("Spatial Filter"), 3, 0)
        self.chk_spatial = QPushButton("Enable")
        self.chk_spatial.setCheckable(True)
        self.chk_spatial.setChecked(True)
        self.chk_spatial.clicked.connect(self._on_spatial_toggled)
        depth_proc_layout.addWidget(self.chk_spatial, 3, 1)
        
        depth_proc_layout.addWidget(QLabel("Smooth α:"), 4, 0)
        self.sld_spatial_alpha = QSlider(Qt.Horizontal)
        self.sld_spatial_alpha.setRange(0, 100)
        self.sld_spatial_alpha.setValue(50)  # Default 0.5
        self.sld_spatial_alpha.valueChanged.connect(self._on_spatial_alpha_changed)
        depth_proc_layout.addWidget(self.sld_spatial_alpha, 4, 1)
        self.lbl_spatial_alpha = QLabel("0.50")
        depth_proc_layout.addWidget(self.lbl_spatial_alpha, 4, 2)
        
        depth_proc_layout.addWidget(QLabel("Smooth Δ:"), 5, 0)
        self.sld_spatial_delta = QSlider(Qt.Horizontal)
        self.sld_spatial_delta.setRange(1, 100)
        self.sld_spatial_delta.setValue(20)  # Default 20
        self.sld_spatial_delta.valueChanged.connect(self._on_spatial_delta_changed)
        depth_proc_layout.addWidget(self.sld_spatial_delta, 5, 1)
        self.lbl_spatial_delta = QLabel("20")
        depth_proc_layout.addWidget(self.lbl_spatial_delta, 5, 2)
        
        # Temporal filter controls
        depth_proc_layout.addWidget(QLabel("Temporal Filter"), 6, 0)
        self.chk_temporal = QPushButton("Enable")
        self.chk_temporal.setCheckable(True)
        self.chk_temporal.setChecked(True)
        self.chk_temporal.clicked.connect(self._on_temporal_toggled)
        depth_proc_layout.addWidget(self.chk_temporal, 6, 1)
        
        depth_proc_layout.addWidget(QLabel("Smooth α:"), 7, 0)
        self.sld_temporal_alpha = QSlider(Qt.Horizontal)
        self.sld_temporal_alpha.setRange(0, 100)
        self.sld_temporal_alpha.setValue(40)  # Default 0.4
        self.sld_temporal_alpha.valueChanged.connect(self._on_temporal_alpha_changed)
        depth_proc_layout.addWidget(self.sld_temporal_alpha, 7, 1)
        self.lbl_temporal_alpha = QLabel("0.40")
        depth_proc_layout.addWidget(self.lbl_temporal_alpha, 7, 2)
        
        depth_proc_layout.addWidget(QLabel("Smooth Δ:"), 8, 0)
        self.sld_temporal_delta = QSlider(Qt.Horizontal)
        self.sld_temporal_delta.setRange(1, 100)
        self.sld_temporal_delta.setValue(20)  # Default 20
        self.sld_temporal_delta.valueChanged.connect(self._on_temporal_delta_changed)
        depth_proc_layout.addWidget(self.sld_temporal_delta, 8, 1)
        self.lbl_temporal_delta = QLabel("20")
        depth_proc_layout.addWidget(self.lbl_temporal_delta, 8, 2)
        
        # Hole filling filter controls
        depth_proc_layout.addWidget(QLabel("Hole Filling"), 9, 0)
        self.chk_hole = QPushButton("Enable")
        self.chk_hole.setCheckable(True)
        self.chk_hole.setChecked(True)
        self.chk_hole.clicked.connect(self._on_hole_toggled)
        depth_proc_layout.addWidget(self.chk_hole, 9, 1)
        
        depth_proc_layout.addWidget(QLabel("Mode:"), 10, 0)
        self.cmb_hole_mode = QComboBox()
        self.cmb_hole_mode.addItem("No Fill", 0)
        self.cmb_hole_mode.addItem("Nearest Neighbors", 1)
        self.cmb_hole_mode.addItem("Farthest Around Hole", 2)
        self.cmb_hole_mode.addItem("Nearest Lower Pixel", 3)
        self.cmb_hole_mode.addItem("Nearest Pixel", 4)
        self.cmb_hole_mode.setCurrentIndex(1)  # Default to nearest neighbors
        self.cmb_hole_mode.currentIndexChanged.connect(self._on_hole_mode_changed)
        depth_proc_layout.addWidget(self.cmb_hole_mode, 10, 1, 1, 2)
        
        # Add to control layout
        ctrl_layout.addWidget(self.depth_proc_group)
        self.depth_proc_group.setVisible(False)  # Hide until RealSense detected

        # Save settings button
        self.btn_save_rs = QPushButton("Save Camera Settings")
        self.btn_save_rs.clicked.connect(self._on_save_rs_settings)
        ctrl_layout.addWidget(self.btn_save_rs)

        # Save detection parameters button (persists threshold & area bounds)
        self.btn_save_detection = QPushButton("Save Detection Settings")
        self.btn_save_detection.clicked.connect(self._on_save_detection_settings)
        ctrl_layout.addWidget(self.btn_save_detection)

        # Reset detection parameters to defaults
        self.btn_reset_detection = QPushButton("Reset Detection Params")
        self.btn_reset_detection.setToolTip("Restore threshold and contour area parameters to factory defaults (15,100,2000).")
        self.btn_reset_detection.clicked.connect(self._on_reset_detection)
        ctrl_layout.addWidget(self.btn_reset_detection)

        # Connect RealSense control signals
        self.chk_emitter_on.toggled.connect(self._on_emitter_toggled)
        self.sld_laser_power.valueChanged.connect(self._on_laser_power_changed)
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        self.chk_auto_exposure.toggled.connect(self._on_ae_toggled)
        self.sld_exposure.valueChanged.connect(self._on_exposure_changed)
        self.sld_gain.valueChanged.connect(self._on_gain_changed)

        # Slider connections
        self.sld_threshold.valueChanged.connect(self._on_threshold_changed)
        self.sld_min_area.valueChanged.connect(self._on_min_area_changed)
        self.sld_max_area.valueChanged.connect(self._on_max_area_changed)

        # Auto-threshold helper
        self.btn_auto_thresh = QPushButton("Auto Threshold")
        self.btn_auto_thresh.setToolTip("Analyze the current frame and suggest a detection threshold (mean+N*std).")
        self.btn_auto_thresh.clicked.connect(self._on_auto_threshold)
        ctrl_layout.addWidget(self.btn_auto_thresh)

        # Adaptive threshold toggle
        adapt_row = QHBoxLayout()
        self.chk_adapt_thresh = QPushButton("Adaptive Threshold")
        self.chk_adapt_thresh.setCheckable(True)
        self.chk_adapt_thresh.setToolTip("Continuously tune threshold to keep foreground pixel ratio in optimal range.")
        self.chk_adapt_thresh.toggled.connect(self._on_adapt_toggled)
        adapt_row.addWidget(self.chk_adapt_thresh)
        ctrl_layout.addLayout(adapt_row)

        # Smoothing slider connection
        self.sld_smooth.valueChanged.connect(self._on_smooth_changed)

        # Detected objects table
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
        self.tbl_objects = QTableWidget(0, 4)
        self.tbl_objects.setHorizontalHeaderLabels(["ID", "Pos (X,Y)", "Velocity", "Status"])
        self.tbl_objects.verticalHeader().setVisible(False)
        ctrl_layout.addWidget(self.tbl_objects)

        layout.addWidget(self.ctrl_group)

        # Worker thread (lazy-started when page is shown)
        self._stop_event: Optional[Event] = None
        self._worker: Optional[TrackingWorker] = None

        # Timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_frames)
        self._timer.start(30)
        self._last_time = 0
        self._frame_counter = 0
        # FPS tracking helpers
        import time
        self._fps_last_ts = time.perf_counter()
        self._fps_frame_count = 0

        # Initially hide RealSense group until camera detected
        self.rs_group.setVisible(False)

        # ---------------- Crop Settings ---------------- #
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

        # -------- Point Cloud Preview (RealSense debug) -------- #
        self.btn_pointcloud = QPushButton("Point Cloud Preview")
        self.btn_pointcloud.setToolTip("Open real-time 3-D point cloud window (RealSense)")
        self.btn_pointcloud.setEnabled(False)
        self.btn_pointcloud.clicked.connect(self._on_pointcloud_clicked)
        ctrl_layout.addWidget(self.btn_pointcloud)

        self._pc_window = None  # lazily created widget

    def _start_tracking(self):
        if self._worker and self._worker.is_alive():
            return
        self._stop_event = Event()
        self._worker = TrackingWorker(self._stop_event, dev_mode=self._dev_mode, src=self._cam_src)
        self._worker.start()
        # Notify user of any fallback or initialisation warnings
        if self._worker.error_msg:
            QMessageBox.warning(self, "Camera Warning", self._worker.error_msg)
        self._status_cb("Tracker Setup: tracking active")

        # Initialise parameter sliders from detector values
        det = self._worker._detector
        self.sld_threshold.setValue(det.threshold)
        self.lbl_threshold_val.setText(str(det.threshold))
        self.sld_min_area.setValue(det.min_contour_area)
        self.lbl_min_area_val.setText(str(det.min_contour_area))
        self.sld_max_area.setValue(det.large_contour_area)
        self.lbl_max_area_val.setText(str(det.large_contour_area))

        # Populate crop UI from worker settings
        crop_enabled = self._worker._crop_enabled
        (x1, y1), (x2, y2) = self._worker._crop_rect
        self.chk_crop_enable.setChecked(crop_enabled)
        self.spin_x1.setValue(x1)
        self.spin_y1.setValue(y1)
        self.spin_x2.setValue(x2)
        self.spin_y2.setValue(y2)

        # Init smoothing slider from persisted profile if available
        from objects import SMOOTH_ALPHA
        try:
            prof, _ = _load_json(CALIB_PROFILE_FILE, {})
            last = prof.get("last", {})
            alpha_pct = int(last.get("smooth", SMOOTH_ALPHA * 100))
        except Exception:
            alpha_pct = int(SMOOTH_ALPHA * 100)
        self.sld_smooth.setValue(alpha_pct)
        self.lbl_smooth_val.setText(str(alpha_pct))
        # Apply smoothing immediately based on persisted profile
        from objects import set_smoothing_alpha
        set_smoothing_alpha(alpha_pct / 100.0)

    def stop_tracking(self):
        if self._worker:
            self._worker.stop()
            self._worker = None
        self.btn_pointcloud.setEnabled(False)

    def _refresh_frames(self):
        # ---- Detect worker thread failures or camera errors ---- #
        if self._worker and not self._worker.is_alive():
            # If the worker thread terminated unexpectedly, surface the error to the user
            if self._worker.error_msg:
                msg = self._worker.error_msg
                # Reset to avoid duplicate dialogs
                self._worker.error_msg = None
                QMessageBox.critical(self, "Camera Error", f"Tracking stopped: {msg}")
            # Clean up and reset UI state
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

        # ---- Status refresh ---- #
        self._fps_frame_count += 1
        import time
        now = time.perf_counter()
        if now - self._fps_last_ts >= 1.0:  # update each second
            fps_val = self._fps_frame_count / (now - self._fps_last_ts)
            self.lbl_fps.setText(f"FPS: {fps_val:.1f}")
            self._fps_last_ts = now
            self._fps_frame_count = 0

        # Camera status
        if isinstance(self._worker._camera, RealsenseStream):
            cam_name = "RealSense"
            self.btn_pointcloud.setEnabled(True)
        elif isinstance(self._worker._camera, VideoFileStream):
            cam_name = "VideoFile"
        else:
            cam_name = "Webcam"
        self.lbl_rs_detected.setText(f"Intel RealSense Detected: {'YES' if cam_name=='RealSense' else 'NO'}")

        # Show RealSense controls only when appropriate
        self.rs_group.setVisible(cam_name == "RealSense")
        self.depth_proc_group.setVisible(cam_name == "RealSense")

        if cam_name == "RealSense":
            try:
                # Update UI with current sensor values every second (~30 frames)
                if self._fps_frame_count == 0:
                    emitter_val = self._worker._camera.get_option(rs.option.emitter_enabled)
                    laser_val = int(self._worker._camera.get_option(rs.option.laser_power) or 0)
                    self.chk_emitter_on.blockSignals(True)
                    self.chk_emitter_on.setChecked(bool(emitter_val))
                    self.chk_emitter_on.blockSignals(False)
                    self.sld_laser_power.blockSignals(True)
                    self.sld_laser_power.setValue(laser_val)
                    self.sld_laser_power.blockSignals(False)
                    self.lbl_laser_val.setText(str(laser_val))

                    # Populate presets lazily (once) and sync selection
                    if self.cmb_preset.count() == 0:
                        presets = self._worker._camera.list_visual_presets()
                        for val, name in presets:
                            self.cmb_preset.addItem(name, val)

                    cur_preset = self._worker._camera.get_visual_preset()
                    if cur_preset is not None:
                        idx = self.cmb_preset.findData(cur_preset)
                        if idx != -1 and idx != self.cmb_preset.currentIndex():
                            self.cmb_preset.blockSignals(True)
                            self.cmb_preset.setCurrentIndex(idx)
                            self.cmb_preset.blockSignals(False)

                    # Exposure / gain sync
                    exp_val = int(self._worker._camera.get_option(rs.option.exposure) or 0)
                    gain_val = int(self._worker._camera.get_option(rs.option.gain) or 0)
                    ae_enabled = bool(self._worker._camera.get_option(rs.option.enable_auto_exposure) or 0)

                    # Update controls without feedback loop
                    self.chk_auto_exposure.blockSignals(True)
                    self.chk_auto_exposure.setChecked(ae_enabled)
                    self.chk_auto_exposure.blockSignals(False)

                    self.sld_exposure.blockSignals(True)
                    self.sld_exposure.setValue(exp_val)
                    self.sld_exposure.blockSignals(False)
                    self.lbl_exp_val.setText(str(exp_val))

                    self.sld_gain.blockSignals(True)
                    self.sld_gain.setValue(gain_val)
                    self.sld_gain.blockSignals(False)
                    self.lbl_gain_val.setText(str(gain_val))
                    
                    # ---------------- Sync Depth Processing UI ---------------- #
                    # Get current filter settings
                    filters = self._worker._camera.get_filter_status()
                    
                    # Update main toggle
                    self.chk_postproc_master.blockSignals(True)
                    self.chk_postproc_master.setChecked(filters["master_enabled"])
                    self.chk_postproc_master.blockSignals(False)
                    
                    # Update decimation filter UI
                    self.chk_decimate.blockSignals(True)
                    self.chk_decimate.setChecked(filters["decimation"]["enabled"])
                    self.chk_decimate.blockSignals(False)
                    
                    mag_idx = self.cmb_decimate_mag.findData(filters["decimation"]["magnitude"])
                    if mag_idx != -1:
                        self.cmb_decimate_mag.blockSignals(True)
                        self.cmb_decimate_mag.setCurrentIndex(mag_idx)
                        self.cmb_decimate_mag.blockSignals(False)
                    
                    # Update spatial filter UI
                    self.chk_spatial.blockSignals(True)
                    self.chk_spatial.setChecked(filters["spatial"]["enabled"])
                    self.chk_spatial.blockSignals(False)
                    
                    spatial_alpha = int(filters["spatial"]["smooth_alpha"] * 100)
                    self.sld_spatial_alpha.blockSignals(True)
                    self.sld_spatial_alpha.setValue(spatial_alpha)
                    self.sld_spatial_alpha.blockSignals(False)
                    self.lbl_spatial_alpha.setText(f"{filters['spatial']['smooth_alpha']:.2f}")
                    
                    spatial_delta = int(filters["spatial"]["smooth_delta"])
                    self.sld_spatial_delta.blockSignals(True)
                    self.sld_spatial_delta.setValue(spatial_delta)
                    self.sld_spatial_delta.blockSignals(False)
                    self.lbl_spatial_delta.setText(str(spatial_delta))
                    
                    # Update temporal filter UI
                    self.chk_temporal.blockSignals(True)
                    self.chk_temporal.setChecked(filters["temporal"]["enabled"])
                    self.chk_temporal.blockSignals(False)
                    
                    temporal_alpha = int(filters["temporal"]["smooth_alpha"] * 100)
                    self.sld_temporal_alpha.blockSignals(True)
                    self.sld_temporal_alpha.setValue(temporal_alpha)
                    self.sld_temporal_alpha.blockSignals(False)
                    self.lbl_temporal_alpha.setText(f"{filters['temporal']['smooth_alpha']:.2f}")
                    
                    temporal_delta = int(filters["temporal"]["smooth_delta"])
                    self.sld_temporal_delta.blockSignals(True)
                    self.sld_temporal_delta.setValue(temporal_delta)
                    self.sld_temporal_delta.blockSignals(False)
                    self.lbl_temporal_delta.setText(str(temporal_delta))
                    
                    # Update hole filling UI
                    self.chk_hole.blockSignals(True)
                    self.chk_hole.setChecked(filters["hole_filling"]["enabled"])
                    self.chk_hole.blockSignals(False)
                    
                    # Enable/disable controls based on main toggle
                    enabled = filters["master_enabled"]
                    self.chk_decimate.setEnabled(enabled)
                    self.chk_spatial.setEnabled(enabled)
                    self.chk_temporal.setEnabled(enabled)
                    self.chk_hole.setEnabled(enabled)
                    self.cmb_decimate_mag.setEnabled(enabled and filters["decimation"]["enabled"])
                    self.cmb_hole_mode.setEnabled(enabled and filters["hole_filling"]["enabled"])
                    self.sld_spatial_alpha.setEnabled(enabled and filters["spatial"]["enabled"])
                    self.sld_spatial_delta.setEnabled(enabled and filters["spatial"]["enabled"])
                    self.sld_temporal_alpha.setEnabled(enabled and filters["temporal"]["enabled"])
                    self.sld_temporal_delta.setEnabled(enabled and filters["temporal"]["enabled"])
                    
            except Exception:
                pass

        # Populate detected object table
        current_beys = self._worker._registry.bey_list[-1]
        self.tbl_objects.setRowCount(len(current_beys))
        from PySide6.QtWidgets import QTableWidgetItem
        for r, bey in enumerate(current_beys):
            id_item = QTableWidgetItem(str(bey.getId()))
            pos_item = QTableWidgetItem(str(bey.getPos()))
            vel_item = QTableWidgetItem("{:.1f},{:.1f}".format(*bey.getVel()))
            status_item = QTableWidgetItem("Active")
            for c, item in enumerate([id_item, pos_item, vel_item, status_item]):
                self.tbl_objects.setItem(r, c, item)

        # Highlight out-of-range contours on debug feed for immediate feedback
        try:
            det = self._worker._detector
            thresh_src = self._worker.latest_thresh
            if thresh_src is not None:
                thresh_gray = thresh_src[..., 0] if len(thresh_src.shape) == 3 else thresh_src
                _contours, _ = cv2.findContours(thresh_gray.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_KCOS)
                dbg_overlay = frame.copy()
                for cnt in _contours:
                    area = cv2.contourArea(cnt)
                    if area < det.min_contour_area or area > det.large_contour_area:
                        x, y, w, h = cv2.boundingRect(cnt)
                        cv2.rectangle(dbg_overlay, (x, y), (x + w, y + h), (255, 0, 0), 1)
                # overwrite live debug label with overlay image for clarity
                dbg_rgb2 = cv2.cvtColor(dbg_overlay, cv2.COLOR_BGR2RGB)
                qt_dbg2 = QImage(dbg_rgb2.data, w, h, ch * w, QImage.Format_RGB888)
                self.debug_feed_lbl.setPixmap(QPixmap.fromImage(qt_dbg2.scaled(self.debug_feed_lbl.size(), Qt.KeepAspectRatio)))
        except Exception:
            pass

    def closeEvent(self, event):
        self.stop_tracking()
        super().closeEvent(event)

    def _open_calibration_wizard(self):
        wizard = CalibrationWizard(self._get_worker)
        wizard.exec()
        main_win = self.window()
        if hasattr(main_win, "apply_saved_layout"):
            main_win.apply_saved_layout()

    def _get_worker(self):
        return self._worker

    # ----------------------- Qt visibility hooks ----------------------- #
    def showEvent(self, event):
        """Start the tracking worker when the page becomes visible."""
        super().showEvent(event)
        self._start_tracking()

    def hideEvent(self, event):
        """Stop the tracking worker when the page is hidden to free the camera."""
        self.stop_tracking()
        super().hideEvent(event)

    # ---------------- Parameter Handlers ---------------- #

    def _update_detector_param(self, attr: str, value: int):
        if self._worker and self._worker.is_alive():
            setattr(self._worker._detector, attr, value)

    def _on_threshold_changed(self, val: int):
        self.lbl_threshold_val.setText(str(val))
        self._update_detector_param("threshold", val)

    def _on_min_area_changed(self, val: int):
        self.lbl_min_area_val.setText(str(val))
        self._update_detector_param("min_contour_area", val)

    def _on_max_area_changed(self, val: int):
        self.lbl_max_area_val.setText(str(val))
        self._update_detector_param("large_contour_area", val)

    def _on_smooth_changed(self, val: int):
        self.lbl_smooth_val.setText(str(val))
        try:
            from objects import set_smoothing_alpha
            set_smoothing_alpha(val / 100.0)

            # --- Persist smoothing factor to calibration profile ('last') --- #
            try:
                from .calibration_wizard import CALIB_PROFILE_FILE, _load_json, _save_json  # type: ignore
                prof, _ = _load_json(CALIB_PROFILE_FILE, {}) if callable(_load_json) else ({}, None)
                last = prof.get("last", {})
                last["smooth"] = int(val)
                prof["last"] = last
                _save_json(CALIB_PROFILE_FILE, prof)
            except Exception:
                pass
        except Exception:
            pass

    def _on_invert_toggled(self, checked: bool):
        if self._worker and self._worker.is_alive():
            self._worker.set_invert_ir(checked)

    # ---------------- RealSense control handlers ---------------- #
    def _on_emitter_toggled(self, checked: bool):
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_option(rs.option.emitter_enabled, 1.0 if checked else 0.0)

    def _on_laser_power_changed(self, val: int):
        self.lbl_laser_val.setText(str(val))
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_option(rs.option.laser_power, float(val))

    def _on_preset_changed(self, idx: int):
        if idx < 0:
            return
        val = self.cmb_preset.itemData(idx)
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_visual_preset(int(val))

    def _on_ae_toggled(self, checked: bool):
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_option(rs.option.enable_auto_exposure, 1.0 if checked else 0.0)

    def _on_exposure_changed(self, val: int):
        self.lbl_exp_val.setText(str(val))
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_option(rs.option.exposure, float(val))

    def _on_gain_changed(self, val: int):
        self.lbl_gain_val.setText(str(val))
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_option(rs.option.gain, float(val))

    # ----------------------- Persist RealSense settings ----------------------- #
    def _on_save_rs_settings(self):
        if self._worker and self._worker.is_alive():
            ok = self._worker.save_current_rs_settings()
            QMessageBox.information(self, "Save Settings", "Settings saved." if ok else "Unable to save settings (camera not available).")

    # ----------------------- Persist Detection params ----------------------- #
    def _on_save_detection_settings(self):
        if not (self._worker and self._worker.is_alive()):
            QMessageBox.warning(self, "Save Error", "Tracker must be running to read current detector settings.")
            return
        det = self._worker._detector
        from objects import SMOOTH_ALPHA
        data = {
            "threshold": det.threshold,
            "min_area": det.min_contour_area,
            "max_area": det.large_contour_area,
            "smooth": int(SMOOTH_ALPHA * 100),
        }
        # load existing, merge under 'last'
        profiles, _ = _load_json(CALIB_PROFILE_FILE, {})
        profiles["last"] = data
        _save_json(CALIB_PROFILE_FILE, profiles)
        QMessageBox.information(self, "Detection Settings", "Settings saved and will load on next start.")

    def _on_reset_detection(self):
        """Restore default threshold/min/max values and update detector + sliders."""
        defaults = {"threshold": 15, "min_contour_area": 100, "large_contour_area": 2000}
        self.sld_threshold.setValue(defaults["threshold"])
        self.sld_min_area.setValue(defaults["min_contour_area"])
        self.sld_max_area.setValue(defaults["large_contour_area"])
        # Detector attributes will update via slider signals automatically
        QMessageBox.information(self, "Detection", "Detection parameters reset to defaults.")

    def _on_apply_crop(self):
        if not (self._worker and self._worker.is_alive()):
            QMessageBox.warning(self, "Crop", "Tracker must be running to apply crop.")
            return
        x1 = self.spin_x1.value()
        y1 = self.spin_y1.value()
        x2 = self.spin_x2.value()
        y2 = self.spin_y2.value()
        if x2 <= x1 + 10 or y2 <= y1 + 10:
            QMessageBox.warning(self, "Crop", "Invalid crop rectangle dimensions.")
            return
        enabled = self.chk_crop_enable.isChecked()
        self._worker.set_crop(x1, y1, x2, y2, enabled)
        QMessageBox.information(self, "Crop", "Crop updated and saved.")

    def _on_adapt_toggled(self, checked: bool):
        if self._worker and self._worker.is_alive():
            self._worker.set_adaptive_threshold(checked)

    # ---------------- Auto-threshold helper (Tracker Setup) ---------------- #
    def _on_auto_threshold(self):
        """Compute recommended threshold based on current IR frame statistics."""
        if not (self._worker and self._worker.is_alive()):
            QMessageBox.warning(self, "Auto Threshold", "Tracker must be running to analyze frame.")
            return
        try:
            gray = self._worker._get_cropped_frame().astype(np.float32)
            mu, sigma = gray.mean(), gray.std() + 1e-6
            z = (gray - mu) / sigma
            import numpy as np
            target = float(np.percentile(z, 99.5))
            suggested = int(max(5, min(40, round(target))))
            ret = QMessageBox.question(
                self,
                "Auto Threshold",
                f"Suggested threshold: {suggested}. Apply?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ret == QMessageBox.Yes:
                self._worker._detector.threshold = suggested
                self._status_cb(f"Threshold set to {suggested}")
        except Exception as exc:
            QMessageBox.warning(self, "Auto Threshold", f"Unable to compute suggestion: {exc}")

    # ---------------- Point Cloud ---------------- #
    def _on_pointcloud_clicked(self):
        if self._pc_window and self._pc_window.isVisible():
            self._pc_window.raise_()
            return

        if not (self._worker and self._worker.is_alive() and isinstance(self._worker._camera, RealsenseStream)):
            QMessageBox.information(self, "Point Cloud", "RealSense camera not active.")
            return

        from .pointcloud_widget import PointCloudWidget

        cam: RealsenseStream = self._worker._camera  # type: ignore

        def _provider():
            return cam.get_pointcloud_vertices(max_points=30000)

        self._pc_window = PointCloudWidget(_provider)
        self._pc_window.setWindowTitle("RealSense Point Cloud – Debug")
        self._pc_window.resize(640, 480)
        
        # Create measurement controls
        from PySide6.QtWidgets import QToolBar, QVBoxLayout, QPushButton, QLabel, QApplication, QMainWindow
        class PCWindow(QMainWindow):
            def __init__(self, pc_widget, camera):
                super().__init__()
                self.setWindowTitle("RealSense Point Cloud – Measurement Tools")
                
                # Store camera reference
                self._camera = camera
                
                # Central widget is our point cloud view
                self.setCentralWidget(pc_widget)
                self._pc_widget = pc_widget
                
                # Create toolbar with measurement controls
                toolbar = QToolBar("Measurement Controls")
                self.addToolBar(toolbar)
                
                # Measure button
                self.btn_measure = QPushButton("Enable Measurement")
                self.btn_measure.setCheckable(True)
                self.btn_measure.toggled.connect(self._toggle_measurement)
                toolbar.addWidget(self.btn_measure)
                
                # Reset button 
                self.btn_reset = QPushButton("Reset")
                self.btn_reset.clicked.connect(self._reset_measurement)
                toolbar.addWidget(self.btn_reset)
                
                # Connect to the measurement signal
                pc_widget.measurement_updated.connect(self._on_measurement_updated)
                
                # Add arena analysis section
                self.btn_analyze = QPushButton("Analyze Arena")
                self.btn_analyze.clicked.connect(self._analyze_arena)
                toolbar.addWidget(self.btn_analyze)
                
                # Status bar for arena information
                self.statusBar().showMessage("Ready")
                
            def _toggle_measurement(self, enabled):
                """Enable/disable measurement mode."""
                self._pc_widget.enable_measurement(enabled)
                self.btn_measure.setText("Disable Measurement" if enabled else "Enable Measurement")
                
            def _reset_measurement(self):
                """Reset current measurement points."""
                self._pc_widget.reset_measurement()
                
            def _on_measurement_updated(self, distance_m, description):
                """Handle new measurement."""
                self.statusBar().showMessage(description)
                
            def _analyze_arena(self):
                """Analyze arena dimensions and flatness."""
                if not self._camera:
                    return
                    
                # Get arena dimensions
                width, length, height = self._camera.get_arena_dimensions()
                
                if width <= 0 or length <= 0:
                    QMessageBox.information(self, "Arena Analysis", 
                                           "Unable to detect arena dimensions. Make sure the arena is visible.")
                    return
                    
                # Get arena flatness
                flatness_score, flatness_desc = self._camera.analyze_arena_floor()
                
                # Format message
                msg = (
                    f"Arena Dimensions:\n"
                    f"Width: {width*100:.1f} cm\n"
                    f"Length: {length*100:.1f} cm\n"
                    f"Height (depth): {height*100:.1f} cm\n\n"
                    f"Flatness: {flatness_score:.2f}\n"
                    f"{flatness_desc}"
                )
                
                QMessageBox.information(self, "Arena Analysis Results", msg)
                
        # Create new window with the point cloud widget and measurement controls
        window = PCWindow(self._pc_window, cam)
        window.resize(800, 600)
        window.show()
        
        # Store reference to prevent garbage collection
        self._pc_window = window

    # ---------------- Depth Processing Controls Handlers ---------------- #
    def _on_postproc_master_toggled(self, checked: bool):
        """Enable/disable all depth post-processing."""
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_postprocessing_enabled(checked)
            # Update UI state to reflect enabled/disabled
            self.chk_decimate.setEnabled(checked)
            self.chk_spatial.setEnabled(checked)
            self.chk_temporal.setEnabled(checked)
            self.chk_hole.setEnabled(checked)
            self.cmb_decimate_mag.setEnabled(checked)
            self.cmb_hole_mode.setEnabled(checked)
            self.sld_spatial_alpha.setEnabled(checked)
            self.sld_spatial_delta.setEnabled(checked)
            self.sld_temporal_alpha.setEnabled(checked)
            self.sld_temporal_delta.setEnabled(checked)
    
    def _on_decimate_toggled(self, checked: bool):
        """Toggle decimation filter."""
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_decimation_enabled(checked)
            self.cmb_decimate_mag.setEnabled(checked)
    
    def _on_decimate_mag_changed(self, idx: int):
        """Set decimation factor."""
        if idx >= 0:
            value = self.cmb_decimate_mag.itemData(idx)
            if self._worker and isinstance(self._worker._camera, RealsenseStream):
                self._worker._camera.set_decimation_magnitude(value)
    
    def _on_spatial_toggled(self, checked: bool):
        """Toggle spatial filter."""
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_spatial_filter_enabled(checked)
            self.sld_spatial_alpha.setEnabled(checked)
            self.sld_spatial_delta.setEnabled(checked)
    
    def _on_spatial_alpha_changed(self, val: int):
        """Update spatial filter alpha parameter."""
        alpha = val / 100.0  # Convert 0-100 range to 0.0-1.0
        self.lbl_spatial_alpha.setText(f"{alpha:.2f}")
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            delta = float(self.sld_spatial_delta.value())
            self._worker._camera.set_spatial_filter_params(alpha, delta)
    
    def _on_spatial_delta_changed(self, val: int):
        """Update spatial filter delta parameter."""
        self.lbl_spatial_delta.setText(str(val))
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            alpha = float(self.sld_spatial_alpha.value()) / 100.0
            self._worker._camera.set_spatial_filter_params(alpha, float(val))
    
    def _on_temporal_toggled(self, checked: bool):
        """Toggle temporal filter."""
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_temporal_filter_enabled(checked)
            self.sld_temporal_alpha.setEnabled(checked)
            self.sld_temporal_delta.setEnabled(checked)
    
    def _on_temporal_alpha_changed(self, val: int):
        """Update temporal filter alpha parameter."""
        alpha = val / 100.0  # Convert 0-100 range to 0.0-1.0
        self.lbl_temporal_alpha.setText(f"{alpha:.2f}")
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            delta = float(self.sld_temporal_delta.value())
            self._worker._camera.set_temporal_filter_params(alpha, delta)
    
    def _on_temporal_delta_changed(self, val: int):
        """Update temporal filter delta parameter."""
        self.lbl_temporal_delta.setText(str(val))
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            alpha = float(self.sld_temporal_alpha.value()) / 100.0
            self._worker._camera.set_temporal_filter_params(alpha, float(val))
    
    def _on_hole_toggled(self, checked: bool):
        """Toggle hole filling filter."""
        if self._worker and isinstance(self._worker._camera, RealsenseStream):
            self._worker._camera.set_hole_filling_enabled(checked)
            self.cmb_hole_mode.setEnabled(checked)
    
    def _on_hole_mode_changed(self, idx: int):
        """Change hole filling mode."""
        if idx >= 0:
            value = self.cmb_hole_mode.itemData(idx)
            if self._worker and isinstance(self._worker._camera, RealsenseStream):
                self._worker._camera.set_hole_filling_mode(value)


# --------------------------- Projection Setup Page --------------------------- #


class ProjectionSetupPage(QWidget):
    """Projection configuration screen for Unity client display."""

    def __init__(self, status_cb):
        super().__init__()
        self._status_cb = status_cb
        self._last_worker = None  # Store reference to last active worker for TCP communication

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
        preview_group = QGroupBox("Projection Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_widget = QWidget()
        self.preview_widget.setMinimumSize(320, 240)
        self.preview_widget.setStyleSheet("background-color:#111;border:1px solid #444;")
        preview_layout.addWidget(self.preview_widget)
        
        main_layout.addWidget(preview_group)
        
        # Right side - controls
        controls_group = QGroupBox("Projection Settings")
        controls_layout = QGridLayout(controls_group)
        
        controls_layout.addWidget(QLabel("Width (pixels):"), 0, 0)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 7680)  # Support for very high resolutions
        self.width_spin.setValue(1920)        # Default common resolution
        self.width_spin.setSingleStep(10)
        self.width_spin.valueChanged.connect(self._update_preview)
        controls_layout.addWidget(self.width_spin, 0, 1)
        
        controls_layout.addWidget(QLabel("Height (pixels):"), 1, 0)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 4320)  # Support for very high resolutions
        self.height_spin.setValue(1080)       # Default common resolution
        self.height_spin.setSingleStep(10)
        self.height_spin.valueChanged.connect(self._update_preview)
        controls_layout.addWidget(self.height_spin, 1, 1)
        
        # Presets section
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
        
        # Action buttons
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
        
        # Unity connection section
        unity_group = QGroupBox("Unity Connection")
        unity_layout = QVBoxLayout(unity_group)
        
        self.connection_info = QLabel(
            "The Unity client must be running and connected to this tracker.\n"
            "Changes will apply immediately when you click 'Apply Projection Settings'.\n"
            "Connection status is shown at the top of this page."
        )
        self.connection_info.setWordWrap(True)
        unity_layout.addWidget(self.connection_info)
        
        # Unity restart button for when connection is lost
        self.restart_unity_btn = QPushButton("Restart Unity Client")
        self.restart_unity_btn.setToolTip("Attempt to launch/restart the Unity client application")
        self.restart_unity_btn.clicked.connect(self._restart_unity)
        unity_layout.addWidget(self.restart_unity_btn)
        
        controls_layout.addWidget(unity_group, 5, 0, 1, 2)
        
        main_layout.addWidget(controls_group)
        
        # Timer to check connection status periodically
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_connection_status)
        self._status_timer.start(1000)  # Check once per second
        
        # Load saved profile on init
        self._load_profile()
    
    def _apply_preset(self, width: int, height: int):
        """Set dimensions to a predefined preset."""
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        self._update_preview()
    
    def _update_preview(self):
        """Redraw the preview with current dimensions."""
        # Trigger a paint event
        self.preview_widget.update()
    
    def _auto_detect_resolution(self):
        """Attempt to detect the resolution of connected displays."""
        try:
            # Try to get desktop resolution from Qt
            desktop = QApplication.instance().desktop()
            screen = desktop.screenGeometry(0)  # Primary monitor
            width, height = screen.width(), screen.height()
            
            # Offer to apply detected resolution
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, 
                "Detected Resolution",
                f"Detected primary display resolution: {width}×{height}\n\n"
                f"Apply this resolution?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self.width_spin.setValue(width)
                self.height_spin.setValue(height)
                self._update_preview()
                self._status_cb(f"Applied detected resolution: {width}×{height}")
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, 
                "Auto-Detection Failed",
                f"Could not auto-detect display resolution: {e}"
            )
    
    def _apply_projection(self):
        """Send current projection settings to Unity client via TCP."""
        width = self.width_spin.value()
        height = self.height_spin.value()
        
        # Get an active worker to send the message
        worker = self._find_worker()
        if not worker:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Connection Error",
                "No active tracking worker found. Start tracking in Free Play or Tracker Setup first."
            )
            return
        
        # Send the command to Unity
        worker.send_projection_update(width, height)
        self._status_cb(f"Sent projection update: {width}×{height}")
        
        # Save to default profile if requested
        if self.save_default_cb.isChecked():
            self._save_profile(width, height)
            self._status_cb("Saved as default projection profile")

    def _save_profile(self, width: int, height: int):
        """Save the current projection settings as the default profile."""
        # Load existing profiles, merge under "default"
        layouts, _ = _load_json(LAYOUT_FILE, {})
        layouts["default"] = {
            "width": width,
            "height": height
        }
        _save_json(LAYOUT_FILE, layouts)
    
    def _load_profile(self):
        """Load saved profile and apply settings."""
        try:
            layouts, _ = _load_json(LAYOUT_FILE, {})
            default = layouts.get("default", {})
            if default:
                width = int(default.get("width", 1920))
                height = int(default.get("height", 1080))
                self.width_spin.blockSignals(True)
                self.height_spin.blockSignals(True)
                self.width_spin.setValue(width)
                self.height_spin.setValue(height)
                self.width_spin.blockSignals(False)
                self.height_spin.blockSignals(False)
                self._update_preview()
        except Exception:
            # Fallback to defaults if loading fails
            pass
    
    def _find_worker(self):
        """Find an active tracking worker to use for TCP communication."""
        # Get main window and try to find a worker in the open pages
        main_win = self.window()
        
        # Check if MainWindow has access to worker
        if hasattr(main_win, "_tracker_setup_page") and main_win._tracker_setup_page._worker:
            worker = main_win._tracker_setup_page._worker
            if worker.is_alive():
                self._last_worker = worker
                return worker
                
        if hasattr(main_win, "_free_play_page") and main_win._free_play_page._worker:
            worker = main_win._free_play_page._worker  
            if worker.is_alive():
                self._last_worker = worker
                return worker
        
        # Return last known good worker as fallback
        return self._last_worker
    
    def _update_connection_status(self):
        """Check if TCP connection to Unity is active and update status label."""
        worker = self._find_worker()
        if worker and hasattr(worker, "_tcp_client_socket") and worker._tcp_client_socket:
            self.connection_status.setText("Status: Connected to Unity")
            self.connection_status.setStyleSheet("font-size:14px;color:#88FF88;")
            self.restart_unity_btn.setEnabled(False)
        else:
            self.connection_status.setText("Status: Not Connected")
            self.connection_status.setStyleSheet("font-size:14px;color:#FF8888;")
            self.restart_unity_btn.setEnabled(True)
    
    def _restart_unity(self):
        """Attempt to launch or restart the Unity client application."""
        import subprocess
        import os
        from pathlib import Path
        
        try:
            # Look for Unity client in standard locations (modify paths as needed)
            unity_paths = [
                Path.cwd() / "beysion-unity" / "BeysionClient.exe",
                Path.cwd().parent / "beysion-unity" / "BeysionClient.exe",
                Path("C:/Program Files/Beysion/BeysionClient.exe"),
                Path("C:/Beysion/BeysionClient.exe"),
            ]
            
            for path in unity_paths:
                if path.exists():
                    self._status_cb(f"Launching Unity client: {path}")
                    subprocess.Popen([str(path)])
                    return
                    
            # If not found, show message with manual instructions
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "Unity Client Not Found",
                "The Unity client application could not be found in standard locations.\n\n"
                "Please launch the Unity client manually and ensure it's configured to connect "
                f"to this tracker at {HOST}:{TCP_PORT}."
            )
            
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Launch Failed",
                f"Failed to launch Unity client: {e}"
            )
    
    # ----------------------- Paint Event for Preview ----------------------- #
    def paintEvent(self, event):
        """Update the preview widget with current dimensions."""
        super().paintEvent(event)
        # Also ensure preview widget is updated
        self.preview_widget.update()
    
    # ----------------------- Custom preview painter ----------------------- #
    def eventFilter(self, obj, event):
        """Handle paint events for the preview widget."""
        if obj is self.preview_widget and event.type() == QEvent.Paint:
            self._draw_preview(obj)
            return True
        return super().eventFilter(obj, event)
    
    def _draw_preview(self, widget):
        """Draw the projection preview with proper aspect ratio."""
        painter = QPainter(widget)
        
        # Clear background
        painter.fillRect(widget.rect(), QColor("#111"))
        
        # Get current settings
        width = self.width_spin.value()
        height = self.height_spin.value()
        
        # Calculate scaled rectangle to fit in the preview widget
        aspect = width / height if height else 1.0
        preview_w = widget.width()
        preview_h = widget.height()
        
        if preview_w / aspect <= preview_h:
            # Width-constrained
            scaled_w = int(preview_w * 0.9)
            scaled_h = int(scaled_w / aspect)
        else:
            # Height-constrained
            scaled_h = int(preview_h * 0.9)
            scaled_w = int(scaled_h * aspect)
        
        x = (preview_w - scaled_w) // 2
        y = (preview_h - scaled_h) // 2
        
        # Draw the outline with dimming effect
        painter.setPen(QPen(QColor("#4CFF4C"), 2))
        painter.drawRect(x, y, scaled_w, scaled_h)
        
        # Draw resolution text
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            QRect(x, y + scaled_h // 2 - 20, scaled_w, 40),
            Qt.AlignCenter,
            f"{width} × {height}"
        )
        
        # Draw projector icon
        proj_rect = QRect(x + scaled_w // 2 - 15, y - 30, 30, 20)
        painter.fillRect(proj_rect, QColor("#555"))
        # Draw projector "lens"
        painter.fillRect(proj_rect.x() + 10, proj_rect.y() + 15, 10, 5, QColor("#AAA"))
        
        # Draw "light beam" lines from projector to screen
        painter.setPen(QPen(QColor("#333"), 1))
        painter.drawLine(proj_rect.x() + 5, proj_rect.y() + 20, x, y + scaled_h)
        painter.drawLine(proj_rect.x() + 25, proj_rect.y() + 20, x + scaled_w, y + scaled_h)
    
    def showEvent(self, event):
        """Set up event filter when widget becomes visible."""
        super().showEvent(event)
        # Install event filter for custom preview painting
        self.preview_widget.installEventFilter(self)
        # Initial update
        self._update_connection_status()
    
    def hideEvent(self, event):
        """Clean up event filter when widget is hidden."""
        super().hideEvent(event)
        self.preview_widget.removeEventFilter(self)

# --------------------------- Toast Manager --------------------------- #


class _ToastManager(QWidget):
    """Simple overlay widget to display transient toast notifications."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._label = QLabel(parent=self)
        self._label.setStyleSheet(
            "background:rgba(50,50,50,200); color:white; padding:8px 14px; border-radius:6px;"
        )
        self._label.setAlignment(Qt.AlignCenter)
        self._label.hide()

        self._effect = QGraphicsOpacityEffect(self._label)
        self._label.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(600)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.finished.connect(self._label.hide)

    def show(self, text: str, duration_ms: int = 3000):
        self._label.setText(text)
        self._label.adjustSize()
        # Position top-right with margin
        margin = 20
        parent_rect = self.parent().rect()
        lbl_w, lbl_h = self._label.width(), self._label.height()
        self._label.move(parent_rect.width() - lbl_w - margin, margin)
        self._effect.setOpacity(1.0)
        self._label.show()

        # Restart animation timer
        self._anim.stop()
        QTimer.singleShot(duration_ms, self._anim.start)


# --------------------------- Main Window --------------------------- #

class MainWindow(QMainWindow):
    """Main application window with stacked pages for different screens."""

    def __init__(self, *, dev_mode: bool = False, cam_src: int = 0):
        super().__init__()
        
        # Basic window settings
        self.setWindowTitle("Beysion Tracker - V2")
        self.setMinimumSize(1280, 720)
        
        # Try layout file for ideal geometry
        try:
            cfg = _load_json(LAYOUT_FILE, {}).get("default", {})
            if cfg:
                w, h = cfg.get("width"), cfg.get("height")
                if w and h:
                    self.resize(int(w * 0.8), int(h * 0.8))  # 80% of projection size
        except Exception:
            pass
            
        # Fallback
        self.resize(1280, 720)
        
        # Central widget and stacked layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # Create stacked widget for navigation
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)
        
        # Create status bar for notifications
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        
        # Create toast notification manager
        self._toast = _ToastManager(self)
        
        # Create the pages
        self._create_pages(dev_mode, cam_src)
        
        # Set up navigation connections
        self._wire_navigation()
        
        # Apply theme from preferences
        self._apply_saved_theme()
    
    def _status_message(self, msg: str):
        """Display a status message in the status bar."""
        self._status_bar.showMessage(msg, 4000)
        # Also show a toast notification for important operations
        self._toast.show(msg)
    
    def _create_pages(self, dev_mode: bool, cam_src: int):
        """Create all pages in the application."""
        # Free play mode
        self._free_play_page = FreePlayPage(self._status_message, dev_mode=dev_mode, cam_src=cam_src)
        self._stack.addWidget(self._free_play_page)
        
        # System hub (navigation page)
        self._system_hub_page = SystemHubPage()
        self._stack.addWidget(self._system_hub_page)
        
        # Tracker setup page
        self._tracker_setup_page = TrackerSetupPage(self._status_message, dev_mode=dev_mode, cam_src=cam_src)
        self._stack.addWidget(self._tracker_setup_page)
        
        # NEW: Projection setup page
        self._projection_setup_page = ProjectionSetupPage(self._status_message)
        self._stack.addWidget(self._projection_setup_page)
        
        # Set initial page
        self._stack.setCurrentWidget(self._system_hub_page)
    
    def _wire_navigation(self):
        """Connect navigation buttons between pages."""
        # Connect System Hub navigation
        self._system_hub_page.cb_open_tracker = self._open_tracker_setup
        self._system_hub_page.cb_open_free_play = self._open_free_play
        
        # NEW: Connect projection button in System Hub
        self._system_hub_page.btn_projection.clicked.connect(self._open_projection_setup)
        
        # Connect Free Play page navigation
        self._free_play_page.set_open_tracker_setup_cb(self._open_tracker_setup)
        self._free_play_page.set_open_system_hub_cb(self._open_system_hub)
    
    def _open_free_play(self):
        """Switch to Free Play page."""
        self._stack.setCurrentWidget(self._free_play_page)
        self._status_message("Free Play mode activated")
    
    def _open_tracker_setup(self):
        """Switch to Tracker Setup page."""
        self._stack.setCurrentWidget(self._tracker_setup_page)
    
    def _open_system_hub(self):
        """Switch to System Hub page."""
        self._stack.setCurrentWidget(self._system_hub_page)
    
    # NEW: Open projection setup from System Hub
    def _open_projection_setup(self):
        """Switch to Projection Setup page."""
        self._stack.setCurrentWidget(self._projection_setup_page)
        self._status_message("Projection Setup opened")
    
    def apply_saved_layout(self):
        """Apply saved layout settings from file."""
        try:
            cfg = _load_json(LAYOUT_FILE, {}).get("default", {})
            if cfg:
                w, h = cfg.get("width"), cfg.get("height")
                if w and h:
                    # Apply unity client size to any currently active worker
                    if hasattr(self, "_free_play_page") and self._free_play_page._worker:
                        self._free_play_page._worker.send_projection_update(w, h)
                    if hasattr(self, "_tracker_setup_page") and self._tracker_setup_page._worker:
                        self._tracker_setup_page._worker.send_projection_update(w, h)
        except Exception:
            pass
    
    def _apply_saved_theme(self):
        """Apply theme settings from preferences file."""
        try:
            prefs, _ = _load_json(GUI_PREFS_FILE, {})
            theme = prefs.get("theme", "Dark")
            self.apply_theme(theme)
        except Exception:
            # Default to dark mode
            self.apply_theme("Dark")
    
    def apply_theme(self, theme_name: str = "Dark"):
        """Switch between dark & light palettes globally."""
        if theme_name == "Light":
            self.setStyleSheet("")
            pal = QApplication.instance().palette()
            pal.setColor(QPalette.Window, QColor("#f0f0f0"))
            pal.setColor(QPalette.WindowText, Qt.black)
            QApplication.instance().setPalette(pal)
        else:  # Dark
            pal = QApplication.instance().palette()
            pal.setColor(QPalette.Window, QColor("#1F2937"))
            pal.setColor(QPalette.WindowText, Qt.white)
            QApplication.instance().setPalette(pal)
            # Maintain existing per-widget dark stylesheets
        # Save choice
        _save_json(GUI_PREFS_FILE, {"theme": theme_name})
    
    def _open_calibration_wizard_global(self):
        """Launch Calibration Wizard regardless of current page.

        The wizard needs a callable returning an active TrackingWorker (or None).
        We provide a resolver that checks Free Play and Tracker Setup pages in
        that priority order.
        """
        def _worker_resolver():
            if self._free_play_page._worker and self._free_play_page._worker.is_alive():
                return self._free_play_page._worker
            if self._tracker_setup_page._worker and self._tracker_setup_page._worker.is_alive():
                return self._tracker_setup_page._worker
            return None

        wizard = CalibrationWizard(_worker_resolver)
        wizard.exec()
        # Apply layout immediately if saved
        if hasattr(self, "apply_saved_layout"):
            self.apply_saved_layout()


def launch(*, dev_mode: bool = False, cam_src: int = 0):
    app = QApplication(sys.argv)
    win = MainWindow(dev_mode=dev_mode, cam_src=cam_src)
    win.show()
    sys.exit(app.exec()) 