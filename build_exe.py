"""
Build script to compile TrackGuardApp into a standalone .exe
"""
import os
import subprocess
import sys
from pathlib import Path

def build():
    print("Building TrackGuard Desktop App...")
    
    project_root = Path(__file__).parent.resolve()
    launcher_path = project_root / "TrackGuardApp.pyw"
    
    # We use PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "tracker",
        "--noconsole",
        "--onefile",
        "--clean",
        str(launcher_path)
    ]
    
    result = subprocess.run(cmd, cwd=str(project_root))
    
    if result.returncode == 0:
        print("\n✅ Build successful! The desktop app is located in the 'dist' folder.")
    else:
        print("\n❌ Build failed.")

if __name__ == "__main__":
    build()
