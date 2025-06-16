from __future__ import annotations

import numpy as np
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QFont
from PySide6.QtWidgets import QOpenGLWidget, QLabel, QVBoxLayout, QWidget, QPushButton, QHBoxLayout
from OpenGL.GL import *  # type: ignore
from OpenGL.GLU import gluUnProject, gluProject  # type: ignore


class PointCloudWidget(QOpenGLWidget):
    """Interactive OpenGL renderer for RealSense point-cloud visualization with measurement tools."""

    # Signal to notify parent widget of measurement updates
    measurement_updated = Signal(float, str)  # distance in meters, description

    def __init__(self, verts_provider: callable[[], np.ndarray | None], parent=None):
        super().__init__(parent)
        self._get_verts = verts_provider
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(30)  # ~33 FPS
        self._verts: np.ndarray | None = None
        
        # View rotation parameters
        self._rotation_x = 30.0
        self._rotation_y = -30.0
        self._zoom = -1.5
        
        # Mouse interaction
        self._last_pos = None
        self._measuring = False
        self._measure_points = []  # List to store selected measurement points
        self._measure_distance = None  # Current measurement result
        
        # Initialize overlay for displaying measurement information
        self._overlay_widget = MeasurementOverlay(parent=self.parent())
        
        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        
    def enable_measurement(self, enable: bool):
        """Toggle measurement mode."""
        self._measuring = enable
        if not enable:
            self._measure_points = []
            self._measure_distance = None
            self._overlay_widget.hide()
        else:
            self._overlay_widget.show()
            self._overlay_widget.set_message("Click to select first point")

    # ---------------- OpenGL lifecycle ---------------- #
    def initializeGL(self):
        glClearColor(0.05, 0.05, 0.05, 1.0)
        glEnable(GL_DEPTH_TEST)
        glPointSize(2.0)
        
        # Enable simple lighting for better 3D perception
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, [0.0, 5.0, 5.0, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        
        # Enable point smoothing for nicer points
        glEnable(GL_POINT_SMOOTH)
        glHint(GL_POINT_SMOOTH_HINT, GL_NICEST)

    def resizeGL(self, w: int, h: int):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = w / h if h else 1.0
        gluPerspective(60.0, aspect, 0.05, 5.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(0.0, 0.0, self._zoom)  # Adjustable zoom
        glRotatef(self._rotation_x, 1, 0, 0)
        glRotatef(self._rotation_y, 0, 1, 0)

        # Fetch latest vertices (in metres)
        verts = self._get_verts()
        if verts is None:
            return
        self._verts = verts

        # Draw coordinate axes for reference
        self._draw_axes()
        
        # Draw measurement points if in measurement mode
        if self._measuring and self._measure_points:
            glDisable(GL_LIGHTING)  # Disable lighting for measurement points
            
            # Draw selected measurement points
            glPointSize(8.0)
            for i, point in enumerate(self._measure_points):
                # First point red, second point blue
                color = [1.0, 0.0, 0.0] if i == 0 else [0.0, 0.5, 1.0]
                glColor3f(*color)
                glBegin(GL_POINTS)
                glVertex3f(point[0], point[1], point[2])
                glEnd()
                
            # Draw line between measurement points if we have two
            if len(self._measure_points) == 2:
                glLineWidth(2.0)
                glColor3f(1.0, 1.0, 0.0)  # Yellow line
                glBegin(GL_LINES)
                glVertex3f(*self._measure_points[0])
                glVertex3f(*self._measure_points[1])
                glEnd()
                
            glEnable(GL_LIGHTING)  # Re-enable lighting
        
        # Draw the point cloud with lighting effects
        glDisable(GL_LIGHTING)  # Disable lighting for points
        
        # Draw white points
        glColor3f(0.9, 0.9, 0.9)
        glBegin(GL_POINTS)
        for x, y, z in verts:
            glVertex3f(x, -y, -z)  # Simple axis mapping
        glEnd()
        
        glEnable(GL_LIGHTING)

    def _draw_axes(self):
        """Draw RGB coordinate axes (X=red, Y=green, Z=blue)."""
        glDisable(GL_LIGHTING)
        
        axis_length = 0.2  # 20 cm axes
        
        glLineWidth(3.0)
        glBegin(GL_LINES)
        # X axis (red)
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(axis_length, 0.0, 0.0)
        
        # Y axis (green)
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, axis_length, 0.0)
        
        # Z axis (blue)
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, axis_length)
        glEnd()
        
        glEnable(GL_LIGHTING)

    # ---------------- Mouse interaction ---------------- #
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events for measurement and rotation."""
        self._last_pos = event.position()
        
        if self._measuring and event.button() == Qt.LeftButton:
            # Try to find the 3D point under the cursor
            point = self._get_3d_point_at_cursor(event.position().x(), event.position().y())
            if point is not None:
                if len(self._measure_points) < 2:
                    self._measure_points.append(point)
                    
                    if len(self._measure_points) == 1:
                        self._overlay_widget.set_message("Click to select second point")
                    elif len(self._measure_points) == 2:
                        # Calculate distance between points
                        p1, p2 = self._measure_points
                        distance = np.linalg.norm(np.array(p1) - np.array(p2))
                        # Convert to millimeters for display
                        distance_mm = distance * 1000
                        
                        # Update measurement info
                        self._measure_distance = distance
                        self._overlay_widget.set_measurement(distance_mm)
                        
                        # Emit signal with measurement data
                        self.measurement_updated.emit(distance, f"Distance: {distance_mm:.1f} mm")
            
    def mouseReleaseEvent(self, event: QMouseEvent):
        self._last_pos = None

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse movement for camera rotation."""
        if not self._measuring and self._last_pos and event.buttons() == Qt.LeftButton:
            # Rotate the view
            dx = event.position().x() - self._last_pos.x()
            dy = event.position().y() - self._last_pos.y()
            
            # Update rotation angles
            self._rotation_y += dx * 0.5
            self._rotation_x += dy * 0.5
            
            self.update()
            
        self._last_pos = event.position()
    
    def wheelEvent(self, event):
        """Handle mouse wheel for zooming."""
        delta = event.angleDelta().y() / 120
        self._zoom += delta * 0.1
        # Limit zoom range
        self._zoom = max(-3.0, min(-0.5, self._zoom))
        self.update()

    def _get_3d_point_at_cursor(self, mouse_x, mouse_y):
        """Find the closest point in the point cloud to the cursor position."""
        if self._verts is None or len(self._verts) == 0:
            return None
            
        # Get viewport, projection, and model-view matrices
        viewport = glGetIntegerv(GL_VIEWPORT)
        projection = glGetDoublev(GL_PROJECTION_MATRIX)
        model_view = glGetDoublev(GL_MODELVIEW_MATRIX)
        
        # Convert mouse y-coordinate (OpenGL has origin at bottom left)
        y = viewport[3] - mouse_y
        
        # Try to find the closest point in the point cloud
        min_dist = float('inf')
        closest_point = None
        
        for vert in self._verts:
            # Apply our axis mapping to match what's displayed
            x, y_mapped, z_mapped = vert[0], -vert[1], -vert[2]
            
            # Project the 3D point to screen space
            win_x, win_y, win_z = gluProject(
                x, y_mapped, z_mapped,
                model_view, projection, viewport)
                
            # Calculate 2D screen distance to mouse cursor
            screen_dist = ((win_x - mouse_x)**2 + (win_y - y)**2)**0.5
            
            # If this is closest so far, remember it
            if screen_dist < min_dist and screen_dist < 15:  # 15 pixel tolerance
                min_dist = screen_dist
                closest_point = (x, y_mapped, z_mapped)
        
        return closest_point

    # ---------------- Public methods for measurement ---------------- #
    def reset_measurement(self):
        """Clear current measurement points."""
        self._measure_points = []
        self._measure_distance = None
        if self._measuring:
            self._overlay_widget.set_message("Click to select first point")
            self._overlay_widget.clear_measurement()
        self.update()
    
    def get_current_measurement(self) -> float:
        """Return the current measurement distance in meters."""
        return self._measure_distance if self._measure_distance is not None else 0.0


