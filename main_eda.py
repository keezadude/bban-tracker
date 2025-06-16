"""
Main entry point for BBAN-Tracker Event-Driven Architecture.

This module serves as the composition root for the application, implementing
dependency injection and wiring together all services according to the
architectural mandates. It demonstrates the complete EDA pattern with HAL.
"""

import sys
import time
import signal
import argparse
from pathlib import Path

from core.event_broker import EventBroker, DependencyContainer
from core.interfaces import ITrackerHardware, IProjectionAdapter
from hardware.realsense_d400_hal import RealSenseD400_HAL
from adapters.beysion_unity_adapter_corrected import BeysionUnityAdapterCorrected
from services.tracking_service import TrackingService
from services.gui_service import GUIService
from services.projection_service import ProjectionService


class BBanTrackerApplication:
    """
    Main application class that orchestrates the event-driven architecture.
    
    This class serves as the composition root and implements the dependency
    injection pattern to wire together all services and hardware abstractions.
    """
    
    def __init__(self, config: dict):
        """
        Initialize the application with dependency injection.
        
        Args:
            config: Application configuration including hardware settings
        """
        self.config = config
        self.shutdown_requested = False
        
        # Create dependency injection container
        self.container = DependencyContainer()
        
        # Core infrastructure
        self.event_broker = None
        self.tracking_service = None
        self.gui_service = None
        self.projection_service = None
        
        # Hardware abstractions
        self.hardware = None
        self.projection_adapter = None
    
    def initialize(self) -> bool:
        """
        Initialize all services using dependency injection pattern.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            print("[BBanTracker] Initializing Event-Driven Architecture...")
            
            # 1. Create event broker (central communication hub)
            print("[BBanTracker] Creating event broker...")
            self.event_broker = EventBroker(max_workers=4, max_queue_size=10000)
            
            # 2. Create hardware abstraction layer
            print("[BBanTracker] Initializing hardware abstraction layer...")
            self.hardware = RealSenseD400_HAL()
            
            # Register hardware in DI container
            self.container.register_singleton(ITrackerHardware, self.hardware)
            
            # 3. Create corrected projection adapter with UDP/TCP networking
            print("[BBanTracker] Creating BeysionUnityAdapterCorrected with UDP/TCP networking...")
            unity_path = self.config.get('unity_path')
            if unity_path:
                print(f"[BBanTracker] Unity executable path: {unity_path}")
            
            self.projection_adapter = BeysionUnityAdapterCorrected(
                udp_host="127.0.0.1",
                udp_port=50007,  # Unity listening port
                tcp_host="127.0.0.1", 
                tcp_port=50008,  # Unity command port
                unity_executable_path=unity_path
            )
            
            # Register corrected adapter in DI container  
            self.container.register_singleton(IProjectionAdapter, self.projection_adapter)
            print("[BBanTracker] ✅ Corrected BeysionUnityAdapterCorrected registered in DI container")
            
            # 4. Create services with dependency injection
            print("[BBanTracker] Creating services...")
            
            # Resolve dependencies from container
            hardware_interface = self.container.resolve(ITrackerHardware)
            projection_interface = self.container.resolve(IProjectionAdapter)
            
            # Verify we got the real adapter, not a placeholder
            adapter_type = type(projection_interface).__name__
            print(f"[BBanTracker] Resolved projection adapter: {adapter_type}")
            
            # Create services with injected dependencies
            self.tracking_service = TrackingService(self.event_broker, hardware_interface)
            self.gui_service = GUIService(self.event_broker)
            self.projection_service = ProjectionService(self.event_broker, projection_interface)
            
            # 4.5. Set up command callback for Unity commands (calibration, threshold)
            print("[BBanTracker] Setting up Unity command callback integration...")
            self._setup_unity_command_callback()
            
            # 5. Start services
            print("[BBanTracker] Starting services...")
            self.tracking_service.start()
            self.gui_service.start()
            self.projection_service.start()
            
            print("[BBanTracker] ✅ Event-Driven Architecture initialized successfully!")
            print(f"[BBanTracker] Services running: {self._get_service_status()}")
            
            return True
            
        except Exception as e:
            print(f"[BBanTracker] ❌ Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self, gui_mode: bool = True) -> None:
        """
        Run the main application loop.
        
        Args:
            gui_mode: If True, launch GUI application. If False, run console mode.
        """
        print(f"[BBanTracker] Starting application in {'GUI' if gui_mode else 'console'} mode...")
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            if gui_mode:
                self._run_gui_mode()
            else:
                self._run_console_mode()
                
        except KeyboardInterrupt:
            print("\n[BBanTracker] Shutdown requested by user")
        except Exception as e:
            print(f"[BBanTracker] Application error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.shutdown()
    
    def _run_gui_mode(self) -> None:
        """Run the application with GUI interface."""
        try:
            # Import EDA GUI Bridge for monolithic GUI integration
            from gui.eda_gui_bridge import create_eda_gui_application
            
            print("[BBanTracker] Creating EDA-integrated GUI application...")
            gui_app = create_eda_gui_application(self.gui_service)
            
            # Demonstrate EDA pattern for initial state
            self._demonstrate_eda_pattern()
            
            print("[BBanTracker] 🚀 Launching BBAN-Tracker with EDA Architecture")
            
            # Run Qt application event loop
            # This will block until the GUI is closed
            exit_code = gui_app.exec()
            
            print(f"[BBanTracker] EDA GUI application exited with code: {exit_code}")
            
        except ImportError as e:
            print(f"[BBanTracker] ❌ GUI dependencies not available: {e}")
            print("[BBanTracker] Falling back to console mode...")
            self._run_console_mode()
        except Exception as e:
            print(f"[BBanTracker] ❌ GUI launch failed: {e}")
            import traceback
            traceback.print_exc()
    
    def _run_console_mode(self) -> None:
        """Run the application in console mode (original implementation)."""
        print("[BBanTracker] Running in console mode...")
        
        # Demonstrate the EDA pattern by triggering some events
        self._demonstrate_eda_pattern()
        
        # Main loop - monitor services and handle demo timeout
        start_time = time.time()
        demo_time = self.config.get('demo_time', 0)
        
        while not self.shutdown_requested:
            # Monitor service health
            self._monitor_services()
            
            # Check demo timeout
            if demo_time > 0 and time.time() - start_time >= demo_time:
                print(f"\n[BBanTracker] Demo completed after {demo_time} seconds")
                break
            
            # Brief sleep to prevent excessive CPU usage
            time.sleep(1.0)
    
    def _demonstrate_eda_pattern(self) -> None:
        """
        Demonstrate the event-driven architecture by publishing some events.
        
        This shows how services communicate exclusively through events
        without direct coupling.
        """
        print("\n[BBanTracker] 🎯 Demonstrating Event-Driven Architecture...")
        
        # Simulate starting tracking
        from core.events import StartTracking
        print("[BBanTracker] Publishing StartTracking event...")
        self.gui_service.request_start_tracking(
            dev_mode=self.config.get('dev_mode', False),
            cam_src=self.config.get('cam_src', 0)
        )
        
        # Wait a bit for tracking to start
        time.sleep(2.0)
        
        # Simulate changing tracker settings
        print("[BBanTracker] Publishing tracker settings change...")
        self.gui_service.update_tracker_settings(
            threshold=25,
            min_area=150,
            max_area=2500
        )
        
        # Simulate projection configuration
        print("[BBanTracker] Publishing projection config...")
        self.gui_service.update_projection_config(1920, 1080)
        
        print("[BBanTracker] ✅ EDA demonstration complete - services are communicating via events")
    
    def _monitor_services(self) -> None:
        """Monitor service health and report status."""
        status = self._get_service_status()
        
        # Get event broker statistics
        broker_stats = self.event_broker.get_event_statistics()
        
        # Periodic status report (every 30 seconds)
        current_time = time.time()
        if not hasattr(self, '_last_status_report'):
            self._last_status_report = current_time
        
        if current_time - self._last_status_report > 30:
            print(f"\n[BBanTracker] 📊 Status Report:")
            print(f"  Services: {status}")
            print(f"  Events/sec: {broker_stats.get('events_per_second', 0):.1f}")
            print(f"  Total events: {broker_stats.get('total_events_published', 0)}")
            print(f"  Active subscriptions: {broker_stats.get('active_subscriptions', 0)}")
            
            self._last_status_report = current_time
    
    def _get_service_status(self) -> str:
        """Get a summary of service running status."""
        status = []
        if self.tracking_service and self.tracking_service.is_running():
            status.append("Tracking")
        if self.gui_service and self.gui_service.is_running():
            status.append("GUI")
        if self.projection_service and self.projection_service.is_running():
            status.append("Projection")
        
        return f"{len(status)}/3 ({', '.join(status)})"
    
    def _setup_unity_command_callback(self) -> None:
        """Set up command callback integration between Unity adapter and tracking service."""
        def unity_command_callback(command: str, adapter) -> str:
            """
            Handle Unity commands by forwarding them to the appropriate services.
            
            This integrates the corrected adapter with the EDA system by translating
            Unity commands to EDA events and returning appropriate responses.
            """
            try:
                if command == "calibrate":
                    # Publish calibration event to tracking service
                    from core.events import CalibrateTracker
                    self.event_broker.publish(CalibrateTracker())
                    print("[BBanTracker] Unity calibration request forwarded to tracking service")
                    return "calibrated"
                
                elif command == "threshold_up":
                    # Get current detector settings and increment threshold
                    current_settings = self.tracking_service.get_current_settings()
                    current_threshold = current_settings.get('threshold', 15)
                    new_threshold = current_threshold + 1
                    
                    # Publish threshold change event
                    from core.events import ChangeTrackerSettings
                    self.event_broker.publish(ChangeTrackerSettings(threshold=new_threshold))
                    print(f"[BBanTracker] Unity threshold_up: {current_threshold} -> {new_threshold}")
                    return f"threshold:{new_threshold}"
                
                elif command == "threshold_down":
                    # Get current detector settings and decrement threshold
                    current_settings = self.tracking_service.get_current_settings()
                    current_threshold = current_settings.get('threshold', 15)
                    new_threshold = max(1, current_threshold - 1)  # Prevent going below 1
                    
                    # Publish threshold change event
                    from core.events import ChangeTrackerSettings
                    self.event_broker.publish(ChangeTrackerSettings(threshold=new_threshold))
                    print(f"[BBanTracker] Unity threshold_down: {current_threshold} -> {new_threshold}")
                    return f"threshold:{new_threshold}"
                
                else:
                    print(f"[BBanTracker] Unknown Unity command: {command}")
                    return "unknown_command"
                    
            except Exception as e:
                print(f"[BBanTracker] Error handling Unity command '{command}': {e}")
                return "error"
        
        # Set the callback on the corrected adapter
        if hasattr(self.projection_adapter, 'set_command_callback'):
            self.projection_adapter.set_command_callback(unity_command_callback)
            print("[BBanTracker] ✅ Unity command callback integration complete")
        else:
            print("[BBanTracker] ❌ Warning: Adapter does not support command callbacks")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print(f"\n[BBanTracker] Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    def shutdown(self) -> None:
        """
        Gracefully shutdown all services and clean up resources.
        
        This demonstrates proper cleanup in the EDA pattern.
        """
        print("\n[BBanTracker] 🛑 Shutting down Event-Driven Architecture...")
        
        try:
            # Stop services in reverse order
            if self.projection_service:
                print("[BBanTracker] Stopping projection service...")
                self.projection_service.stop()
            
            if self.gui_service:
                print("[BBanTracker] Stopping GUI service...")
                self.gui_service.stop()
            
            if self.tracking_service:
                print("[BBanTracker] Stopping tracking service...")
                self.tracking_service.stop()
            
            # Shutdown event broker last
            if self.event_broker:
                print("[BBanTracker] Shutting down event broker...")
                stats = self.event_broker.get_event_statistics()
                print(f"[BBanTracker] Final statistics: {stats['total_events_published']} events published")
                self.event_broker.shutdown()
            
            print("[BBanTracker] ✅ Shutdown complete")
            
        except Exception as e:
            print(f"[BBanTracker] Error during shutdown: {e}")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="BBAN-Tracker Event-Driven Architecture")
    parser.add_argument(
        '--dev',
        action='store_true',
        help='Use development mode (webcam instead of RealSense)'
    )
    parser.add_argument(
        '--cam-src',
        type=int,
        default=0,
        help='Camera source index for development mode (default: 0)'
    )
    parser.add_argument(
        '--demo-time',
        type=int,
        default=0,
        help='Run for specified seconds then exit (for testing, 0=indefinite)'
    )
    parser.add_argument(
        '--unity-path',
        type=str,
        help='Path to Unity executable for projection client'
    )
    parser.add_argument(
        '--console-mode',
        action='store_true',
        help='Run in console mode instead of GUI mode'
    )
    
    return parser.parse_args()


def main():
    """Main entry point demonstrating the complete EDA architecture."""
    print("🚀 BBAN-Tracker Event-Driven Architecture")
    print("=" * 50)
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Create configuration
    config = {
        'dev_mode': args.dev,
        'cam_src': args.cam_src,
        'demo_time': args.demo_time,
        'unity_path': args.unity_path
    }
    
    print(f"Configuration: {config}")
    
    # Create and run application
    app = BBanTrackerApplication(config)
    
    if app.initialize():
        # Determine run mode
        gui_mode = not args.console_mode
        print(f"[BBanTracker] Run mode: {'GUI' if gui_mode else 'Console'}")
        
        # Run application
        app.run(gui_mode=gui_mode)
    else:
        print("[BBanTracker] ❌ Application initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    main() 