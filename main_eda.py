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
from services.tracking_service import TrackingService
from services.gui_service import GUIService
from services.projection_service import ProjectionService


class BeysionUnityAdapter:
    """Placeholder adapter for Unity client communication.
    
    This is a minimal implementation to satisfy the architecture requirements.
    Full implementation will be completed in CORE-02.
    """
    
    def __init__(self):
        self._connected = False
    
    def connect(self) -> bool:
        print("[BeysionUnityAdapter] Placeholder adapter - connect")
        return True
    
    def disconnect(self) -> None:
        print("[BeysionUnityAdapter] Placeholder adapter - disconnect")
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    def send_tracking_data(self, frame_id: int, beys: list, hits: list) -> bool:
        # Placeholder - just log the data
        print(f"[BeysionUnityAdapter] Frame {frame_id}: {len(beys)} beys, {len(hits)} hits")
        return True
    
    def send_projection_config(self, width: int, height: int) -> bool:
        print(f"[BeysionUnityAdapter] Projection config: {width}×{height}")
        return True
    
    def receive_commands(self) -> list:
        return []
    
    def get_client_info(self) -> dict:
        return {'address': 'localhost', 'status': 'placeholder'}


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
            
            # 3. Create projection adapter (placeholder for now)
            print("[BBanTracker] Creating projection adapter...")
            self.projection_adapter = BeysionUnityAdapter()
            
            # Register adapter in DI container  
            self.container.register_singleton(IProjectionAdapter, self.projection_adapter)
            
            # 4. Create services with dependency injection
            print("[BBanTracker] Creating services...")
            
            # Resolve dependencies from container
            hardware_interface = self.container.resolve(ITrackerHardware)
            projection_interface = self.container.resolve(IProjectionAdapter)
            
            # Create services with injected dependencies
            self.tracking_service = TrackingService(self.event_broker, hardware_interface)
            self.gui_service = GUIService(self.event_broker)
            self.projection_service = ProjectionService(self.event_broker, projection_interface)
            
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
            return False
    
    def run(self) -> None:
        """
        Run the main application loop.
        
        This demonstrates how the EDA operates with minimal coordination
        from the main application - services communicate via events.
        """
        print("[BBanTracker] Starting main application loop...")
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            # Demonstrate the EDA pattern by triggering some events
            self._demonstrate_eda_pattern()
            
            # Main loop - in a real application this might be a GUI event loop
            while not self.shutdown_requested:
                # Monitor service health
                self._monitor_services()
                
                # Brief sleep to prevent excessive CPU usage
                time.sleep(1.0)
                
        except KeyboardInterrupt:
            print("\n[BBanTracker] Shutdown requested by user")
        except Exception as e:
            print(f"[BBanTracker] Application error: {e}")
        finally:
            self.shutdown()
    
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
        default=60,
        help='Run for specified seconds then exit (for testing)'
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
        'demo_time': args.demo_time
    }
    
    print(f"Configuration: {config}")
    
    # Create and run application
    app = BBanTrackerApplication(config)
    
    if app.initialize():
        # Run for specified time in demo mode, or indefinitely
        if config['demo_time'] > 0:
            print(f"\n[BBanTracker] Running for {config['demo_time']} seconds...")
            start_time = time.time()
            
            try:
                while time.time() - start_time < config['demo_time']:
                    app._monitor_services()
                    time.sleep(1.0)
            except KeyboardInterrupt:
                pass
            
            print(f"\n[BBanTracker] Demo completed after {config['demo_time']} seconds")
        else:
            app.run()
    else:
        print("[BBanTracker] ❌ Application initialization failed")
        sys.exit(1)


if __name__ == "__main__":
    main() 