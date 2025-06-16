from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Any, Dict, Tuple

from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QWidget,
    QWizard,
    QWizardPage,
    QMessageBox,
    QProgressDialog,
)

CONFIG_DIR = Path.home() / ".beytracker"
CONFIG_DIR.mkdir(exist_ok=True)
LAYOUT_FILE = CONFIG_DIR / "layouts.json"
CALIB_PROFILE_FILE = CONFIG_DIR / "calibration_profiles.json"


def _load_json(path: Path, default: Any) -> Tuple[Any, Optional[str]]:
    """
    Safely load JSON data from a file with comprehensive error handling.
    
    Args:
        path: Path to the JSON file
        default: Default value to return if loading fails
        
    Returns:
        Tuple containing:
        - The loaded data or default value
        - Error message if an error occurred, None otherwise
    """
    error_msg = None
    result = default
    
    if not path.exists():
        return default, None  # Not an error, just use default
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            result = json.load(f)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format in {path.name}: {str(e)}"
    except PermissionError:
        error_msg = f"Permission denied when reading {path.name}"
    except OSError as e:
        error_msg = f"File system error when reading {path.name}: {str(e)}"
    except Exception as e:
        error_msg = f"Unexpected error reading {path.name}: {str(e)}"
        
    return result, error_msg


def _save_json(path: Path, data: Any) -> Optional[str]:
    """
    Safely save JSON data to a file with comprehensive error handling.
    
    Args:
        path: Path where to save the JSON file
        data: Data to serialize and save
        
    Returns:
        Error message if an error occurred, None otherwise
    """
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to a temporary file first to avoid corruption
        temp_path = path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())  # Ensure data is written to disk
            
        # Replace the original file with the temporary file
        if path.exists():
            path.unlink()  # Remove existing file
        temp_path.rename(path)
        
        return None  # Success
    except json.JSONEncoder as e:
        return f"Failed to encode data for {path.name}: {str(e)}"
    except PermissionError:
        return f"Permission denied when writing to {path.name}"
    except OSError as e:
        return f"File system error when writing to {path.name}: {str(e)}"
    except Exception as e:
        return f"Unexpected error writing to {path.name}: {str(e)}"


class LayoutPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Layout Setup")
        self.setSubTitle("Resize and position the projection window; then click 'Save Profile' to continue.")

        layout = QVBoxLayout(self)
        # Placeholder thumbnail image
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(QSize(640, 360))
        self.thumbnail.setStyleSheet("background:#222; border: 1px solid #555;")
        self.thumbnail.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.thumbnail)

        # draw initial preview
        self._update_preview()

        form = QHBoxLayout()
        layout.addLayout(form)
        form.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox(maximum=4096)
        self.width_spin.setValue(1920)
        form.addWidget(self.width_spin)
        form.addWidget(QLabel("Height:"))
        self.height_spin = QSpinBox(maximum=4096)
        self.height_spin.setValue(1080)
        form.addWidget(self.height_spin)

        self.save_btn = QPushButton("Save Profile")
        self.save_btn.clicked.connect(self.save_profile)
        layout.addWidget(self.save_btn)

        # Connect spin changes to live preview
        self.width_spin.valueChanged.connect(self._update_preview)
        self.height_spin.valueChanged.connect(self._update_preview)

    def save_profile(self):
        # Load existing layouts with error handling
        layouts, load_error = _load_json(LAYOUT_FILE, {})
        if load_error:
            QMessageBox.warning(self, "Load Error", 
                                f"Error loading existing profiles: {load_error}\n"
                                "Creating a new profile file.")
            layouts = {}
            
        # Update with new values
        layouts["default"] = {
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
        }
        
        # Save with error handling
        save_error = _save_json(LAYOUT_FILE, layouts)
        if save_error:
            QMessageBox.critical(self, "Save Error", 
                                f"Failed to save layout profile: {save_error}")
            return
            
        QMessageBox.information(self, "Saved", "Layout profile saved successfully.")
        self.completeChanged.emit()

    def isComplete(self):
        # Completion when profile exists
        return LAYOUT_FILE.exists()

    # ----------------------- Preview Rendering ----------------------- #
    def _update_preview(self):
        thumb_w, thumb_h = self.thumbnail.width(), self.thumbnail.height()
        pix = QPixmap(thumb_w, thumb_h)
        pix.fill(QColor("#222"))

        # Calculate rectangle representing projection aspect ratio
        w = self.width_spin.value()
        h = self.height_spin.value()
        if w == 0 or h == 0:
            self.thumbnail.setPixmap(pix)
            return
        aspect = w / h
        # Fit inside thumbnail keeping aspect
        if aspect > thumb_w / thumb_h:
            rect_w = thumb_w * 0.9
            rect_h = rect_w / aspect
        else:
            rect_h = thumb_h * 0.9
            rect_w = rect_h * aspect
        rect_x = (thumb_w - rect_w) / 2
        rect_y = (thumb_h - rect_h) / 2

        painter = QPainter(pix)
        pen = QPen(QColor("#4caf50"))
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawRect(int(rect_x), int(rect_y), int(rect_w), int(rect_h))
        painter.end()

        self.thumbnail.setPixmap(pix)


