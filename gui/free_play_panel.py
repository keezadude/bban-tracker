"""
FreePlayPage for BBAN-Tracker Event-Driven Architecture.

This module contains the Free Play Mode UI panel extracted and modernized for EDA integration.
Provides an intuitive gaming interface for unlimited beyblade battles.
"""

from __future__ import annotations

import time
from typing import Optional, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QGridLayout, QMessageBox
)


class FreePlayPage(QWidget):
    """Free Play Mode gaming interface with score tracking and game controls."""
    
    def __init__(self, status_cb):
        super().__init__()
        self._status_cb = status_cb
        
        # Game state
        self._game_active = False
        self._score_p1 = 0
        self._score_p2 = 0
        self._time_remaining = 300  # 5 minutes default
        self._start_time = None
        
        # EDA integration attributes
        self.event_broker = None
        self._eda_callback = None
        
        # Navigation callbacks
        self.cb_open_system_hub: Optional[Callable] = None
        self.cb_open_tracker: Optional[Callable] = None
        self.cb_open_projection: Optional[Callable] = None
        self.cb_open_calibration: Optional[Callable] = None
        
        self._setup_ui()
        self._setup_timer()
    
    def set_eda_integration(self, event_broker=None, eda_callback=None):
        """Set EDA integration for event publishing."""
        self.event_broker = event_broker
        self._eda_callback = eda_callback
        print("[FreePlayPage] EDA integration configured")
    
    def _setup_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Header with navigation
        header_layout = QHBoxLayout()
        
        header = QLabel("FREE PLAY MODE")
        header.setStyleSheet("font-size:28px;font-weight:bold;color:#90EE90;")
        header_layout.addWidget(header, alignment=Qt.AlignLeft)
        
        header_layout.addStretch()
        
        # Navigation buttons
        self.btn_back = QPushButton("← System Hub")
        self.btn_back.clicked.connect(self._on_back_clicked)
        header_layout.addWidget(self.btn_back)
        
        layout.addLayout(header_layout)
        
        # Game timer display
        timer_group = QGroupBox("Game Timer")
        timer_layout = QHBoxLayout(timer_group)
        
        self.timer_label = QLabel("05:00")
        self.timer_label.setStyleSheet("""
            QLabel {
                font-size: 36px;
                font-weight: bold;
                color: #4CAF50;
                text-align: center;
                background-color: #1e1e1e;
                border: 2px solid #555;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        self.timer_label.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.timer_label)
        
        layout.addWidget(timer_group)
        
        # Score display and controls
        scores_layout = QHBoxLayout()
        
        # Player 1 Score
        p1_group = QGroupBox("PLAYER 1")
        p1_layout = QVBoxLayout(p1_group)
        
        self.score_p1_label = QLabel("0")
        self.score_p1_label.setStyleSheet("""
            QLabel {
                font-size: 72px;
                font-weight: bold;
                color: #2196F3;
                text-align: center;
                background-color: #1e1e1e;
                border: 2px solid #2196F3;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        self.score_p1_label.setAlignment(Qt.AlignCenter)
        p1_layout.addWidget(self.score_p1_label)
        
        self.btn_p1_add = QPushButton("+1 Point")
        self.btn_p1_add.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 10px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.btn_p1_add.clicked.connect(self._add_p1_score)
        p1_layout.addWidget(self.btn_p1_add)
        
        scores_layout.addWidget(p1_group, 1)
        
        # Center game controls
        controls_group = QGroupBox("Game Control")
        controls_layout = QVBoxLayout(controls_group)
        
        self.status_label = QLabel("Ready to Start")
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #FFC107;
                text-align: center;
                padding: 10px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        controls_layout.addWidget(self.status_label)
        
        self.btn_start_stop = QPushButton("Start Game")
        self.btn_start_stop.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px;
                border: none;
                border-radius: 8px;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_start_stop.clicked.connect(self._toggle_game)
        controls_layout.addWidget(self.btn_start_stop)
        
        self.btn_reset = QPushButton("Reset Scores")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        self.btn_reset.clicked.connect(self._reset_game)
        controls_layout.addWidget(self.btn_reset)
        
        scores_layout.addWidget(controls_group, 1)
        
        # Player 2 Score
        p2_group = QGroupBox("PLAYER 2")
        p2_layout = QVBoxLayout(p2_group)
        
        self.score_p2_label = QLabel("0")
        self.score_p2_label.setStyleSheet("""
            QLabel {
                font-size: 72px;
                font-weight: bold;
                color: #F44336;
                text-align: center;
                background-color: #1e1e1e;
                border: 2px solid #F44336;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        self.score_p2_label.setAlignment(Qt.AlignCenter)
        p2_layout.addWidget(self.score_p2_label)
        
        self.btn_p2_add = QPushButton("+1 Point")
        self.btn_p2_add.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 10px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
        """)
        self.btn_p2_add.clicked.connect(self._add_p2_score)
        p2_layout.addWidget(self.btn_p2_add)
        
        scores_layout.addWidget(p2_group, 1)
        
        layout.addLayout(scores_layout)
        
        # Quick access panel
        quick_access_group = QGroupBox("Quick Access")
        quick_layout = QHBoxLayout(quick_access_group)
        
        self.btn_tracker = QPushButton("⚙ Tracker Setup")
        self.btn_tracker.clicked.connect(self._on_tracker_clicked)
        quick_layout.addWidget(self.btn_tracker)
        
        self.btn_projection = QPushButton("📽 Projection Setup")
        self.btn_projection.clicked.connect(self._on_projection_clicked)
        quick_layout.addWidget(self.btn_projection)
        
        self.btn_calibration = QPushButton("🎯 Calibrate")
        self.btn_calibration.clicked.connect(self._on_calibration_clicked)
        quick_layout.addWidget(self.btn_calibration)
        
        layout.addWidget(quick_access_group)
        
        # Apply overall styling
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 10px;
                color: #fff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ccc;
            }
            QPushButton {
                background-color: #3c3c3c;
                color: #fff;
                border: 1px solid #555;
                padding: 8px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #4c4c4c;
            }
        """)
    
    def _setup_timer(self):
        """Setup the game timer."""
        self._game_timer = QTimer(self)
        self._game_timer.timeout.connect(self._update_timer)
    
    def _toggle_game(self):
        """Toggle game start/stop."""
        if not self._game_active:
            self._start_game()
        else:
            self._stop_game()
    
    def _start_game(self):
        """Start the free play game."""
        self._game_active = True
        self._start_time = time.time()
        self._time_remaining = 300  # 5 minutes
        
        self.btn_start_stop.setText("Stop Game")
        self.btn_start_stop.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px;
                border: none;
                border-radius: 8px;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        
        self.status_label.setText("Game Active!")
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #4CAF50;
                text-align: center;
                padding: 10px;
            }
        """)
        
        # Enable scoring
        self.btn_p1_add.setEnabled(True)
        self.btn_p2_add.setEnabled(True)
        
        # Start timer
        self._game_timer.start(1000)  # Update every second
        
        self._status_cb("Free Play game started!")
        
        # Notify EDA system about game start
        if hasattr(self, 'event_broker') and self.event_broker:
            # Could publish a custom FreePlayGameStarted event
            pass
    
    def _stop_game(self):
        """Stop the free play game."""
        self._game_active = False
        self._game_timer.stop()
        
        self.btn_start_stop.setText("Start Game")
        self.btn_start_stop.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px;
                border: none;
                border-radius: 8px;
                min-height: 50px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        self.status_label.setText("Game Stopped")
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #FF9800;
                text-align: center;
                padding: 10px;
            }
        """)
        
        # Show final score
        winner = ""
        if self._score_p1 > self._score_p2:
            winner = "Player 1 Wins!"
        elif self._score_p2 > self._score_p1:
            winner = "Player 2 Wins!"
        else:
            winner = "It's a Tie!"
        
        QMessageBox.information(self, "Game Over", f"Final Score:\nPlayer 1: {self._score_p1}\nPlayer 2: {self._score_p2}\n\n{winner}")
        
        self._status_cb(f"Free Play game ended - {winner}")
    
    def _reset_game(self):
        """Reset all game scores and timer."""
        if self._game_active:
            reply = QMessageBox.question(
                self, 
                "Reset Game", 
                "Game is currently active. Reset scores and stop game?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
            self._stop_game()
        
        self._score_p1 = 0
        self._score_p2 = 0
        self._time_remaining = 300
        
        self.score_p1_label.setText("0")
        self.score_p2_label.setText("0")
        self.timer_label.setText("05:00")
        
        self.status_label.setText("Ready to Start")
        self.status_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #FFC107;
                text-align: center;
                padding: 10px;
            }
        """)
        
        self._status_cb("Free Play scores reset")
    
    def _add_p1_score(self):
        """Add point to Player 1."""
        if self._game_active:
            self._score_p1 += 1
            self.score_p1_label.setText(str(self._score_p1))
            self._status_cb(f"Player 1 scores! ({self._score_p1})")
    
    def _add_p2_score(self):
        """Add point to Player 2."""
        if self._game_active:
            self._score_p2 += 1
            self.score_p2_label.setText(str(self._score_p2))
            self._status_cb(f"Player 2 scores! ({self._score_p2})")
    
    def _update_timer(self):
        """Update the game timer display."""
        if self._game_active and self._start_time:
            elapsed = time.time() - self._start_time
            remaining = max(0, self._time_remaining - elapsed)
            
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            
            self.timer_label.setText(f"{minutes:02d}:{seconds:02d}")
            
            # Change color when time is running low
            if remaining <= 60:  # Last minute
                self.timer_label.setStyleSheet("""
                    QLabel {
                        font-size: 36px;
                        font-weight: bold;
                        color: #F44336;
                        text-align: center;
                        background-color: #1e1e1e;
                        border: 2px solid #F44336;
                        border-radius: 8px;
                        padding: 10px;
                    }
                """)
            
            # Auto-stop when time runs out
            if remaining <= 0:
                self.timer_label.setText("00:00")
                self._stop_game()
                QMessageBox.information(self, "Time's Up!", "Game ended due to time limit!")
    
    # Navigation event handlers
    def _on_back_clicked(self):
        """Handle back to system hub."""
        if self.cb_open_system_hub:
            if self._game_active:
                reply = QMessageBox.question(
                    self,
                    "Exit Game",
                    "Game is currently active. Exit to System Hub?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
                self._stop_game()
            self.cb_open_system_hub()
    
    def _on_tracker_clicked(self):
        """Handle tracker setup navigation."""
        if self.cb_open_tracker:
            self.cb_open_tracker()
    
    def _on_projection_clicked(self):
        """Handle projection setup navigation."""
        if self.cb_open_projection:
            self.cb_open_projection()
    
    def _on_calibration_clicked(self):
        """Handle calibration navigation."""
        if self.cb_open_calibration:
            self.cb_open_calibration()
    
    # Navigation callback setters
    def set_system_hub_callback(self, callback: Callable):
        """Set the system hub navigation callback."""
        self.cb_open_system_hub = callback
    
    def set_tracker_callback(self, callback: Callable):
        """Set the tracker navigation callback."""
        self.cb_open_tracker = callback
    
    def set_projection_callback(self, callback: Callable):
        """Set the projection navigation callback."""
        self.cb_open_projection = callback
    
    def set_calibration_callback(self, callback: Callable):
        """Set the calibration navigation callback."""
        self.cb_open_calibration = callback
    
    def showEvent(self, event):
        """Handle show event."""
        super().showEvent(event)
        self._status_cb("Free Play Mode activated")
    
    def hideEvent(self, event):
        """Handle hide event."""
        super().hideEvent(event)
        if self._game_active:
            self._stop_game() 