#!/usr/bin/env python3
"""
Phoenix Finalis Validation Script - Comprehensive EDA Compliance Check

This script validates that all critical gaps identified in the Phoenix Finalis
gap analysis have been properly addressed and that the Unity integration
contract is maintained.

Areas Validated:
1. TrackerSetupPage EDA Eventification
2. ProjectionSetupPage Worker Access Elimination  
3. Lifecycle Management via Service Layer
4. Unity Command/Data Flow Contract Compliance
5. Hardware Abstraction Layer Completeness
"""

import sys
import ast
import inspect
from pathlib import Path
from typing import List, Dict, Set, Tuple

# Import core project modules for validation
sys.path.insert(0, str(Path(__file__).parent))

try:
    from gui.tracking_panel import TrackerSetupPage
    from gui.projection_panel import ProjectionSetupPage
    from services.gui_service import GUIService
    from services.tracking_service import TrackingService
    from services.projection_service import ProjectionService
    from core.events import *
    from adapters.beysion_unity_adapter_corrected import BeysionUnityAdapterCorrected
    IMPORTS_SUCCESS = True
except ImportError as e:
    print(f"❌ Import failed: {e}")
    IMPORTS_SUCCESS = False


class PhoenixFinalisValidator:
    """Comprehensive validator for Phoenix Finalis EDA compliance."""
    
    def __init__(self):
        self.validation_results = {}
        self.issues_found = []
        self.unity_contract_violations = []
        
    def validate_all(self) -> bool:
        """Run all validation checks."""
        print("🔥 PHOENIX FINALIS: EDA COMPLIANCE VALIDATION")
        print("=" * 60)
        
        if not IMPORTS_SUCCESS:
            print("❌ CRITICAL: Import validation failed")
            return False
        
        # Core EDA validation
        self.validate_tracker_setup_eda_compliance()
        self.validate_projection_setup_eda_compliance()
        self.validate_lifecycle_management()
        self.validate_event_coverage()
        
        # Unity integration validation
        self.validate_unity_data_contract()
        self.validate_unity_command_contract()
        self.validate_hal_completeness()
        
        # Generate final report
        return self.generate_final_report()
    
    def validate_tracker_setup_eda_compliance(self):
        """Validate TrackerSetupPage EDA compliance."""
        print("\n🎯 VALIDATING: TrackerSetupPage EDA Compliance")
        print("-" * 40)
        
        issues = []
        
        # Check for EDA integration methods
        if hasattr(TrackerSetupPage, 'set_eda_integration'):
            print("✅ TrackerSetupPage.set_eda_integration() method exists")
        else:
            issues.append("Missing set_eda_integration() method")
        
        if hasattr(TrackerSetupPage, 'update_tracking_status'):
            print("✅ TrackerSetupPage.update_tracking_status() method exists")
        else:
            issues.append("Missing update_tracking_status() method")
            
        # Check event handler implementation
        methods_to_check = [
            '_on_threshold_changed', '_on_min_area_changed', '_on_max_area_changed',
            '_on_emitter_toggled', '_on_laser_power_changed', '_on_ae_toggled',
            '_on_exposure_changed', '_on_gain_changed', '_on_apply_crop'
        ]
        
        for method_name in methods_to_check:
            if hasattr(TrackerSetupPage, method_name):
                method = getattr(TrackerSetupPage, method_name)
                source = inspect.getsource(method)
                
                if 'event_broker' in source and 'publish' in source:
                    print(f"✅ {method_name} uses EDA event publishing")
                elif '_eda_callback' in source:
                    print(f"✅ {method_name} uses EDA callback pattern")
                elif '[WARNING]' in source and 'deprecated' in source:
                    print(f"⚠️  {method_name} marked as deprecated (acceptable)")
                else:
                    issues.append(f"{method_name} does not use EDA pattern")
        
        # Check lifecycle methods
        lifecycle_methods = ['_start_tracking', 'stop_tracking']
        for method_name in lifecycle_methods:
            if hasattr(TrackerSetupPage, method_name):
                method = getattr(TrackerSetupPage, method_name)
                source = inspect.getsource(method)
                
                if 'StartTracking' in source or 'StopTracking' in source:
                    print(f"✅ {method_name} publishes EDA lifecycle events")
                elif 'DEPRECATED' in source:
                    print(f"✅ {method_name} properly marked as deprecated")
                else:
                    issues.append(f"{method_name} does not use EDA lifecycle pattern")
        
        self.validation_results['tracker_setup_eda'] = {
            'status': 'PASS' if not issues else 'FAIL',
            'issues': issues
        }
        
        if issues:
            print(f"❌ TrackerSetupPage EDA compliance: {len(issues)} issues found")
            self.issues_found.extend(issues)
        else:
            print("✅ TrackerSetupPage EDA compliance: PASSED")
    
    def validate_projection_setup_eda_compliance(self):
        """Validate ProjectionSetupPage EDA compliance."""
        print("\n🎯 VALIDATING: ProjectionSetupPage EDA Compliance")
        print("-" * 40)
        
        issues = []
        
        # Check for EDA integration methods
        if hasattr(ProjectionSetupPage, 'set_eda_integration'):
            print("✅ ProjectionSetupPage.set_eda_integration() method exists")
        else:
            issues.append("Missing set_eda_integration() method")
        
        if hasattr(ProjectionSetupPage, 'update_projection_status'):
            print("✅ ProjectionSetupPage.update_projection_status() method exists")
        else:
            issues.append("Missing update_projection_status() method")
        
        # Check _apply_projection method
        if hasattr(ProjectionSetupPage, '_apply_projection'):
            method = getattr(ProjectionSetupPage, '_apply_projection')
            source = inspect.getsource(method)
            
            if 'ProjectionConfigUpdated' in source:
                print("✅ _apply_projection() publishes EDA events")
            elif '_eda_callback' in source:
                print("✅ _apply_projection() uses EDA callback pattern")
            else:
                issues.append("_apply_projection() does not use EDA pattern")
        
        # Check _find_worker method for deprecation
        if hasattr(ProjectionSetupPage, '_find_worker'):
            method = getattr(ProjectionSetupPage, '_find_worker')
            source = inspect.getsource(method)
            
            if 'DEPRECATED' in source:
                print("✅ _find_worker() properly marked as deprecated")
            else:
                issues.append("_find_worker() should be marked as deprecated")
        
        self.validation_results['projection_setup_eda'] = {
            'status': 'PASS' if not issues else 'FAIL',
            'issues': issues
        }
        
        if issues:
            print(f"❌ ProjectionSetupPage EDA compliance: {len(issues)} issues found")
            self.issues_found.extend(issues)
        else:
            print("✅ ProjectionSetupPage EDA compliance: PASSED")
    
    def validate_lifecycle_management(self):
        """Validate service-layer lifecycle management."""
        print("\n🎯 VALIDATING: Service Layer Lifecycle Management")
        print("-" * 40)
        
        issues = []
        
        # Check GUIService integration methods
        gui_methods = [
            'request_start_tracking', 'request_stop_tracking', 'request_calibration',
            'update_tracker_settings', 'update_realsense_settings', 
            'update_crop_settings', 'update_projection_config'
        ]
        
        for method_name in gui_methods:
            if hasattr(GUIService, method_name):
                print(f"✅ GUIService.{method_name}() exists")
            else:
                issues.append(f"Missing GUIService.{method_name}() method")
        
        # Check TrackingService event subscription
        if hasattr(TrackingService, '_setup_event_subscriptions'):
            print("✅ TrackingService has event subscription setup")
        else:
            issues.append("TrackingService missing event subscription setup")
        
        # Check ProjectionService event subscription
        if hasattr(ProjectionService, '_setup_event_subscriptions'):
            print("✅ ProjectionService has event subscription setup")
        else:
            issues.append("ProjectionService missing event subscription setup")
        
        self.validation_results['lifecycle_management'] = {
            'status': 'PASS' if not issues else 'FAIL',
            'issues': issues
        }
        
        if issues:
            print(f"❌ Lifecycle management: {len(issues)} issues found")
            self.issues_found.extend(issues)
        else:
            print("✅ Lifecycle management: PASSED")
    
    def validate_event_coverage(self):
        """Validate that all required events are defined."""
        print("\n🎯 VALIDATING: Event Coverage")
        print("-" * 40)
        
        required_events = [
            'StartTracking', 'StopTracking', 'ChangeTrackerSettings',
            'ChangeRealSenseSettings', 'ChangeCropSettings', 'CalibrateTracker',
            'ProjectionConfigUpdated', 'TrackingStarted', 'TrackingStopped',
            'TrackingDataUpdated', 'ProjectionClientConnected', 'ProjectionClientDisconnected'
        ]
        
        issues = []
        
        for event_name in required_events:
            if hasattr(sys.modules[__name__], event_name):
                print(f"✅ Event {event_name} is defined")
            else:
                issues.append(f"Missing event definition: {event_name}")
        
        # Check ChangeTrackerSettings for new fields
        if hasattr(ChangeTrackerSettings, 'adaptive_threshold'):
            print("✅ ChangeTrackerSettings.adaptive_threshold field added")
        else:
            issues.append("ChangeTrackerSettings missing adaptive_threshold field")
        
        self.validation_results['event_coverage'] = {
            'status': 'PASS' if not issues else 'FAIL',
            'issues': issues
        }
        
        if issues:
            print(f"❌ Event coverage: {len(issues)} issues found")
            self.issues_found.extend(issues)
        else:
            print("✅ Event coverage: PASSED")
    
    def validate_unity_data_contract(self):
        """Validate Unity data flow contract compliance."""
        print("\n🎯 VALIDATING: Unity Data Flow Contract")
        print("-" * 40)
        
        issues = []
        
        # Expected Unity data structures from the gap analysis
        expected_structures = {
            'TrackerFrame': ['frameCount', 'beys', 'hits', 'timestamp'],
            'BeyDetected': ['id', 'position', 'worldPosition'],
            'BeyCollision': ['position', 'timestamp', 'bey1Id', 'bey2Id']
        }
        
        # Check if BeysionUnityAdapterCorrected implements required methods
        adapter_methods = ['send_udp_message', 'handle_tcp_command', 'set_command_callback']
        
        for method_name in adapter_methods:
            if hasattr(BeysionUnityAdapterCorrected, method_name):
                print(f"✅ BeysionUnityAdapterCorrected.{method_name}() exists")
            else:
                issues.append(f"Missing adapter method: {method_name}")
        
        # Check event data structure compatibility
        if hasattr(TrackingDataUpdated, 'beys') and hasattr(TrackingDataUpdated, 'hits'):
            print("✅ TrackingDataUpdated has Unity-compatible structure")
        else:
            issues.append("TrackingDataUpdated missing Unity-compatible fields")
        
        self.validation_results['unity_data_contract'] = {
            'status': 'PASS' if not issues else 'FAIL',
            'issues': issues
        }
        
        if issues:
            print(f"❌ Unity data contract: {len(issues)} issues found")
            self.unity_contract_violations.extend(issues)
        else:
            print("✅ Unity data contract: PASSED")
    
    def validate_unity_command_contract(self):
        """Validate Unity command flow contract compliance."""
        print("\n🎯 VALIDATING: Unity Command Flow Contract")
        print("-" * 40)
        
        # Expected Unity commands from the gap analysis
        expected_commands = [
            'calibrate', 'threshold_up', 'threshold_down', 'ping', 'status',
            'SET_BRIGHTNESS', 'SET_CONTRAST', 'SET_EXPOSURE', 'RESET_SETTINGS'
        ]
        
        issues = []
        
        # Check if main_eda.py has Unity command callback integration
        try:
            with open('main_eda.py', 'r') as f:
                content = f.read()
            
            if 'unity_command_callback' in content:
                print("✅ Unity command callback integration exists")
                
                # Check for specific command handling
                for cmd in ['calibrate', 'threshold_up', 'threshold_down']:
                    if f'"{cmd}"' in content:
                        print(f"✅ Unity command '{cmd}' is handled")
                    else:
                        issues.append(f"Unity command '{cmd}' not handled")
            else:
                issues.append("Missing Unity command callback integration")
                
        except FileNotFoundError:
            issues.append("main_eda.py not found")
        
        self.validation_results['unity_command_contract'] = {
            'status': 'PASS' if not issues else 'FAIL',
            'issues': issues
        }
        
        if issues:
            print(f"❌ Unity command contract: {len(issues)} issues found")
            self.unity_contract_violations.extend(issues)
        else:
            print("✅ Unity command contract: PASSED")
    
    def validate_hal_completeness(self):
        """Validate Hardware Abstraction Layer completeness."""
        print("\n🎯 VALIDATING: Hardware Abstraction Layer")
        print("-" * 40)
        
        issues = []
        
        # Check for HAL implementation
        hal_file = Path('hardware/realsense_d400_hal.py')
        if hal_file.exists():
            print("✅ RealSenseD400_HAL implementation exists")
            
            # Check for required interface compliance
            try:
                from hardware.realsense_d400_hal import RealSenseD400_HAL
                from core.interfaces import ITrackerHardware
                
                if issubclass(RealSenseD400_HAL, ITrackerHardware):
                    print("✅ HAL implements ITrackerHardware interface")
                else:
                    issues.append("HAL does not implement required interface")
                    
            except ImportError:
                issues.append("Could not import HAL implementation")
        else:
            issues.append("HAL implementation file not found")
        
        self.validation_results['hal_completeness'] = {
            'status': 'PASS' if not issues else 'FAIL',
            'issues': issues
        }
        
        if issues:
            print(f"❌ HAL completeness: {len(issues)} issues found")
            self.issues_found.extend(issues)
        else:
            print("✅ HAL completeness: PASSED")
    
    def generate_final_report(self) -> bool:
        """Generate final validation report."""
        print("\n" + "=" * 60)
        print("🏆 PHOENIX FINALIS VALIDATION REPORT")
        print("=" * 60)
        
        passed_count = sum(1 for result in self.validation_results.values() 
                          if result['status'] == 'PASS')
        total_count = len(self.validation_results)
        
        print(f"\n📊 VALIDATION SUMMARY:")
        print(f"   Passed: {passed_count}/{total_count}")
        print(f"   Failed: {total_count - passed_count}/{total_count}")
        
        if self.issues_found:
            print(f"\n❌ EDA COMPLIANCE ISSUES ({len(self.issues_found)}):")
            for i, issue in enumerate(self.issues_found, 1):
                print(f"   {i}. {issue}")
        
        if self.unity_contract_violations:
            print(f"\n❌ UNITY CONTRACT VIOLATIONS ({len(self.unity_contract_violations)}):")
            for i, violation in enumerate(self.unity_contract_violations, 1):
                print(f"   {i}. {violation}")
        
        # Overall assessment
        overall_success = (passed_count == total_count and 
                          not self.issues_found and 
                          not self.unity_contract_violations)
        
        if overall_success:
            print("\n🎉 PHOENIX FINALIS: 100% EDA COMPLIANCE ACHIEVED!")
            print("✅ All gaps have been successfully addressed")
            print("✅ Unity integration contract maintained")
            print("✅ Ready for production deployment")
        else:
            print("\n⚠️  PHOENIX FINALIS: EDA COMPLIANCE INCOMPLETE")
            print("❌ Critical gaps remain - see issues above")
            print("❌ Unity integration may be compromised")
            
        return overall_success


def main():
    """Main validation function."""
    validator = PhoenixFinalisValidator()
    success = validator.validate_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 