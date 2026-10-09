"""Build the TrackGuard desktop launcher and reusable Windows agent app."""
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4


def build_executable(
    project_root: Path,
    name: str,
    entry_point: Path,
    extra_args: Sequence[str] = (),
) -> bool:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--name",
        name,
        "--noconsole",
        "--onefile",
        "--clean",
        "--distpath",
        str(project_root / "dist"),
        "--workpath",
        str(project_root / "build" / f"pyinstaller-{name}-{uuid4().hex[:8]}"),
        "--specpath",
        str(project_root / "build"),
        *extra_args,
        str(entry_point),
    ]
    result = subprocess.run(command, cwd=str(project_root), capture_output=True, text=True)
    if result.returncode != 0:
        print((result.stderr or result.stdout or f"PyInstaller exited with status {result.returncode}")[-4000:])
        return False
    return True


def build() -> bool:
    project_root = Path(__file__).parent.resolve()
    agent_dir = project_root / "agent"
    setup_script = project_root / "installer" / "TrackGuardSetup.pyw"

    print("Building TrackGuard desktop launcher...")
    if not build_executable(project_root, "tracker", project_root / "TrackGuardApp.pyw"):
        print("TrackGuard desktop launcher build failed.")
        return False

    print("Building reusable TrackGuard device app...")
    setup_args = [
        "--paths",
        str(agent_dir),
        "--add-data",
        f"{agent_dir};agent",
        "--hidden-import",
        "websockets",
        "--hidden-import",
        "httpx",
        "--hidden-import",
        "psutil",
    ]
    if not build_executable(project_root, "TrackGuardSetup", setup_script, setup_args):
        print("TrackGuard device app build failed.")
        return False

    print("\nBuild successful. See dist\\tracker.exe and dist\\TrackGuardSetup.exe.")
    return True

if __name__ == "__main__":
    raise SystemExit(0 if build() else 1)
