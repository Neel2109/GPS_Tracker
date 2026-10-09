"""
TrackGuard — All-in-One Windows Launcher
=========================================
Double-click this file to start TrackGuard as a standalone Windows app.
It starts the server, the agent, and opens the dashboard automatically.

No terminal, no localhost commands — just click and go.
"""
import os
import sys
import time
import signal
import subprocess
import threading
import webbrowser
import logging
from pathlib import Path

# ─── Setup Paths ─────────────────────────────────────────────
# Hardcode project root so the .exe works anywhere (like the Desktop)
PROJECT_DIR = r"D:\Neel College\Projects\Laptop GPS Tracking"
if os.path.exists(PROJECT_DIR):
    ROOT = Path(PROJECT_DIR)
else:
    ROOT = Path(__file__).resolve().parent

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Logging to file (no console since .pyw hides it)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "trackguard_launcher.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("TrackGuard.Launcher")

# ─── Find Python ─────────────────────────────────────────────
def find_python() -> str:
    """Find the project's virtual environment Python, or fall back to system Python."""
    venv_names = [".venv312", ".venv"]
    for venv in venv_names:
        python_exe = ROOT / venv / "Scripts" / "python.exe"
        if python_exe.exists():
            return str(python_exe)
    # Fallback to the Python running this script
    return sys.executable


PYTHON = find_python()
logger.info(f"Using Python: {PYTHON}")