class AutoCalibrationPage(QWizardPage):
    def __init__(self, worker_accessor):
        super().__init__()
        self.setTitle("Auto Calibration")
        self.worker_accessor = worker_accessor

        layout = QVBoxLayout(self)
        self.desc = QLabel("Press the button to run automatic calibration.")
        layout.addWidget(self.desc)

        self.calib_btn = QPushButton("Start Auto-Calibration")
        self.calib_btn.clicked.connect(self.run_calibration)
        layout.addWidget(self.calib_btn)

        self._done = False

        # Busy overlay elements (created lazily)
        self._overlay: Optional[_BusyOverlay] = None

    def run_calibration(self):
        # -- Validation: ensure we have an active tracking worker -- #
        worker = self.worker_accessor()
        if worker is None:
            QMessageBox.warning(self, "Error", "Detector unavailable (tracking not running). Start tracking first.")
            return

        # Disable button to prevent duplicate clicks
        self.calib_btn.setEnabled(False)

        # Show semi-transparent busy overlay
        if not self._overlay:
            self._overlay = _BusyOverlay(self.wizard())
        self._overlay.start("Calibrating…")

        from PySide6.QtCore import QThread, Signal
        from PySide6.QtWidgets import QProgressDialog

        class _CalibWorker(QThread):
            finished_signal = Signal()

            def __init__(self, detector, camera):
                super().__init__()
                self._detector = detector
                self._camera = camera

            def run(self):
                try:
                    self._detector.calibrate(lambda: self._camera.readNext())
                finally:
                    self.finished_signal.emit()

        # Launch worker thread
        self._worker_thread = _CalibWorker(worker._detector, worker._camera)
        self._worker_thread.finished_signal.connect(self._on_calibration_done)
        self._worker_thread.start()

    def _on_calibration_done(self):
        # Close progress dialog and mark page complete
        if self._overlay:
            self._overlay.stop()

        self._done = True
        self.completeChanged.emit()
        QMessageBox.information(self, "Calibration", "Auto-calibration completed.")

        # Re-enable calibrate button for potential re-run
        self.calib_btn.setEnabled(True)

    def isComplete(self):
        return self._done


