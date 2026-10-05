"""
TrackGuard Windows Agent Configuration
"""
import os
import json
from pathlib import Path

# ─── Default Configuration ──────────────────────────────────
DEFAULT_CONFIG = {
    "server_url": "http://localhost:8000",
    "ws_url": "ws://localhost:8000",
    "device_id": "",
    "device_token": "",
    "heartbeat_interval": 30,
    "location_interval": 60,
    "status_interval": 60,
    "battery_interval": 30,
    "network_interval": 30,
    "lost_mode_location_interval": 10,
    "reconnect_base_delay": 2,
    "reconnect_max_delay": 60,
}

CONFIG_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "TrackGuard"
CONFIG_FILE = CONFIG_DIR / "agent_config.json"


def load_config() -> dict:
    """Load configuration from file or return defaults."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
            config = DEFAULT_CONFIG.copy()
            config.update(saved)
            return config
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save configuration to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def is_registered() -> bool:
    """Check if the agent has been registered (has device_id and token)."""
    config = load_config()
    return bool(config.get("device_id")) and bool(config.get("device_token"))
