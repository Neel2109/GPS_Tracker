"""
Create a Desktop shortcut for TrackGuard.
Run once: python create_shortcut.py
"""
import os
import sys
from pathlib import Path

def create_shortcut():
    """Create a Windows Desktop shortcut (.lnk) for TrackGuard."""
    # Use PowerShell — works on all Windows without extra packages
    _create_shortcut_powershell()


def _create_shortcut_powershell():
    """Create shortcut using PowerShell (no extra dependencies needed)."""
    import subprocess
    
    project_root = Path(__file__).resolve().parent
    
    # Get actual Desktop path (handles OneDrive redirection)
    desktop_result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True, text=True
    )
    if desktop_result.returncode == 0 and desktop_result.stdout.strip():
        desktop = Path(desktop_result.stdout.strip())
    else:
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    
    desktop.mkdir(parents=True, exist_ok=True)
    shortcut_path = str(desktop / "TrackGuard.lnk")
    
    # Find pythonw
    venv_names = [".venv312", ".venv"]
    pythonw = None
    for venv in venv_names:
        candidate = project_root / venv / "Scripts" / "pythonw.exe"
        if candidate.exists():
            pythonw = str(candidate)
            break
    
    if not pythonw:
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    
    launcher = str(project_root / "TrackGuardApp.pyw")
    working_dir = str(project_root)
    
    # Escape backslashes for PowerShell
    ps_script = (
        '$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut("{shortcut_path}"); '
        f'$s.TargetPath = "{pythonw}"; '
        f'$s.Arguments = \'"{launcher}"\'; '
        f'$s.WorkingDirectory = "{working_dir}"; '
        '$s.Description = "TrackGuard - GPS Device Tracking"; '
        '$s.Save()'
    )
    
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        print(f"[OK] Desktop shortcut created: {shortcut_path}")
    else:
        print(f"[ERROR] Failed to create shortcut: {result.stderr}")


if __name__ == "__main__":
    create_shortcut()