class MeasurementOverlay(QWidget):
    """Overlay widget for displaying measurement information."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        
        # Semi-transparent dark background
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Layout
        layout = QVBoxLayout(self)
        
        self.instruction_label = QLabel("Measurement mode")
        self.instruction_label.setStyleSheet("color: white; font-weight: bold;")
        layout.addWidget(self.instruction_label)
        
        self.measurement_label = QLabel()
        self.measurement_label.setStyleSheet("color: #5DC1B9; font-size: 14pt;")
        layout.addWidget(self.measurement_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setFixedWidth(80)
        button_layout.addWidget(self.reset_btn)
        
        layout.addLayout(button_layout)
        
        # Position in upper-right corner of parent
        self.setFixedSize(200, 100)
        self._position_overlay()
    
    def _position_overlay(self):
        """Position the overlay in the top-right corner of its parent."""
        if self.parent():
            parent_rect = self.parent().rect()
            self.move(parent_rect.width() - self.width() - 20, 20)
    
    def set_message(self, message: str):
        """Update the instruction message."""
        self.instruction_label.setText(message)
    
    def set_measurement(self, distance_mm: float):
        """Update the measurement display."""
        self.measurement_label.setText(f"Distance: {distance_mm:.1f} mm")
    
    def clear_measurement(self):
        """Clear the measurement display."""
        self.measurement_label.setText("")
    
    def paintEvent(self, event):
        """Draw semi-transparent background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(40, 40, 40, 200))
        painter.drawRoundedRect(self.rect(), 10, 10) 