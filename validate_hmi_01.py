"""
Validation script for HMI-01 implementation.
Tests basic imports and instantiation without running full test suite.
"""

import sys
import traceback

def validate_imports():
    """Validate all required imports."""
    print("=== Validating Imports ===")
    
    try:
        from core.event_broker import EventBroker
        from core.events import (
            TrackingDataUpdated, TrackingStarted, TrackingStopped, TrackingError,
            ChangeTrackerSettings, StartTracking, StopTracking, BeyData, HitData
        )
        from services.gui_service import GUIService
        print("✓ Core imports successful")
        
        try:
            from gui.eda_main_gui import PixelPerfectTrackerSetupPage
            print("✓ PixelPerfectTrackerSetupPage import successful")
        except ImportError as e:
            print(f"✗ GUI import failed: {e}")
            return False
            
        return True
        
    except ImportError as e:
        print(f"✗ Core import failed: {e}")
        return False

def validate_instantiation():
    """Validate that classes can be instantiated."""
    print("\n=== Validating Instantiation ===")
    
    try:
        from core.event_broker import EventBroker
        from services.gui_service import GUIService
        from gui.eda_main_gui import PixelPerfectTrackerSetupPage
        
        # Create event broker
        event_broker = EventBroker(max_workers=1, max_queue_size=10)
        print("✓ EventBroker created")
        
        # Create GUI service
        gui_service = GUIService(event_broker)
        print("✓ GUIService created")
        
        # Create tracker setup page
        tracker_page = PixelPerfectTrackerSetupPage(gui_service)
        print("✓ PixelPerfectTrackerSetupPage created")
        
        # Clean up
        gui_service.stop()
        event_broker.shutdown()
        print("✓ Services cleaned up")
        
        return True
        
    except Exception as e:
        print(f"✗ Instantiation failed: {e}")
        traceback.print_exc()
        return False

def validate_event_handling():
    """Validate event data structures."""
    print("\n=== Validating Event Structures ===")
    
    try:
        from core.events import BeyData, HitData, TrackingDataUpdated, TrackingStarted
        import time
        
        # Create BeyData
        bey = BeyData(
            id=1, 
            pos=(100, 200), 
            velocity=(1.0, 2.0),
            raw_velocity=(1.0, 2.0), 
            acceleration=(0.1, 0.2), 
            shape=(20, 20), 
            frame=123
        )
        print(f"✓ BeyData created: {bey}")
        
        # Create HitData
        hit = HitData(
            pos=(150, 250), 
            shape=(30, 30), 
            bey_ids=(1, 2), 
            is_new_hit=True
        )
        print(f"✓ HitData created: {hit}")
        
        # Create TrackingDataUpdated event
        tracking_event = TrackingDataUpdated(
            frame_id=123,
            timestamp=time.time(),
            beys=[bey],
            hits=[hit]
        )
        print(f"✓ TrackingDataUpdated event created: frame_id={tracking_event.frame_id}")
        
        # Create TrackingStarted event
        started_event = TrackingStarted(
            camera_type="Mock Camera",
            resolution=(640, 360)
        )
        print(f"✓ TrackingStarted event created: {started_event.camera_type}")
        
        return True
        
    except Exception as e:
        print(f"✗ Event validation failed: {e}")
        traceback.print_exc()
        return False

def validate_ui_components():
    """Validate UI component creation."""
    print("\n=== Validating UI Components ===")
    
    try:
        # This requires PySide6, so we'll just check if the imports work
        from gui.eda_main_gui import PixelPerfectTrackerSetupPage
        from services.gui_service import GUIService
        from core.event_broker import EventBroker
        
        print("✓ All UI-related imports successful")
        
        # Check that the class has required methods
        required_methods = [
            'create_page_content',
            'handle_tracking_data_updated',
            'handle_tracking_started', 
            'handle_tracking_stopped',
            'handle_tracking_error',
            'update_performance_metrics'
        ]
        
        for method in required_methods:
            if hasattr(PixelPerfectTrackerSetupPage, method):
                print(f"✓ Method {method} exists")
            else:
                print(f"✗ Method {method} missing")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ UI component validation failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all validations."""
    print("HMI-01 Implementation Validation")
    print("=" * 40)
    
    results = []
    
    # Run validations
    results.append(("Imports", validate_imports()))
    results.append(("Event Structures", validate_event_handling()))
    results.append(("UI Components", validate_ui_components()))
    results.append(("Instantiation", validate_instantiation()))
    
    # Print summary
    print("\n" + "=" * 40)
    print("VALIDATION SUMMARY")
    print("=" * 40)
    
    all_passed = True
    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{test_name:<20} {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 40)
    if all_passed:
        print("🎉 ALL VALIDATIONS PASSED")
        print("HMI-01 implementation is ready for testing!")
        return 0
    else:
        print("❌ SOME VALIDATIONS FAILED")
        print("Please fix the issues above before proceeding.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 