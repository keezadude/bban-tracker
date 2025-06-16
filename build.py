#!/usr/bin/env python3
"""
BBAN-Tracker Build System - Production Deployment Package Generator

This script creates a standalone, distributable executable of the BBAN-Tracker
application using PyInstaller. It handles dependency bundling, configuration
management, and creates both portable and installer versions.

Usage:
    python build.py [--debug] [--onefile] [--clean]
    
Features:
- Bundles all Python dependencies
- Includes Qt/PySide6 plugins and translations
- Packages RealSense libraries (if available)
- Creates default configuration files
- Generates both directory and single-file distributions
- Supports debug builds for troubleshooting
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Any
import json


class BBanTrackerBuilder:
    """
    Comprehensive build system for BBAN-Tracker application.
    
    Handles the complete build pipeline from source to distributable executable,
    including dependency resolution, asset bundling, and configuration setup.
    """
    
    def __init__(self, debug: bool = False, onefile: bool = False, clean: bool = False):
        self.debug = debug
        self.onefile = onefile
        self.clean = clean
        
        # Build paths
        self.project_root = Path(__file__).parent
        self.build_dir = self.project_root / "build"
        self.dist_dir = self.project_root / "dist"
        self.spec_file = self.project_root / "bban_tracker.spec"
        
        # Application metadata
        self.app_name = "BBAN-Tracker"
        self.app_version = "2.1.0"
        self.app_description = "Body Ball Action Network - Enhanced Tracking System"
        self.app_author = "BBAN Development Team"
        
        print(f"🔧 BBAN-Tracker Build System v{self.app_version}")
        print(f"📁 Project root: {self.project_root}")
        print(f"🎯 Build mode: {'Debug' if debug else 'Release'}")
        print(f"📦 Package type: {'Single file' if onefile else 'Directory'}")
    
    def verify_environment(self) -> bool:
        """
        Verify that the build environment is properly set up.
        
        Returns:
            True if environment is ready, False otherwise
        """
        print("\n🔍 Verifying build environment...")
        
        # Check Python version
        if sys.version_info < (3, 11):
            print("❌ Python 3.11+ required")
            return False
        print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
        
        # Check PyInstaller
        try:
            import PyInstaller
            print(f"✅ PyInstaller {PyInstaller.__version__}")
        except ImportError:
            print("❌ PyInstaller not found. Install with: pip install pyinstaller")
            return False
        
        # Check core dependencies
        required_packages = [
            "PySide6", "numpy", "opencv-contrib-python", "pyrealsense2"
        ]
        
        for package in required_packages:
            try:
                __import__(package.replace("-", "_"))
                print(f"✅ {package}")
            except ImportError:
                print(f"❌ {package} not found")
                return False
        
        # Check entry point
        main_script = self.project_root / "run_gui.py"
        if not main_script.exists():
            print(f"❌ Main script not found: {main_script}")
            return False
        print(f"✅ Entry point: {main_script}")
        
        return True
    
    def clean_build_dirs(self) -> None:
        """Clean previous build artifacts."""
        print("\n🧹 Cleaning build directories...")
        
        dirs_to_clean = [self.build_dir, self.dist_dir]
        
        for dir_path in dirs_to_clean:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"  🗑️  Removed {dir_path}")
        
        if self.spec_file.exists():
            self.spec_file.unlink()
            print(f"  🗑️  Removed {self.spec_file}")
    
    def generate_pyinstaller_spec(self) -> Path:
        """
        Generate PyInstaller spec file with comprehensive configuration.
        
        Returns:
            Path to generated spec file
        """
        print("\n📝 Generating PyInstaller spec file...")
        
        # Determine data files and hidden imports
        datas, hidden_imports = self._get_build_dependencies()
        
        # Create spec file content
        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Build configuration
project_root = Path(r"{self.project_root}")
debug = {self.debug}
onefile = {self.onefile}

# Data files and directories
datas = {datas}

# Hidden imports for dynamic loading
hiddenimports = {hidden_imports}

# PyInstaller Analysis
a = Analysis(
    [str(project_root / "run_gui.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
    optimize=0 if debug else 2,
)

# Remove duplicate entries
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

if onefile:
    # Single file executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="{self.app_name}",
        debug=debug,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=debug,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(project_root / "resources" / "icon.ico") if (project_root / "resources" / "icon.ico").exists() else None,
        version_info={{
            "version": "{self.app_version}",
            "description": "{self.app_description}",
            "company": "{self.app_author}",
            "product": "{self.app_name}",
        }}
    )
else:
    # Directory distribution
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="{self.app_name}",
        debug=debug,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=debug,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(project_root / "resources" / "icon.ico") if (project_root / "resources" / "icon.ico").exists() else None,
    )
    
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="{self.app_name}",
    )
'''
        
        # Write spec file
        with open(self.spec_file, 'w') as f:
            f.write(spec_content)
        
        print(f"✅ Generated spec file: {self.spec_file}")
        return self.spec_file
    
    def _get_build_dependencies(self) -> tuple[List[tuple], List[str]]:
        """
        Determine data files and hidden imports needed for the build.
        
        Returns:
            Tuple of (datas, hiddenimports)
        """
        datas = []
        hidden_imports = []
        
        # Configuration files
        config_files = [
            "requirements.txt",
            "README.md"
        ]
        
        for config_file in config_files:
            config_path = self.project_root / config_file
            if config_path.exists():
                datas.append((str(config_path), "."))
        
        # GUI resources
        gui_resources = self.project_root / "gui" / "resources"
        if gui_resources.exists():
            datas.append((str(gui_resources), "gui/resources"))
        
        # Create default configuration directory
        config_dir = self.project_root / "config"
        config_dir.mkdir(exist_ok=True)
        
        # Generate default configuration files
        self._create_default_configs(config_dir)
        datas.append((str(config_dir), "config"))
        
        # Hidden imports for dynamic modules
        hidden_imports.extend([
            "PySide6.QtCore",
            "PySide6.QtWidgets", 
            "PySide6.QtGui",
            "numpy",
            "cv2",
            "pyrealsense2",
            "threading",
            "multiprocessing",
            "queue",
            "json",
            "pickle",
            "socket",
            "struct",
            "time",
            "pathlib",
            "dataclasses",
            "enum",
            "typing"
        ])
        
        # Platform-specific imports
        if sys.platform == "win32":
            hidden_imports.extend([
                "win32api",
                "win32con", 
                "win32gui",
                "winsound"
            ])
        
        return datas, hidden_imports
    
    def _create_default_configs(self, config_dir: Path) -> None:
        """
        Create default configuration files for deployment.
        
        Args:
            config_dir: Directory to create config files in
        """
        print("📋 Creating default configuration files...")
        
        # Default application configuration
        app_config = {
            "application": {
                "name": self.app_name,
                "version": self.app_version,
                "debug_mode": False
            },
            "camera": {
                "type": "realsense",
                "resolution": [1280, 720],
                "fps": 30
            },
            "tracking": {
                "threshold": 15,
                "min_area": 100,
                "max_area": 2500,
                "adaptive_threshold": True
            },
            "projection": {
                "unity_host": "127.0.0.1",
                "unity_udp_port": 50007,
                "unity_tcp_port": 50008,
                "auto_connect": True
            },
            "performance": {
                "target_fps": 30,
                "enable_batching": True,
                "batch_size": 10,
                "max_queue_size": 10000
            }
        }
        
        with open(config_dir / "default_config.json", 'w') as f:
            json.dump(app_config, f, indent=2)
        
        # Network configuration for different deployment scenarios
        localhost_config = {
            "mode": "localhost",
            "description": "Local development and testing",
            "unity_executable": "",
            "auto_launch_unity": False
        }
        
        with open(config_dir / "localhost_config.json", 'w') as f:
            json.dump(localhost_config, f, indent=2)
        
        networked_config = {
            "mode": "networked", 
            "description": "Networked deployment with remote Unity client",
            "unity_host": "192.168.1.100",
            "unity_udp_port": 50007,
            "unity_tcp_port": 50008,
            "connection_timeout": 5000
        }
        
        with open(config_dir / "networked_config.json", 'w') as f:
            json.dump(networked_config, f, indent=2)
        
        # Launcher configuration
        launcher_config = {
            "window_title": f"{self.app_name} v{self.app_version}",
            "window_size": [1200, 800],
            "theme": "dark",
            "auto_start_tracking": False,
            "show_advanced_settings": False
        }
        
        with open(config_dir / "launcher_config.json", 'w') as f:
            json.dump(launcher_config, f, indent=2)
        
        print(f"  ✅ Created configuration files in {config_dir}")
    
    def run_pyinstaller(self) -> bool:
        """
        Execute PyInstaller with the generated spec file.
        
        Returns:
            True if build successful, False otherwise
        """
        print("\n🚀 Running PyInstaller...")
        
        cmd = [
            sys.executable, "-m", "PyInstaller",
            str(self.spec_file),
            "--clean",
            "--noconfirm"
        ]
        
        if self.debug:
            cmd.append("--debug=all")
        
        print(f"📋 Command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("✅ PyInstaller completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ PyInstaller failed with return code {e.returncode}")
            print(f"STDOUT: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            return False
    
    def post_build_setup(self) -> None:
        """Perform post-build setup and validation."""
        print("\n🔧 Post-build setup...")
        
        # Find the built application
        if self.onefile:
            app_path = self.dist_dir / f"{self.app_name}.exe"
        else:
            app_path = self.dist_dir / self.app_name / f"{self.app_name}.exe"
        
        if not app_path.exists():
            print(f"❌ Built application not found: {app_path}")
            return
        
        print(f"✅ Built application: {app_path}")
        
        # Create launcher scripts
        self._create_launcher_scripts()
        
        # Copy documentation
        self._copy_documentation()
        
        # Create installer (if tools available)
        self._create_installer()
        
        print(f"✅ Build completed successfully!")
        print(f"📦 Distribution directory: {self.dist_dir}")
    
    def _create_launcher_scripts(self) -> None:
        """Create convenient launcher scripts."""
        print("📝 Creating launcher scripts...")
        
        # Windows batch file
        batch_content = f'''@echo off
title {self.app_name} v{self.app_version}
echo.
echo {self.app_name} v{self.app_version}
echo {self.app_description}
echo.
echo Starting application...
echo.

REM Check for configuration
if not exist "config\\default_config.json" (
    echo WARNING: Default configuration not found
    echo Using built-in defaults
    echo.
)

REM Launch application
if exist "{self.app_name}.exe" (
    "{self.app_name}.exe" %*
) else (
    echo ERROR: Application executable not found
    pause
    exit /b 1
)

REM Handle exit codes
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%
    pause
)
'''
        
        batch_file = self.dist_dir / "launch.bat"
        with open(batch_file, 'w') as f:
            f.write(batch_content)
        
        print(f"  ✅ Created {batch_file}")
        
        # Development mode launcher
        dev_batch_content = f'''@echo off
title {self.app_name} v{self.app_version} - Development Mode
echo.
echo {self.app_name} v{self.app_version} - Development Mode
echo.

REM Launch with webcam for development
if exist "{self.app_name}.exe" (
    "{self.app_name}.exe" --dev --src 0
) else (
    echo ERROR: Application executable not found
    pause
    exit /b 1
)

pause
'''
        
        dev_batch_file = self.dist_dir / "launch_dev.bat"
        with open(dev_batch_file, 'w') as f:
            f.write(dev_batch_content)
        
        print(f"  ✅ Created {dev_batch_file}")
    
    def _copy_documentation(self) -> None:
        """Copy documentation files to distribution."""
        print("📚 Copying documentation...")
        
        doc_files = [
            "README.md",
            "requirements.txt"
        ]
        
        for doc_file in doc_files:
            src_path = self.project_root / doc_file
            if src_path.exists():
                dst_path = self.dist_dir / doc_file
                shutil.copy2(src_path, dst_path)
                print(f"  ✅ Copied {doc_file}")
        
        # Create deployment guide
        deployment_guide = f'''# {self.app_name} v{self.app_version} - Deployment Guide

## System Requirements
- Windows 10/11 (64-bit)
- Minimum 4GB RAM
- USB 3.0 port (for RealSense camera)
- Network connection (for Unity client)

## Installation
1. Extract all files to desired location
2. Run `launch.bat` to start the application
3. For development/testing: use `launch_dev.bat`

## Configuration
- Default settings: `config/default_config.json`
- Localhost setup: `config/localhost_config.json`  
- Networked setup: `config/networked_config.json`

## Troubleshooting
- Check Windows Event Viewer for system errors
- Verify camera connections and drivers
- Ensure Unity client is accessible on network
- Review application logs for detailed error information

## Support
For technical support, contact the BBAN Development Team.

Build Date: {self._get_build_timestamp()}
Version: {self.app_version}
'''
        
        with open(self.dist_dir / "DEPLOYMENT_GUIDE.txt", 'w') as f:
            f.write(deployment_guide)
        
        print(f"  ✅ Created deployment guide")
    
    def _create_installer(self) -> None:
        """Create Windows installer (if NSIS is available)."""
        print("📦 Creating installer...")
        
        # Check for NSIS
        nsis_executable = shutil.which("makensis")
        if not nsis_executable:
            print("  ⚠️  NSIS not found - skipping installer creation")
            print("  💡 Install NSIS to create Windows installer")
            return
        
        # TODO: Create NSIS script and generate installer
        print("  ⚠️  NSIS installer creation not yet implemented")
    
    def _get_build_timestamp(self) -> str:
        """Get current build timestamp."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def build(self) -> bool:
        """
        Execute the complete build process.
        
        Returns:
            True if build successful, False otherwise
        """
        try:
            # Environment verification
            if not self.verify_environment():
                return False
            
            # Clean previous builds
            if self.clean:
                self.clean_build_dirs()
            
            # Generate PyInstaller spec
            self.generate_pyinstaller_spec()
            
            # Run PyInstaller
            if not self.run_pyinstaller():
                return False
            
            # Post-build setup
            self.post_build_setup()
            
            return True
            
        except Exception as e:
            print(f"❌ Build failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point for the build script."""
    parser = argparse.ArgumentParser(description="BBAN-Tracker Build System")
    parser.add_argument("--debug", action="store_true", help="Create debug build")
    parser.add_argument("--onefile", action="store_true", help="Create single-file executable")
    parser.add_argument("--clean", action="store_true", help="Clean build directories first")
    
    args = parser.parse_args()
    
    builder = BBanTrackerBuilder(
        debug=args.debug,
        onefile=args.onefile,
        clean=args.clean
    )
    
    success = builder.build()
    
    if success:
        print("\n🎉 Build completed successfully!")
        print(f"📍 Find your application in: {builder.dist_dir}")
        sys.exit(0)
    else:
        print("\n💥 Build failed!")
        sys.exit(1)


if __name__ == "__main__":
    main() 