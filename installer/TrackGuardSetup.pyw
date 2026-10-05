import asyncio
import json
import os
import runpy
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

import httpx
import psutil
import websockets


def bundle_path(relative_path):
    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return bundle_dir / relative_path


AGENT_BUNDLE_DIR = bundle_path("agent")
if str(AGENT_BUNDLE_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_BUNDLE_DIR))

try:
    from authentication import pair_device
    from config import is_registered
except ImportError as error:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("TrackGuard installer", f"Agent components are missing: {error}")
    raise SystemExit(1)


try:
    INSTALLER_PAYLOAD = json.loads(bundle_path("installer_payload.json").read_text(encoding="utf-8"))
    SERVER_URL = INSTALLER_PAYLOAD["server_url"]
    PAIRING_CODE = INSTALLER_PAYLOAD["pairing_code"]
    DEVICE_NAME = INSTALLER_PAYLOAD["device_name"]
except (OSError, KeyError, json.JSONDecodeError) as error:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("TrackGuard installer", f"Installer setup data is invalid or missing: {error}")
    raise SystemExit(1)


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TrackGuard"
INSTALLED_EXE = APP_DIR / "TrackGuard.exe"
LOG_FILE = APP_DIR / "agent.log"
STARTUP_VALUE_NAME = "TrackGuardAgent"
LEGACY_TASK_NAME = "TrackGuardAgent"


