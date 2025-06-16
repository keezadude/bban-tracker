"""
Main entry point for running bban-tracker as a module.

This allows the application to be run with:
    python -m bban-tracker --dev
    
Which resolves relative import issues that occur when running run_gui.py directly.
"""

import sys
from pathlib import Path

# Add the current directory to Python path to enable imports
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Import and run the main application
from run_gui import _parse_args, main

if __name__ == "__main__":
    # Parse arguments and run the application
    args = _parse_args()
    
    # Import and use the EDA-based main application
    from main_eda import BBanTrackerApplication
    
    # Create configuration from command line arguments
    config = {
        'dev_mode': args.dev,
        'cam_src': args.src,
        'unity_path': args.unity_path
    }
    
    print(f"🚀 BBAN-Tracker Event-Driven Architecture")
    print(f"Configuration: {config}")
    
    # Create and run EDA application
    app = BBanTrackerApplication(config)
    
    if app.initialize():
        # Determine run mode (GUI by default, console if specified)
        gui_mode = not args.console_mode
        print(f"[BBanTracker] Run mode: {'GUI' if gui_mode else 'Console'}")
        
        # Run application
        app.run(gui_mode=gui_mode)
    else:
        print("[BBanTracker] ❌ Application initialization failed")
        sys.exit(1) 