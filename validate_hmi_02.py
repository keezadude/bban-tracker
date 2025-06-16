"""
Validation script for HMI-02 implementation.
Tests basic imports and instantiation without running full test suite.
"""

import sys
import traceback

def validate_imports():
    """Validate all required imports."""
    print("=== Validating HMI-02 Imports ===")
    
    try:
        from core.event_broker import EventBroker
        from core.events import (
            ProjectionConfigUpdated, ProjectionClientConnected, ProjectionClientDisconnected,
            SystemShutdown
        )
        from services.gui_service import GUIService
        print("✓ Core imports successful")
        
        try:
            from gui.eda_main_gui import PixelPerfectProjectionSetupPage
            print("✓ PixelPerfectProjectionSetupPage import successful")
        except ImportError as e:
            print(f"✗ GUI import failed: {e}")
            return False
            
        return True
        
    except ImportError as e:
        print(f"✗ Core import failed: {e}")
        return False

def validate_instantiation():
    """Validate that classes can be instantiated."""
    print("\n=== Validating HMI-02 Instantiation ===")
    
    try:
        from core.event_broker import EventBroker
        from services.gui_service import GUIService
        from gui.eda_main_gui import PixelPerfectProjectionSetupPage
        
        # Create event broker
        event_broker = EventBroker(max_workers=1, max_queue_size=10)
        print("✓ EventBroker created")
        
        # Create GUI service
        gui_service = GUIService(event_broker)
        print("✓ GUIService created")
        
        # Create projection setup page
        projection_page = PixelPerfectProjectionSetupPage(gui_service)
        print("✓ PixelPerfectProjectionSetupPage created")
        
        # Test that transform state exists
        transform = projection_page.get_current_transform()
        print(f"✓ Transform state: scale={transform.scale}%, rotation={transform.rotation}°")
        
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
    """Validate event data structures for projection setup."""
    print("\n=== Validating HMI-02 Event Structures ===")
    
    try:
        from core.events import ProjectionConfigUpdated, ProjectionClientConnected, ProjectionClientDisconnected
        import time
        
        # Create ProjectionConfigUpdated event
        config_event = ProjectionConfigUpdated(
            width=2560,
            height=1440
        )
        print(f"✓ ProjectionConfigUpdated event created: {config_event.width}×{config_event.height}")
        
        # Create ProjectionClientConnected event
        connect_event = ProjectionClientConnected(
            client_address="192.168.1.100"
        )
        print(f"✓ ProjectionClientConnected event created: {connect_event.client_address}")
        
        # Create ProjectionClientDisconnected event
        disconnect_event = ProjectionClientDisconnected(
            reason="network_timeout"
        )
        print(f"✓ ProjectionClientDisconnected event created: {disconnect_event.reason}")
        
        return True
        
    except Exception as e:
        print(f"✗ Event validation failed: {e}")
        traceback.print_exc()
        return False

def validate_mathematical_functions():
    """Validate mathematical calculation functions."""
    print("\n=== Validating Mathematical Calculations ===")
    
    try:
        from gui.eda_main_gui import PixelPerfectProjectionSetupPage
        from services.gui_service import GUIService
        from core.event_broker import EventBroker
        
        # Create minimal setup
        event_broker = EventBroker(max_workers=1, max_queue_size=10)
        gui_service = GUIService(event_broker)
        projection_page = PixelPerfectProjectionSetupPage(gui_service)
        
        # Test scale calculation
        scale_factor = projection_page.calculate_scale_factor(120)
        assert abs(scale_factor - 1.2) < 0.001
        print(f"✓ Scale calculation: 120% = {scale_factor}")
        
        # Test rotation matrix calculation
        rotation_matrix = projection_page.calculate_rotation_matrix(90)
        print(f"✓ Rotation matrix calculation: 90° rotation matrix created")
        
        # Test normalized offset calculation
        normalized_offset = projection_page.calculate_normalized_offset((100, 50), (1920, 1080))
        expected_x = 100.0 / 1920.0
        expected_y = 50.0 / 1080.0
        assert abs(normalized_offset[0] - expected_x) < 0.001
        assert abs(normalized_offset[1] - expected_y) < 0.001
        print(f"✓ Normalized offset calculation: (100, 50) -> {normalized_offset}")
        
        # Test keystone transform calculation
        original_corners = [(0, 0), (1920, 0), (1920, 1080), (0, 1080)]
        adjusted_corners = [(10, 5), (1910, 8), (1915, 1075), (5, 1082)]
        transform_matrix = projection_page.calculate_keystone_transform(original_corners, adjusted_corners)
        assert transform_matrix is not None
        assert len(transform_matrix) == 3
        print("✓ Keystone transform calculation successful")
        
        # Clean up
        gui_service.stop()
        event_broker.shutdown()
        
        return True
        
    except Exception as e:
        print(f"✗ Mathematical validation failed: {e}")
        traceback.print_exc()
        return False

def validate_ui_components():
    """Validate UI component structure."""
    print("\n=== Validating HMI-02 UI Components ===")
    
    try:
        from gui.eda_main_gui import PixelPerfectProjectionSetupPage
        from services.gui_service import GUIService
        from core.event_broker import EventBroker
        
        print("✓ All UI-related imports successful")
        
        # Check that the class has required methods for HMI-02
        required_methods = [
            'create_page_content',
            'handle_projection_config_updated',
            'handle_projection_client_connected', 
            'handle_projection_client_disconnected',
            'calculate_scale_factor',
            'calculate_rotation_matrix',
            'calculate_normalized_offset',
            'calculate_keystone_transform',
            'get_current_transform'
        ]
        
        for method in required_methods:
            if hasattr(PixelPerfectProjectionSetupPage, method):
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
    """Run all HMI-02 validations."""
    print("HMI-02 Projection Setup Implementation Validation")
    print("=" * 50)
    
    results = []
    
    # Run validations
    results.append(("Imports", validate_imports()))
    results.append(("Event Structures", validate_event_handling()))
    results.append(("Mathematical Functions", validate_mathematical_functions()))
    results.append(("UI Components", validate_ui_components()))
    results.append(("Instantiation", validate_instantiation()))
    
    # Print summary
    print("\n" + "=" * 50)
    print("HMI-02 VALIDATION SUMMARY")
    print("=" * 50)
    
    all_passed = True
    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{test_name:<25} {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 ALL HMI-02 VALIDATIONS PASSED")
        print("Projection Setup implementation is ready for testing!")
        return 0
    else:
        print("❌ SOME VALIDATIONS FAILED")
        print("Please fix the issues above before proceeding.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 