class FineTunePage(QWizardPage):
    def __init__(self, worker_accessor):
        super().__init__()
        self.setTitle("Fine Tuning Dashboard")
        self.worker_accessor = worker_accessor

        layout = QVBoxLayout(self)
        # Threshold
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(5, 40)
        layout.addWidget(QLabel("Detection Threshold"))
        layout.addWidget(self.threshold_slider)
        self.threshold_label = QLabel()
        layout.addWidget(self.threshold_label)

        # Min contour area
        self.min_area_slider = QSlider(Qt.Horizontal)
        self.min_area_slider.setRange(50, 500)
        layout.addWidget(QLabel("Min Contour Area (px)"))
        layout.addWidget(self.min_area_slider)
        self.min_area_label = QLabel()
        layout.addWidget(self.min_area_label)

        # Max contour area
        self.max_area_slider = QSlider(Qt.Horizontal)
        self.max_area_slider.setRange(1000, 5000)
        layout.addWidget(QLabel("Max Contour Area (px)"))
        layout.addWidget(self.max_area_slider)
        self.max_area_label = QLabel()
        layout.addWidget(self.max_area_label)

        # --- Live preview of thresholded image --- #
        self.preview_label = QLabel()
        self.preview_label.setFixedHeight(240)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background:#000;border:1px solid #666;")
        layout.addWidget(self.preview_label)

        # Timer for refreshing preview
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_preview)
        self._timer.start(100)

        # Connect signals
        self.threshold_slider.valueChanged.connect(self.update_threshold)
        self.min_area_slider.valueChanged.connect(self.update_min_area)
        self.max_area_slider.valueChanged.connect(self.update_max_area)

        self._saved = False

    def initializePage(self):
        worker = self.worker_accessor()
        detector = worker._detector if worker else None
        if detector:
            self.threshold_slider.setValue(detector.threshold)
            self.threshold_label.setText(str(detector.threshold))
            self.min_area_slider.setValue(detector.min_contour_area)
            self.min_area_label.setText(str(detector.min_contour_area))
            self.max_area_slider.setValue(detector.large_contour_area)
            self.max_area_label.setText(str(detector.large_contour_area))

    def update_threshold(self, value):
        self.threshold_label.setText(str(value))
        worker = self.worker_accessor()
        detector = worker._detector if worker else None
        if detector:
            detector.threshold = value
        self._saved = False

    def update_min_area(self, value):
        self.min_area_label.setText(str(value))
        worker = self.worker_accessor()
        detector = worker._detector if worker else None
        if detector:
            detector.min_contour_area = value
        self._saved = False

    def update_max_area(self, value):
        self.max_area_label.setText(str(value))
        worker = self.worker_accessor()
        detector = worker._detector if worker else None
        if detector:
            detector.large_contour_area = value
        self._saved = False

    # ----------------------- Live preview ----------------------- #
    def _refresh_preview(self):
        worker = self.worker_accessor()
        # Prefer full result frame (includes drawn rectangles). This reflects
        # min / max area changes instantly. Fallback to threshold mask if the
        # worker has not produced a result yet.
        frame = worker.latest_display if worker.latest_display is not None else worker.latest_thresh
        if frame is None:
            return

        # Ensure we have an RGB image to draw on
        if len(frame.shape) == 2 or frame.shape[2] == 1:
            rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # ------------------------------------------------------------------
        # NEW: Draw bounding boxes around contours that are currently being
        #      filtered out by the min / max area sliders so that the user
        #      can instantly see which blobs will be ignored.
        # ------------------------------------------------------------------
        detector = worker._detector if worker else None
        if detector and worker.latest_thresh is not None:
            # Work with the latest threshold mask (single-channel preferred)
            thresh_src = worker.latest_thresh
            if len(thresh_src.shape) == 3 and thresh_src.shape[2] == 3:
                thresh_gray = cv2.cvtColor(thresh_src, cv2.COLOR_BGR2GRAY)
            else:
                thresh_gray = thresh_src.copy()

            # Find all contours in the threshold mask
            _contours, _ = cv2.findContours(
                thresh_gray, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_KCOS
            )
            for cnt in _contours:
                area = cv2.contourArea(cnt)
                # Highlight contours that fall OUTSIDE the accepted area range
                if area < detector.min_contour_area or area > detector.large_contour_area:
                    x, y, w, h = cv2.boundingRect(cnt)
                    cv2.rectangle(rgb, (x, y), (x + w, y + h), (255, 0, 0), 1)
        # ------------------------------------------------------------------

        # Convert to Qt image and push to preview label
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        scaled = img.scaled(
            self.preview_label.width() or 320,
            self.preview_label.height() or 240,
            Qt.KeepAspectRatio,
        )
        self.preview_label.setPixmap(QPixmap.fromImage(scaled))

    def validatePage(self):
        # Load existing profiles with error handling
        profiles, load_error = _load_json(CALIB_PROFILE_FILE, {})
        if load_error:
            QMessageBox.warning(self, "Load Error", 
                               f"Error loading existing profiles: {load_error}\n"
                               "Creating a new profile file.")
            profiles = {}
            
        # Update with new values
        profiles["last"] = {
            "threshold": self.threshold_slider.value(),
            "min_area": self.min_area_slider.value(),
            "max_area": self.max_area_slider.value(),
        }
        
        # Save with error handling
        save_error = _save_json(CALIB_PROFILE_FILE, profiles)
        if save_error:
            QMessageBox.critical(self, "Save Error", 
                                f"Failed to save calibration profile: {save_error}")
            return False
            
        self._saved = True
        return True


class FinalisationPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Profile Saved")
        self.setSubTitle("Your calibration profile has been saved.")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Click 'Finish' to apply and exit the wizard."))


class ConfirmationPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Calibration Complete")
        layout = QVBoxLayout(self)
        lbl = QLabel("Calibration profile is now active. Enjoy tracking!")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)


class CalibrationWizard(QWizard):
    def __init__(self, worker_accessor):
        super().__init__()
        self.setWindowTitle("Calibration Wizard")
        self.setOption(QWizard.NoCancelButton, False)
        self.setStyleSheet("""
            QWizard {
                background-color: #1F2937;
            }
            QLabel {
                color: #E0E0E0;
            }
            QWizardPage {
                background-color: #1F2937;
            }
            QProgressBar {
                border: 1px solid #56637A;
                border-radius: 4px;
                text-align: center;
                background-color: #38414F;
            }
            QProgressBar::chunk {
                background-color: #4A5469;
            }
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
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
            QPushButton:disabled {
                background-color: #2E3644;
                color: #788294;
            }
        """)

        # Pages
        self.addPage(LayoutPage())
        self.addPage(AutoCalibrationPage(worker_accessor))
        self.addPage(FineTunePage(worker_accessor))
        self.addPage(FinalisationPage())
        self.addPage(ConfirmationPage())

        self.setStartId(0)

    def setTitle(self, title):
        super().setTitle(f"<font color='#90EE90' size='6'><b>{title}</b></font>")

    def setSubTitle(self, subTitle):
        super().setSubTitle(f"<font color='#E0E0E0' size='4'>{subTitle}</font>")


# ------------------------- Busy Spinner Overlay ------------------------- #


class _BusyOverlay(QWidget):
    """Modal, semi-transparent overlay with animated ellipsis text."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self._label = QLabel(self)
        self._label.setStyleSheet("font-size:20px;font-weight:bold;color:white;")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._base_text = ""
        self._dots = 0
        self.hide()

    def start(self, text: str):
        self._base_text = text.rstrip(".")
        self._dots = 0
        self._tick()  # update immediately
        # Resize to parent
        self.resize(self.parent().size())
        self.show()
        self.raise_()
        self._timer.start(500)

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._dots = (self._dots + 1) % 4
        self._label.setText(self._base_text + "." * self._dots)
        # Center label
        self._label.adjustSize()
        parent_rect = self.rect()
        lbl_w, lbl_h = self._label.size().width(), self._label.size().height()
        self._label.move((parent_rect.width() - lbl_w) // 2, (parent_rect.height() - lbl_h) // 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 160)) 