class Installer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TrackGuard setup")
        self.root.geometry("440x360")
        self.root.resizable(False, False)
        self.root.configure(bg="#f7f7fa")
        self.status = tk.StringVar(value="Ready to install TrackGuard on this device.")
        self.install_button = None
        self._build_window()

    def _build_window(self):
        tk.Label(
            self.root,
            text="TrackGuard",
            font=("Segoe UI", 20, "bold"),
            fg="#282532",
            bg="#f7f7fa",
        ).pack(pady=(24, 2))
        tk.Label(
            self.root,
            text="Device setup",
            font=("Segoe UI", 10),
            fg="#77747f",
            bg="#f7f7fa",
        ).pack()

        card = tk.Frame(self.root, bg="white", highlightbackground="#e8e6ed", highlightthickness=1)
        card.pack(fill="x", padx=24, pady=20)
        tk.Label(
            card,
            text="This computer will be paired as",
            font=("Segoe UI", 9),
            fg="#77747f",
            bg="white",
        ).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            card,
            text=DEVICE_NAME,
            font=("Segoe UI", 12, "bold"),
            fg="#282532",
            bg="white",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        self.progress = tk.Label(
            self.root,
            textvariable=self.status,
            wraplength=370,
            justify="center",
            font=("Segoe UI", 9),
            fg="#5f5b69",
            bg="#f7f7fa",
        )
        self.progress.pack(padx=24, pady=(0, 12))
        self.install_button = tk.Button(
            self.root,
            text="Install and connect",
            command=self.start_install,
            font=("Segoe UI", 10, "bold"),
            fg="white",
            bg="#171717",
            activebackground="#353535",
            activeforeground="white",
            relief="flat",
            padx=22,
            pady=10,
            cursor="hand2",
        )
        self.install_button.pack(pady=(0, 10))
        tk.Label(
            self.root,
            text="No Python installation or terminal commands are required.",
            font=("Segoe UI", 8),
            fg="#92909a",
            bg="#f7f7fa",
        ).pack()

    def start_install(self):
        self.install_button.configure(state="disabled", text="Installing…")
        self.status.set("Installing and connecting this device. Please wait…")
        threading.Thread(target=self.install, daemon=True).start()

    def install(self):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            if not getattr(sys, "frozen", False):
                raise RuntimeError("Run the downloaded TrackGuardSetup.exe to install this device.")
            if Path(sys.executable).resolve() != INSTALLED_EXE.resolve():
                shutil.copy2(sys.executable, INSTALLED_EXE)

            if not is_registered():
                self._set_status("Securely enrolling this device…")
                result = asyncio.run(pair_device(SERVER_URL, PAIRING_CODE))
                if not result:
                    raise RuntimeError(
                        "Enrollment was rejected. The installer may have expired or the server address "
                        "may be unreachable. Create a fresh installer from the dashboard."
                    )

            self._set_status("Starting the background tracking service…")
            with LOG_FILE.open("a", encoding="utf-8") as log:
                agent_process = subprocess.Popen(
                    [str(INSTALLED_EXE), "--agent"],
                    cwd=str(APP_DIR),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            self.root.after(1500, lambda: self._finish_install(agent_process))
        except Exception as error:
            detail = str(error)
            self.root.after(0, lambda: self._install_failed(detail))

    def _set_status(self, text):
        self.root.after(0, self.status.set, text)

    def _finish_install(self, process):
        if process.poll() is not None:
            try:
                details = LOG_FILE.read_text(encoding="utf-8", errors="replace")[-1800:]
            except OSError:
                details = "The agent stopped before connecting."
            self._install_failed(details or "The agent stopped before connecting.")
            return

        try:
            import winreg

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.SetValueEx(
                    key,
                    STARTUP_VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    f'"{INSTALLED_EXE}" --agent',
                )
            subprocess.run(
                ["schtasks", "/Delete", "/TN", LEGACY_TASK_NAME, "/F"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            self.status.set("Agent started, but Windows could not enable automatic startup.")
            self.install_button.configure(text="Agent running", state="disabled")
            messagebox.showwarning(
                "Setup complete; startup not enabled",
                "The agent is running for this session. Windows could not configure automatic startup:\n\n"
                + str(error),
            )
        else:
            self.status.set("Agent started. TrackGuard will start automatically when you sign in.")
            self.install_button.configure(text="Installed", state="disabled")
            messagebox.showinfo(
                "TrackGuard setup complete",
                f"The agent is installed at:\n{INSTALLED_EXE}\n\n"
                "It is running in the background and will start when you sign in. "
                "The downloaded setup file is no longer needed and can be deleted.",
            )
            self.root.after(1200, self.root.destroy)

    def _install_failed(self, detail):
        self.status.set("Setup could not complete.")
        self.install_button.configure(state="normal", text="Try again")
        messagebox.showerror(
            "TrackGuard setup failed",
            "TrackGuard could not install or connect the agent.\n\n"
            + detail
            + "\n\nCheck the server address and internet access, then try again.",
        )

    def run(self):
        self.root.mainloop()


def run_bundled_agent():
    agent_script = AGENT_BUNDLE_DIR / "agent.py"
    if not agent_script.is_file():
        raise FileNotFoundError("The bundled TrackGuard agent is missing.")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    agent_log = LOG_FILE.open("a", encoding="utf-8")
    sys.stdout = agent_log
    sys.stderr = agent_log
    sys.path.insert(0, str(AGENT_BUNDLE_DIR))
    sys.argv = [str(agent_script)]
    runpy.run_path(str(agent_script), run_name="__main__")


def verify_bundle():
    required_files = ("agent.py", "authentication.py", "config.py", "location.py")
    if not all((AGENT_BUNDLE_DIR / filename).is_file() for filename in required_files):
        raise FileNotFoundError("One or more bundled TrackGuard agent files are missing.")
    if not all((httpx, psutil, websockets)):
        raise ImportError("A bundled TrackGuard agent dependency is missing.")


if __name__ == "__main__":
    try:
        if "--self-test" in sys.argv[1:]:
            verify_bundle()
        elif "--agent" in sys.argv[1:]:
            run_bundled_agent()
        else:
            Installer().run()
    except Exception:
        error_text = traceback.format_exc()
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("TrackGuard setup error", error_text[-1800:])
        except tk.TclError:
            with LOG_FILE.open("a", encoding="utf-8") as log:
                log.write(error_text)