# ─── Process Manager ─────────────────────────────────────────
class TrackGuardManager:
    """Manages the server and agent processes as a single unit."""

    def __init__(self):
        self.server_process = None
        self.agent_process = None
        self.running = False
        self.port = 8000

    def start_server(self) -> bool:
        """Start the FastAPI server in the background."""
        logger.info("Starting FastAPI server...")
        try:
            server_log = open(LOG_DIR / "server.log", "w", encoding="utf-8")
            self.server_process = subprocess.Popen(
                [PYTHON, "run.py", "--port", str(self.port)],
                cwd=str(ROOT),
                stdout=server_log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logger.info(f"Server started (PID: {self.server_process.pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False

    def wait_for_server(self, timeout: int = 30) -> bool:
        """Wait until the server's /health endpoint responds."""
        import urllib.request
        import urllib.error

        url = f"http://localhost:{self.port}/health"
        logger.info(f"Waiting for server at {url}...")

        start = time.time()
        while time.time() - start < timeout:
            # Check if server process died
            if self.server_process and self.server_process.poll() is not None:
                logger.error("Server process exited unexpectedly")
                return False

            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        logger.info("Server is healthy and ready!")
                        return True
            except (urllib.error.URLError, ConnectionError, OSError):
                pass

            time.sleep(0.5)

        logger.error(f"Server did not become ready within {timeout}s")
        return False

    def start_agent(self) -> bool:
        """Start the TrackGuard agent in the background."""
        logger.info("Starting TrackGuard agent...")
        try:
            agent_log = open(LOG_DIR / "agent.log", "w", encoding="utf-8")
            self.agent_process = subprocess.Popen(
                [PYTHON, str(ROOT / "agent" / "agent.py")],
                cwd=str(ROOT / "agent"),
                stdout=agent_log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logger.info(f"Agent started (PID: {self.agent_process.pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            return False

    def open_dashboard(self):
        """Open the TrackGuard dashboard natively."""
        url = f"http://localhost:{self.port}"
        logger.info(f"Opening dashboard window: {url}")
        try:
            import webview
            webview.create_window('TrackGuard', url, width=1024, height=768)
            webview.start()
        except ImportError:
            import webbrowser
            logger.info("pywebview not available, falling back to default browser.")
            webbrowser.open(url)

    def stop(self):
        """Stop both the agent and server gracefully."""
        self.running = False
        logger.info("Stopping TrackGuard...")

        for name, proc in [("Agent", self.agent_process), ("Server", self.server_process)]:
            if proc and proc.poll() is None:
                logger.info(f"Terminating {name} (PID: {proc.pid})...")
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                    logger.info(f"{name} stopped.")
                except subprocess.TimeoutExpired:
                    proc.kill()
                    logger.warning(f"{name} killed forcefully.")
                except Exception as e:
                    logger.error(f"Error stopping {name}: {e}")

    def is_alive(self) -> bool:
        """Check if both processes are still running."""
        server_ok = self.server_process and self.server_process.poll() is None
        agent_ok = self.agent_process and self.agent_process.poll() is None
        return server_ok and agent_ok

    def agent_status(self) -> str:
        if self.agent_process is None:
            return "not started"
        if self.agent_process.poll() is None:
            return "running; see agent.log for connection state"
        return "stopped; check agent.log and re-pair if needed"


# ─── System Tray Icon ────────────────────────────────────────
def run_with_tray(manager: TrackGuardManager):
    """
    Run TrackGuard with a system tray icon.
    Falls back to a simple tkinter window if pystray is not available.
    """
    try:
        import pystray
        from PIL import Image, ImageDraw
        _run_pystray(manager, pystray, Image, ImageDraw)
    except ImportError:
        logger.info("pystray/Pillow not available, using tkinter fallback")
        _run_tkinter_fallback(manager)


def _create_tray_icon_image():
    """Create a simple tray icon image using PIL."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Dark circle background
    draw.ellipse([4, 4, 60, 60], fill="#171717")
    # Green inner dot (GPS signal)
    draw.ellipse([22, 22, 42, 42], fill="#22c55e")
    # Small white center
    draw.ellipse([28, 28, 36, 36], fill="white")
    return img


def _run_pystray(manager, pystray, Image, ImageDraw):
    """Run with pystray system tray icon."""

    def on_open_dashboard(icon, item):
        manager.open_dashboard()

    def on_restart_agent(icon, item):
        if manager.agent_process and manager.agent_process.poll() is None:
            manager.agent_process.terminate()
            manager.agent_process.wait(timeout=5)
        manager.start_agent()

    def on_view_logs(icon, item):
        os.startfile(str(LOG_DIR))

    def on_quit(icon, item):
        manager.stop()
        icon.stop()

    icon_image = _create_tray_icon_image()
    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", on_open_dashboard, default=True),
        pystray.MenuItem(
            lambda item: f"Agent: {manager.agent_status()}",
            lambda icon, item: None,
            enabled=False,
        ),
        pystray.MenuItem("Restart Agent", on_restart_agent),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("View Logs", on_view_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit TrackGuard", on_quit),
    )
    icon = pystray.Icon("TrackGuard", icon_image, "TrackGuard — Running", menu)
    logger.info("System tray icon started")
    icon.run()


def _run_tkinter_fallback(manager: TrackGuardManager):
    """Fallback: minimal hidden tkinter window that keeps the launcher alive."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("TrackGuard")
    root.geometry("420x220")
    root.resizable(False, False)
    root.configure(bg="#0f0f0f")

    def on_close():
        if messagebox.askyesno(
            "Quit TrackGuard",
            "Quit TrackGuard and stop its background tracking processes?",
            parent=root,
        ):
            on_quit()

    def on_quit():
        manager.stop()
        root.destroy()

    def on_open_dashboard():
        manager.open_dashboard()

    root.protocol("WM_DELETE_WINDOW", on_close)

    # Header
    tk.Label(
        root, text="🛰️ TrackGuard", font=("Segoe UI", 16, "bold"),
        fg="white", bg="#0f0f0f",
    ).pack(pady=(20, 4))

    agent_status = tk.StringVar(value="Starting the TrackGuard agent…")
    tk.Label(
        root, textvariable=agent_status, font=("Segoe UI", 10),
        fg="#22c55e", bg="#0f0f0f",
    ).pack()

    def update_agent_status():
        process = manager.agent_process
        if process is None:
            agent_status.set("Agent was not started. Check logs.")
        elif process.poll() is None:
            agent_status.set("Agent process is running. Connection status: logs/agent.log")
        else:
            agent_status.set("Agent stopped. Check logs/agent.log and re-pair if needed.")
        root.after(1500, update_agent_status)

    update_agent_status()

    tk.Label(
        root, text=f"Dashboard: http://localhost:{manager.port}",
        font=("Segoe UI", 9), fg="#a0a0a0", bg="#0f0f0f",
    ).pack(pady=(8, 12))

    # Buttons frame
    btn_frame = tk.Frame(root, bg="#0f0f0f")
    btn_frame.pack(pady=6)

    tk.Button(
        btn_frame, text="Open Dashboard", command=on_open_dashboard,
        font=("Segoe UI", 10, "bold"), fg="white", bg="#22c55e",
        activebackground="#16a34a", activeforeground="white",
        relief="flat", padx=16, pady=6, cursor="hand2",
    ).pack(side="left", padx=6)

    tk.Button(
        btn_frame, text="Quit", command=on_quit,
        font=("Segoe UI", 10), fg="white", bg="#dc2626",
        activebackground="#b91c1c", activeforeground="white",
        relief="flat", padx=16, pady=6, cursor="hand2",
    ).pack(side="left", padx=6)

    tk.Label(
        root,         text="Use the system tray to keep TrackGuard running, or choose Quit to stop.",
        font=("Segoe UI", 8), fg="#666", bg="#0f0f0f",
    ).pack(pady=(8, 0))

    root.mainloop()


# ─── Error Dialog ─────────────────────────────────────────────
def show_error(title: str, message: str):
    """Show an error dialog."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        pass


# ─── Main ─────────────────────────────────────────────────────
def main():
    logger.info("=" * 50)
    logger.info("TrackGuard Launcher starting...")
    logger.info(f"Project root: {ROOT}")
    logger.info("=" * 50)

    manager = TrackGuardManager()

    # Step 1: Start the server
    if not manager.start_server():
        show_error("TrackGuard", "Failed to start the TrackGuard server.\nCheck logs/server.log for details.")
        return

    # Step 2: Wait for server to be ready
    if not manager.wait_for_server(timeout=30):
        show_error(
            "TrackGuard",
            "The TrackGuard server did not start in time.\n\n"
            "Possible causes:\n"
            "• Python dependencies not installed (run: pip install -r requirements.txt)\n"
            "• Port 8000 is already in use\n\n"
            "Check logs/server.log for details."
        )
        manager.stop()
        return

    # Step 3: Start the agent
    manager.start_agent()

    # Open the dashboard only when the user launches TrackGuard.
    manager.open_dashboard()

    # Keep the background processes managed by a visible system-tray app.
    manager.running = True
    try:
        run_with_tray(manager)
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop()
        logger.info("TrackGuard Launcher stopped.")


if __name__ == "__main__":
    main()
