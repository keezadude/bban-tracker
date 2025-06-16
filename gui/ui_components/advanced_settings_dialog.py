"""
Advanced Settings Dialog for BBAN-Tracker Event-Driven Architecture.

Provides power users with access to advanced configuration options including
event batching toggles, serialization methods, performance optimization controls,
and detailed system metrics. Hidden from normal users but accessible for
system configuration and troubleshooting.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, 
    QCheckBox, QSpinBox, QComboBox, QPushButton, QGroupBox, QFormLayout,
    QTextEdit, QProgressBar, QGridLayout, QSlider, QFrame, QScrollArea
)
from PySide6.QtGui import QFont, QTextCursor


@dataclass
class AdvancedSettings:
    """Data structure for advanced settings."""
    
    # Event System Settings
    event_batching_enabled: bool = True
    event_batch_size: int = 10
    event_queue_max_size: int = 10000
    event_processing_threads: int = 4
    
    # Serialization Settings
    serialization_method: str = "pickle"  # pickle, json, msgpack
    compression_enabled: bool = True
    compression_level: int = 6
    
    # Performance Settings
    fps_target: int = 30
    adaptive_quality: bool = True
    frame_skip_threshold: int = 5
    memory_limit_mb: int = 512
    
    # Network Settings
    unity_timeout_ms: int = 5000
    unity_retry_count: int = 3
    udp_buffer_size: int = 65536
    tcp_keep_alive: bool = True
    
    # Debugging Settings
    debug_logging: bool = False
    performance_profiling: bool = False
    memory_monitoring: bool = False
    event_tracing: bool = False


class PerformanceMetricsWidget(QWidget):
    """Widget for displaying detailed performance metrics."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_timer()
        
    def _setup_ui(self):
        """Set up the performance metrics UI."""
        layout = QVBoxLayout(self)
        
        # CPU Usage
        cpu_group = QGroupBox("CPU Usage")
        cpu_layout = QFormLayout(cpu_group)
        
        self._cpu_label = QLabel("--")
        self._cpu_bar = QProgressBar()
        self._cpu_bar.setRange(0, 100)
        cpu_layout.addRow("Current:", self._cpu_label)
        cpu_layout.addRow("", self._cpu_bar)
        
        layout.addWidget(cpu_group)
        
        # Memory Usage
        memory_group = QGroupBox("Memory Usage")
        memory_layout = QFormLayout(memory_group)
        
        self._memory_label = QLabel("--")
        self._memory_bar = QProgressBar()
        self._memory_bar.setRange(0, 1024)  # MB
        memory_layout.addRow("Current:", self._memory_label)
        memory_layout.addRow("", self._memory_bar)
        
        layout.addWidget(memory_group)
        
        # Event Statistics
        events_group = QGroupBox("Event Statistics")
        events_layout = QFormLayout(events_group)
        
        self._events_total = QLabel("--")
        self._events_rate = QLabel("--")
        self._events_queue = QLabel("--")
        
        events_layout.addRow("Total Events:", self._events_total)
        events_layout.addRow("Events/sec:", self._events_rate)
        events_layout.addRow("Queue Size:", self._events_queue)
        
        layout.addWidget(events_group)
        
    def _setup_timer(self):
        """Set up timer for periodic updates."""
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_metrics)
        self._timer.start(1000)  # Update every second
        
    def _update_metrics(self):
        """Update the performance metrics display."""
        try:
            import psutil
            
            # CPU usage
            cpu_percent = psutil.cpu_percent()
            self._cpu_label.setText(f"{cpu_percent:.1f}%")
            self._cpu_bar.setValue(int(cpu_percent))
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_mb = memory.used / 1024 / 1024
            self._memory_label.setText(f"{memory_mb:.1f} MB ({memory.percent:.1f}%)")
            self._memory_bar.setValue(int(memory_mb))
            
        except ImportError:
            # psutil not available, show placeholder
            self._cpu_label.setText("N/A (psutil required)")
            self._memory_label.setText("N/A (psutil required)")


