"""
Tracking Worker for BBAN-Tracker Event-Driven Architecture.

This module contains the core tracking logic extracted from the monolithic GUI.
It will be integrated with the TrackingService to provide the actual tracking
implementation while maintaining separation of concerns.
"""

from __future__ import annotations

import socket
import time
from pathlib import Path
from threading import Thread, Event
from typing import Optional

import cv2
import numpy as np
import pyrealsense2 as rs

from ..camera import RealsenseStream, WebcamVideoStream, VideoFileStream
from ..detector import Detector
from ..registry import Registry
from ..gui.calibration_wizard import LAYOUT_FILE, _load_json, _save_json


# Global config paths
_CONFIG_DIR = Path.home() / ".beytracker"
_CONFIG_DIR.mkdir(exist_ok=True)
RS_SETTINGS_FILE = _CONFIG_DIR / "rs_settings.json"
CROP_SETTINGS_FILE = _CONFIG_DIR / "crop_settings.json"


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
            from ..gui.calibration_wizard import CALIB_PROFILE_FILE, _load_json  # type: ignore
            from ..objects import set_smoothing_alpha  # global helper

            prof, _ = _load_json(CALIB_PROFILE_FILE, {}) if callable(_load_json) else ({}, None)
            smooth_pct = int(prof.get("last", {}).get("smooth", 20))
            set_smoothing_alpha(smooth_pct / 100.0)
        except Exception:
            # On any failure fall back to default (20 %)
            pass

        # ----------------------- Networking Setup (UDP + TCP) ----------------------- #
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

    def set_threshold(self, threshold: int):
        """Set detection threshold value."""
        if hasattr(self, '_detector') and self._detector:
            self._detector.threshold = int(threshold)

    def set_min_area(self, min_area: int):
        """Set minimum contour area for detection."""
        if hasattr(self, '_detector') and self._detector:
            self._detector.min_contour_area = int(min_area)

    def set_max_area(self, max_area: int):
        """Set maximum contour area for detection."""
        if hasattr(self, '_detector') and self._detector:
            self._detector.large_contour_area = int(max_area)

    def calibrate(self):
        """Perform calibration on the detector."""
        if hasattr(self, '_detector') and self._detector:
            self._detector.calibrate(lambda: self._get_cropped_frame())

    def stop_tracking(self):
        """Stop the tracking worker."""
        self.stop()

    # ---------------- RealSense-specific settings ---------------- #

    def set_emitter_enabled(self, enabled: bool):
        """Enable/disable IR emitter."""
        if isinstance(self._camera, RealsenseStream):
            try:
                self._camera.set_option(rs.option.emitter_enabled, 1.0 if enabled else 0.0)
            except Exception:
                pass

    def set_laser_power(self, power: int):
        """Set laser power (0-360)."""
        if isinstance(self._camera, RealsenseStream):
            try:
                self._camera.set_option(rs.option.laser_power, float(power))
            except Exception:
                pass

    def set_visual_preset(self, preset: int):
        """Set visual preset."""
        if isinstance(self._camera, RealsenseStream):
            try:
                self._camera.set_visual_preset(int(preset))
            except Exception:
                pass

    def set_exposure(self, exposure: int):
        """Set exposure value."""
        if isinstance(self._camera, RealsenseStream):
            try:
                self._camera.set_option(rs.option.exposure, float(exposure))
            except Exception:
                pass

    def set_gain(self, gain: int):
        """Set gain value."""
        if isinstance(self._camera, RealsenseStream):
            try:
                self._camera.set_option(rs.option.gain, float(gain))
            except Exception:
                pass

    def set_auto_exposure(self, enabled: bool):
        """Enable/disable auto exposure."""
        if isinstance(self._camera, RealsenseStream):
            try:
                self._camera.set_option(rs.option.enable_auto_exposure, 1.0 if enabled else 0.0)
            except Exception:
                pass

    def set_postprocessing_enabled(self, enabled: bool):
        """Enable/disable post-processing filters."""
        if isinstance(self._camera, RealsenseStream):
            try:
                self._camera.set_postprocessing_enabled(bool(enabled))
            except Exception:
                pass

    # ---------------- Accessors for monitoring loop ---------------- #

    @property
    def current_frame(self):
        """Get the current display frame."""
        return self.latest_display

    @property
    def beys(self):
        """Get current bey objects."""
        if hasattr(self, '_registry') and self._registry:
            return self._registry.beys
        return []

    @property
    def hits(self):
        """Get current hit objects."""
        if hasattr(self, '_registry') and self._registry:
            return self._registry.hits
        return []

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