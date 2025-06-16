import argparse


def _parse_args():
    p = argparse.ArgumentParser(description="Launch BBAN Tracker GUI")
    p.add_argument("--dev", action="store_true", help="Use webcam (development mode) instead of RealSense")
    p.add_argument("--src", type=int, default=0, help="Camera index when --dev is supplied (default 0)")
    p.add_argument("--unity-path", type=str, help="Path to Unity executable for projection client")
    p.add_argument("--console-mode", action="store_true", help="Run in console mode instead of GUI mode")
    return p.parse_args()


if __name__ == "__main__":
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
        import sys
        sys.exit(1) 