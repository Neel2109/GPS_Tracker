import asyncio
import os
import runpy
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlsplit

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
    from config import is_registered, load_config
    from system import get_device_name
except ImportError as error:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("TrackGuard installer", f"Agent components are missing: {error}")
    raise SystemExit(1)

APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TrackGuard"
INSTALLED_EXE = APP_DIR / "TrackGuard.exe"
LOG_FILE = APP_DIR / "agent.log"
STARTUP_VALUE_NAME = "TrackGuardAgent"
LEGACY_TASK_NAME = "TrackGuardAgent"


class Installer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TrackGuard device setup")
        self.root.geometry("460x540")
        self.root.minsize(420, 500)
        self.root.configure(bg="#f5f7f5")
        config = load_config()
        self.already_registered = is_registered()
        self.server_url = tk.StringVar(value=config.get("server_url", "http://localhost:8000"))
        self.device_name = tk.StringVar(value=config.get("device_name") or get_device_name())
        self.device_type = tk.StringVar(value=config.get("device_type", "laptop"))
        self.pin = tk.StringVar()
        self.status = tk.StringVar(
            value=(
                "This device is already paired. Start tracking to reconnect."
                if self.already_registered
                else "Enter the TrackGuard server and owner PIN to pair this device."
            )
        )
        self.install_button = None
        self._build_window()

    def _build_window(self):
        tk.Label(
            self.root,
            text="TrackGuard",
            font=("Segoe UI", 22, "bold"),
            fg="#173a2d",
            bg="#f5f7f5",
        ).pack(pady=(22, 3))
        tk.Label(
            self.root,
            text="Pair this device with your TrackGuard server",
            font=("Segoe UI", 10),
            fg="#65736a",
            bg="#f5f7f5",
        ).pack(pady=(0, 18))

        card = tk.Frame(self.root, bg="white", highlightbackground="#dce6de", highlightthickness=1)
        card.pack(fill="x", padx=24, pady=(0, 16))
        field_state = "readonly" if self.already_registered else "normal"
        self._add_entry(card, "TrackGuard server address", self.server_url, state=field_state)
        self._add_entry(card, "Device name", self.device_name, state=field_state)

        tk.Label(card, text="Device type", font=("Segoe UI", 9, "bold"), fg="#405247", bg="white").pack(
            anchor="w", padx=16, pady=(8, 4)
        )
        ttk.Combobox(
            card,
            textvariable=self.device_type,
            values=("laptop", "desktop"),
            state="disabled" if self.already_registered else "readonly",
            font=("Segoe UI", 10),
        ).pack(fill="x", padx=16, ipady=4)
        if self.already_registered:
            setup_note = "Saved device credentials will be reused. To pair with another server, remove this device's local TrackGuard configuration first."
        else:
            self._add_entry(card, "Owner PIN", self.pin, show="*")
            setup_note = "The PIN is used once to pair this device and is not saved."
        tk.Label(
            card,
            text=setup_note,
            font=("Segoe UI", 8),
            fg="#748278",
            bg="white",
            wraplength=370,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(7, 16))

        self.progress = tk.Label(
            self.root,
            textvariable=self.status,
            wraplength=390,
            justify="center",
            font=("Segoe UI", 9),
            fg="#5f6b62",
            bg="#f5f7f5",
        )
        self.progress.pack(fill="x", padx=24, pady=(0, 14))
        self.install_button = tk.Button(
            self.root,
            text="Start tracking" if self.already_registered else "Pair and connect",
            command=self.start_install,
            font=("Segoe UI", 10, "bold"),
            fg="white",
            bg="#1d6a49",
            activebackground="#17583c",
            activeforeground="white",
            relief="flat",
            padx=24,
            pady=11,
            cursor="hand2",
        )
        self.install_button.pack(fill="x", padx=24, pady=(0, 10))
        tk.Label(
            self.root,
            text="No installer download or terminal commands are needed.",
            font=("Segoe UI", 8),
            fg="#7d8980",
            bg="#f5f7f5",
        ).pack()

    @staticmethod
    def _add_entry(parent, label, variable, show=None, state="normal"):
        tk.Label(parent, text=label, font=("Segoe UI", 9, "bold"), fg="#405247", bg="white").pack(
            anchor="w", padx=16, pady=(12, 4)
        )
        tk.Entry(
            parent,
            textvariable=variable,
            show=show or "",
            state=state,
            font=("Segoe UI", 10),
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
        ).pack(fill="x", padx=16, ipady=8)

    def start_install(self):
        server_url = self.server_url.get().strip().rstrip("/")
        device_name = self.device_name.get().strip()
        try:
            parsed = urlsplit(server_url)
            valid = (
                parsed.scheme in ("http", "https")
                and parsed.hostname is not None
                and parsed.username is None
                and parsed.password is None
                and parsed.path in ("", "/")
                and parsed.query == ""
                and parsed.fragment == ""
                and (parsed.port is None or 1 <= parsed.port <= 65535)
            )
        except ValueError:
            valid = False
        if not valid:
            messagebox.showerror("Invalid server address", "Enter a valid address starting with http:// or https://.", parent=self.root)
            return
        if not device_name or len(device_name) > 100:
            messagebox.showerror("Invalid device name", "Enter a device name up to 100 characters.", parent=self.root)
            return
        if not is_registered() and (not self.pin.get().isdigit() or not 6 <= len(self.pin.get()) <= 12):
            messagebox.showerror("Invalid PIN", "Enter the 6–12 digit owner PIN configured on the TrackGuard server.", parent=self.root)
            return
        pairing_details = (
            server_url,
            device_name,
            self.device_type.get(),
            self.pin.get(),
        )
        self.install_button.configure(state="disabled", text="Installing…")
        self.status.set("Pairing and connecting this device. Please wait…")
        threading.Thread(target=self.install, args=(pairing_details,), daemon=True).start()

    def install(self, pairing_details):
        server_url, device_name, device_type, pin = pairing_details
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            if not getattr(sys, "frozen", False):
                raise RuntimeError("Run the packaged TrackGuardSetup.exe to set up this device.")
            if Path(sys.executable).resolve() != INSTALLED_EXE.resolve():
                shutil.copy2(sys.executable, INSTALLED_EXE)

            if not is_registered():
                self._set_status("Signing in and pairing this device…")
                result = asyncio.run(
                    pair_device(
                        server_url,
                        pin,
                        device_name,
                        device_type,
                    )
                )
                if not result:
                    raise RuntimeError(
                        "Pairing was rejected. Check the PIN and server address, then try again."
                    )
                self.root.after(0, self.pin.set, "")

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