class NetworkDiagnosticsWidget(QWidget):
    """Widget for network diagnostics and testing."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the network diagnostics UI."""
        layout = QVBoxLayout(self)
        
        # Connection Status
        status_group = QGroupBox("Connection Status")
        status_layout = QFormLayout(status_group)
        
        self._unity_status = QLabel("Disconnected")
        self._unity_latency = QLabel("--")
        self._unity_packets = QLabel("--")
        
        status_layout.addRow("Unity Client:", self._unity_status)
        status_layout.addRow("Latency:", self._unity_latency)
        status_layout.addRow("Packets Sent:", self._unity_packets)
        
        layout.addWidget(status_group)
        
        # Test Controls
        test_group = QGroupBox("Network Tests")
        test_layout = QVBoxLayout(test_group)
        
        ping_button = QPushButton("Ping Unity Client")
        ping_button.clicked.connect(self._ping_unity)
        test_layout.addWidget(ping_button)
        
        stress_button = QPushButton("Connection Stress Test")
        stress_button.clicked.connect(self._stress_test)
        test_layout.addWidget(stress_button)
        
        layout.addWidget(test_group)
        
        # Results
        self._results_text = QTextEdit()
        self._results_text.setMaximumHeight(150)
        self._results_text.setReadOnly(True)
        layout.addWidget(QLabel("Test Results:"))
        layout.addWidget(self._results_text)
        
    def _ping_unity(self):
        """Perform ping test to Unity client."""
        self._results_text.append("Pinging Unity client...")
        # Implementation would test UDP/TCP connectivity
        
    def _stress_test(self):
        """Perform connection stress test."""
        self._results_text.append("Running connection stress test...")
        # Implementation would send burst of test packets


class AdvancedSettingsDialog(QDialog):
    """
    Advanced settings dialog for power users.
    
    Provides access to optimization settings, performance metrics,
    and system configuration options not exposed in the main UI.
    """
    
    settings_changed = Signal(dict)  # Emitted when settings are modified
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setMinimumSize(600, 500)
        self.setModal(True)
        
        self._settings = AdvancedSettings()
        self._config_file = Path.home() / ".beytracker" / "advanced_settings.json"
        
        self._setup_ui()
        self._setup_styling()
        self._load_settings()
        
    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Tab widget for different categories
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)
        
        # Performance Tab
        self._setup_performance_tab()
        
        # Event System Tab
        self._setup_event_system_tab()
        
        # Network Tab
        self._setup_network_tab()
        
        # Diagnostics Tab
        self._setup_diagnostics_tab()
        
        # Debugging Tab
        self._setup_debugging_tab()
        
        # Button box
        button_layout = QHBoxLayout()
        
        reset_button = QPushButton("Reset to Defaults")
        reset_button.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(reset_button)
        
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._apply_settings)
        button_layout.addWidget(apply_button)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self._ok_clicked)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
    
    def _setup_performance_tab(self):
        """Set up the performance settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Performance Settings
        perf_group = QGroupBox("Performance Settings")
        perf_layout = QFormLayout(perf_group)
        
        self._fps_target = QSpinBox()
        self._fps_target.setRange(15, 120)
        self._fps_target.setValue(self._settings.fps_target)
        perf_layout.addRow("Target FPS:", self._fps_target)
        
        self._adaptive_quality = QCheckBox("Enable Adaptive Quality")
        self._adaptive_quality.setChecked(self._settings.adaptive_quality)
        perf_layout.addRow(self._adaptive_quality)
        
        self._frame_skip = QSpinBox()
        self._frame_skip.setRange(1, 20)
        self._frame_skip.setValue(self._settings.frame_skip_threshold)
        perf_layout.addRow("Frame Skip Threshold:", self._frame_skip)
        
        self._memory_limit = QSpinBox()
        self._memory_limit.setRange(128, 2048)
        self._memory_limit.setSuffix(" MB")
        self._memory_limit.setValue(self._settings.memory_limit_mb)
        perf_layout.addRow("Memory Limit:", self._memory_limit)
        
        layout.addWidget(perf_group)
        
        # Performance Metrics
        metrics_widget = PerformanceMetricsWidget()
        layout.addWidget(metrics_widget)
        
        layout.addStretch()
        self._tabs.addTab(tab, "Performance")
    
    def _setup_event_system_tab(self):
        """Set up the event system settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Event Batching
        batch_group = QGroupBox("Event Batching")
        batch_layout = QFormLayout(batch_group)
        
        self._batching_enabled = QCheckBox("Enable Event Batching")
        self._batching_enabled.setChecked(self._settings.event_batching_enabled)
        batch_layout.addRow(self._batching_enabled)
        
        self._batch_size = QSpinBox()
        self._batch_size.setRange(1, 100)
        self._batch_size.setValue(self._settings.event_batch_size)
        batch_layout.addRow("Batch Size:", self._batch_size)
        
        self._queue_size = QSpinBox()
        self._queue_size.setRange(1000, 100000)
        self._queue_size.setValue(self._settings.event_queue_max_size)
        batch_layout.addRow("Max Queue Size:", self._queue_size)
        
        self._processing_threads = QSpinBox()
        self._processing_threads.setRange(1, 16)
        self._processing_threads.setValue(self._settings.event_processing_threads)
        batch_layout.addRow("Processing Threads:", self._processing_threads)
        
        layout.addWidget(batch_group)
        
        # Serialization
        serial_group = QGroupBox("Serialization")
        serial_layout = QFormLayout(serial_group)
        
        self._serialization = QComboBox()
        self._serialization.addItems(["pickle", "json", "msgpack"])
        self._serialization.setCurrentText(self._settings.serialization_method)
        serial_layout.addRow("Method:", self._serialization)
        
        self._compression = QCheckBox("Enable Compression")
        self._compression.setChecked(self._settings.compression_enabled)
        serial_layout.addRow(self._compression)
        
        self._compression_level = QSlider(Qt.Horizontal)
        self._compression_level.setRange(1, 9)
        self._compression_level.setValue(self._settings.compression_level)
        serial_layout.addRow("Compression Level:", self._compression_level)
        
        layout.addWidget(serial_group)
        
        layout.addStretch()
        self._tabs.addTab(tab, "Event System")
    
    def _setup_network_tab(self):
        """Set up the network settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Unity Connection
        unity_group = QGroupBox("Unity Connection")
        unity_layout = QFormLayout(unity_group)
        
        self._unity_timeout = QSpinBox()
        self._unity_timeout.setRange(1000, 30000)
        self._unity_timeout.setSuffix(" ms")
        self._unity_timeout.setValue(self._settings.unity_timeout_ms)
        unity_layout.addRow("Timeout:", self._unity_timeout)
        
        self._retry_count = QSpinBox()
        self._retry_count.setRange(1, 10)
        self._retry_count.setValue(self._settings.unity_retry_count)
        unity_layout.addRow("Retry Count:", self._retry_count)
        
        self._udp_buffer = QSpinBox()
        self._udp_buffer.setRange(8192, 1048576)
        self._udp_buffer.setValue(self._settings.udp_buffer_size)
        unity_layout.addRow("UDP Buffer Size:", self._udp_buffer)
        
        self._tcp_keepalive = QCheckBox("TCP Keep-Alive")
        self._tcp_keepalive.setChecked(self._settings.tcp_keep_alive)
        unity_layout.addRow(self._tcp_keepalive)
        
        layout.addWidget(unity_group)
        
        # Network Diagnostics
        diagnostics_widget = NetworkDiagnosticsWidget()
        layout.addWidget(diagnostics_widget)
        
        layout.addStretch()
        self._tabs.addTab(tab, "Network")
    
    def _setup_diagnostics_tab(self):
        """Set up the diagnostics tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # System Information
        info_group = QGroupBox("System Information")
        info_layout = QFormLayout(info_group)
        
        info_layout.addRow("Python Version:", QLabel("3.11+"))
        info_layout.addRow("PySide6 Version:", QLabel("6.7.0"))
        info_layout.addRow("OpenCV Version:", QLabel("4.11.0"))
        info_layout.addRow("Architecture:", QLabel("Event-Driven"))
        
        layout.addWidget(info_group)
        
        # Log Viewer
        log_group = QGroupBox("System Logs")
        log_layout = QVBoxLayout(log_group)
        
        self._log_viewer = QTextEdit()
        self._log_viewer.setReadOnly(True)
        self._log_viewer.setMaximumHeight(200)
        log_layout.addWidget(self._log_viewer)
        
        log_button_layout = QHBoxLayout()
        clear_log_button = QPushButton("Clear Logs")
        clear_log_button.clicked.connect(self._log_viewer.clear)
        log_button_layout.addWidget(clear_log_button)
        
        export_log_button = QPushButton("Export Logs")
        export_log_button.clicked.connect(self._export_logs)
        log_button_layout.addWidget(export_log_button)
        
        log_layout.addLayout(log_button_layout)
        layout.addWidget(log_group)
        
        layout.addStretch()
        self._tabs.addTab(tab, "Diagnostics")
    
    def _setup_debugging_tab(self):
        """Set up the debugging settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Debug Options
        debug_group = QGroupBox("Debug Options")
        debug_layout = QFormLayout(debug_group)
        
        self._debug_logging = QCheckBox("Enable Debug Logging")
        self._debug_logging.setChecked(self._settings.debug_logging)
        debug_layout.addRow(self._debug_logging)
        
        self._performance_profiling = QCheckBox("Performance Profiling")
        self._performance_profiling.setChecked(self._settings.performance_profiling)
        debug_layout.addRow(self._performance_profiling)
        
        self._memory_monitoring = QCheckBox("Memory Monitoring")
        self._memory_monitoring.setChecked(self._settings.memory_monitoring)
        debug_layout.addRow(self._memory_monitoring)
        
        self._event_tracing = QCheckBox("Event Tracing")
        self._event_tracing.setChecked(self._settings.event_tracing)
        debug_layout.addRow(self._event_tracing)
        
        layout.addWidget(debug_group)
        
        # Debug Actions
        actions_group = QGroupBox("Debug Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        dump_state_button = QPushButton("Dump System State")
        dump_state_button.clicked.connect(self._dump_system_state)
        actions_layout.addWidget(dump_state_button)
        
        force_gc_button = QPushButton("Force Garbage Collection")
        force_gc_button.clicked.connect(self._force_garbage_collection)
        actions_layout.addWidget(force_gc_button)
        
        test_events_button = QPushButton("Test Event System")
        test_events_button.clicked.connect(self._test_event_system)
        actions_layout.addWidget(test_events_button)
        
        layout.addWidget(actions_group)
        
        layout.addStretch()
        self._tabs.addTab(tab, "Debugging")
    
    def _setup_styling(self):
        """Set up dialog styling."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            
            QTabWidget::pane {
                border: 1px solid #555;
                background-color: #2b2b2b;
            }
            
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #555;
            }
            
            QTabBar::tab:selected {
                background-color: #4c4c4c;
                border-bottom: 1px solid #4c4c4c;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 8px;
                color: #ffffff;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px 0 3px;
                color: #cccccc;
            }
            
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555;
                padding: 5px 10px;
                border-radius: 3px;
                color: #ffffff;
            }
            
            QPushButton:hover {
                background-color: #4c4c4c;
            }
            
            QPushButton:pressed {
                background-color: #1e1e1e;
            }
            
            QCheckBox, QLabel {
                color: #ffffff;
            }
            
            QSpinBox, QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555;
                padding: 3px;
                border-radius: 3px;
                color: #ffffff;
            }
            
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #555;
                color: #ffffff;
                font-family: monospace;
            }
        """)
    
    def _load_settings(self):
        """Load settings from configuration file."""
        try:
            if self._config_file.exists():
                with open(self._config_file, 'r') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(self._settings, key):
                            setattr(self._settings, key, value)
        except Exception as e:
            print(f"[AdvancedSettings] Failed to load settings: {e}")
    
    def _save_settings(self):
        """Save settings to configuration file."""
        try:
            self._config_file.parent.mkdir(exist_ok=True)
            with open(self._config_file, 'w') as f:
                json.dump(asdict(self._settings), f, indent=2)
        except Exception as e:
            print(f"[AdvancedSettings] Failed to save settings: {e}")
    
    def _apply_settings(self):
        """Apply current settings."""
        # Update settings from UI
        self._settings.fps_target = self._fps_target.value()
        self._settings.adaptive_quality = self._adaptive_quality.isChecked()
        self._settings.frame_skip_threshold = self._frame_skip.value()
        self._settings.memory_limit_mb = self._memory_limit.value()
        
        self._settings.event_batching_enabled = self._batching_enabled.isChecked()
        self._settings.event_batch_size = self._batch_size.value()
        self._settings.event_queue_max_size = self._queue_size.value()
        self._settings.event_processing_threads = self._processing_threads.value()
        
        self._settings.serialization_method = self._serialization.currentText()
        self._settings.compression_enabled = self._compression.isChecked()
        self._settings.compression_level = self._compression_level.value()
        
        self._settings.unity_timeout_ms = self._unity_timeout.value()
        self._settings.unity_retry_count = self._retry_count.value()
        self._settings.udp_buffer_size = self._udp_buffer.value()
        self._settings.tcp_keep_alive = self._tcp_keepalive.isChecked()
        
        self._settings.debug_logging = self._debug_logging.isChecked()
        self._settings.performance_profiling = self._performance_profiling.isChecked()
        self._settings.memory_monitoring = self._memory_monitoring.isChecked()
        self._settings.event_tracing = self._event_tracing.isChecked()
        
        # Save and emit signal
        self._save_settings()
        self.settings_changed.emit(asdict(self._settings))
    
    def _ok_clicked(self):
        """Handle OK button click."""
        self._apply_settings()
        self.accept()
    
    def _reset_to_defaults(self):
        """Reset all settings to default values."""
        self._settings = AdvancedSettings()
        
        # Update UI controls
        self._fps_target.setValue(self._settings.fps_target)
        self._adaptive_quality.setChecked(self._settings.adaptive_quality)
        self._frame_skip.setValue(self._settings.frame_skip_threshold)
        self._memory_limit.setValue(self._settings.memory_limit_mb)
        
        # ... (update other controls)
        
    def _export_logs(self):
        """Export system logs to file."""
        print("[AdvancedSettings] Log export requested")
        
    def _dump_system_state(self):
        """Dump current system state for debugging."""
        print("[AdvancedSettings] System state dump requested")
        
    def _force_garbage_collection(self):
        """Force Python garbage collection."""
        import gc
        collected = gc.collect()
        print(f"[AdvancedSettings] Garbage collection: {collected} objects collected")
        
    def _test_event_system(self):
        """Test the event system functionality."""
        print("[AdvancedSettings] Event system test requested")
    
    def get_settings(self) -> AdvancedSettings:
        """Get current settings."""
        return self._settings


def show_advanced_settings_dialog(parent=None) -> Optional[AdvancedSettings]:
    """
    Show the advanced settings dialog.
    
    Args:
        parent: Parent widget
        
    Returns:
        AdvancedSettings if accepted, None if cancelled
    """
    dialog = AdvancedSettingsDialog(parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.get_settings()
    return None 