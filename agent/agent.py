"""
TrackGuard Windows Agent — Main Agent
Background service that connects to the TrackGuard server, sends telemetry,
and listens for authorized remote commands.

Usage:
  python agent.py                    # Run the agent
  python agent.py --pair CODE        # Pair with a pairing code
  python agent.py --server URL       # Set server URL
  python agent.py --install-startup  # Install as Windows startup task
"""
import asyncio
import json
import logging
import sys
import signal
import argparse
import platform
from datetime import datetime, timezone

import websockets

from config import load_config, save_config, is_registered
from location import get_location
from battery import get_battery_info
from network import get_network_info
from system import get_system_info, get_device_name
from commands import execute_command
from authentication import pair_device

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("TrackGuard.Agent")


class TrackGuardAgent:
    """
    Main agent class that manages:
    - WebSocket connection to the backend
    - Periodic telemetry (heartbeat, location, battery, network, status)
    - Remote command execution
    - Automatic reconnection with exponential backoff
    """

    def __init__(self):
        self.config = load_config()
        self.ws = None
        self.running = False
        self.lost_mode = False
        self.reconnect_delay = self.config.get("reconnect_base_delay", 2)
        self._tasks = []

    @property
    def device_id(self) -> str:
        return self.config.get("device_id", "")

    @property
    def device_token(self) -> str:
        return self.config.get("device_token", "")

    @property
    def ws_url(self) -> str:
        base = self.config.get("ws_url", "ws://localhost:8000")
        return f"{base}/ws/device/{self.device_id}?token={self.device_token}"

    @property
    def location_interval(self) -> int:
        if self.lost_mode:
            return self.config.get("lost_mode_location_interval", 10)
        return self.config.get("location_interval", 60)

    # ─── Main Run Loop ──────────────────────────────────────
    async def run(self):
        """Main agent loop with automatic reconnection."""
        self.running = True
        logger.info("TrackGuard Agent starting...")

        while self.running:
            try:
                await self._connect_and_run()
            except Exception as e:
                logger.error(f"Connection error: {e}")

            if self.running:
                delay = min(self.reconnect_delay, self.config.get("reconnect_max_delay", 60))
                logger.info(f"Reconnecting in {delay} seconds...")
                await asyncio.sleep(delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.config.get("reconnect_max_delay", 60))

    async def _connect_and_run(self):
        """Establish WebSocket connection and run telemetry tasks."""
        logger.info(f"Connecting to {self.config.get('ws_url', '')}...")

        async with websockets.connect(
            self.ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            self.ws = ws
            self.reconnect_delay = self.config.get("reconnect_base_delay", 2)
            logger.info("✅ Connected to TrackGuard server")

            # Send initial status
            await self._send_full_status()

            # Start periodic tasks
            self._tasks = [
                asyncio.create_task(self._heartbeat_loop()),
                asyncio.create_task(self._location_loop()),
                asyncio.create_task(self._battery_loop()),
                asyncio.create_task(self._network_loop()),
                asyncio.create_task(self._listen_loop()),
            ]

            try:
                await asyncio.gather(*self._tasks)
            except Exception:
                pass
            finally:
                for task in self._tasks:
                    task.cancel()
                self._tasks = []

    # ─── Telemetry Loops ─────────────────────────────────────
    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        interval = self.config.get("heartbeat_interval", 30)
        while self.running and self.ws:
            try:
                await self._send({
                    "type": "HEARTBEAT",
                    "data": {"timestamp": datetime.now(timezone.utc).isoformat()},
                })
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
            await asyncio.sleep(interval)

    async def _location_loop(self):
        """Send periodic location updates."""
        while self.running and self.ws:
            try:
                location = await get_location()
                if location.get("latitude") is not None:
                    await self._send({
                        "type": "LOCATION_UPDATE",
                        "data": {
                            "latitude": location["latitude"],
                            "longitude": location["longitude"],
                            "accuracy": location.get("accuracy"),
                            "source": location.get("source", "unknown"),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    })
            except Exception as e:
                logger.error(f"Location error: {e}")
                break
            await asyncio.sleep(self.location_interval)

    async def _battery_loop(self):
        """Send periodic battery updates."""
        interval = self.config.get("battery_interval", 30)
        while self.running and self.ws:
            try:
                battery = get_battery_info()
                await self._send({
                    "type": "BATTERY_UPDATE",
                    "data": battery,
                })
            except Exception as e:
                logger.error(f"Battery error: {e}")
                break
            await asyncio.sleep(interval)

    async def _network_loop(self):
        """Send periodic network updates."""
        interval = self.config.get("network_interval", 30)
        while self.running and self.ws:
            try:
                network = get_network_info()
                await self._send({
                    "type": "NETWORK_UPDATE",
                    "data": network,
                })
            except Exception as e:
                logger.error(f"Network error: {e}")
                break
            await asyncio.sleep(interval)

    # ─── Incoming Message Handler ────────────────────────────
    async def _listen_loop(self):
        """Listen for incoming messages from the server."""
        while self.running and self.ws:
            try:
                raw = await self.ws.recv()
                data = json.loads(raw)
                await self._handle_message(data)
            except websockets.ConnectionClosed:
                logger.info("Connection closed by server")
                break
            except Exception as e:
                logger.error(f"Listen error: {e}")
                break

    async def _handle_message(self, data: dict):
        """Process an incoming message from the server."""
        msg_type = data.get("type", "")
        logger.info(f"Received: {msg_type}")

        if msg_type == "COMMAND":
            command = data.get("command", "")
            command_id = data.get("command_id", "")

            if command in ("GET_STATUS",):
                await self._send_full_status()
                result = {"status": "success", "result": "Status sent"}
            elif command in ("GET_LOCATION",):
                location = await get_location()
                if location.get("latitude") is not None:
                    await self._send({
                        "type": "LOCATION_UPDATE",
                        "data": {
                            "latitude": location["latitude"],
                            "longitude": location["longitude"],
                            "accuracy": location.get("accuracy"),
                            "source": location.get("source", "unknown"),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    })
                result = {"status": "success", "result": "Location sent"}
            else:
                result = await execute_command(command)

            # Report result back
            await self._send({
                "type": "COMMAND_RESULT",
                "data": {
                    "command_id": command_id,
                    "command": command,
                    "status": result.get("status", "failed"),
                    "result": result.get("result", ""),
                },
            })

        elif msg_type == "ENABLE_LOST_MODE":
            self.lost_mode = True
            interval = data.get("data", {}).get("interval", 10)
            logger.info(f"Lost Mode ENABLED. Location interval: {interval}s")

        elif msg_type == "DISABLE_LOST_MODE":
            self.lost_mode = False
            logger.info("Lost Mode DISABLED")

        elif msg_type == "DEVICE_REMOVED":
            logger.warning("Device has been removed from TrackGuard. Stopping agent.")
            self.running = False

    # ─── Helpers ─────────────────────────────────────────────
    async def _send(self, message: dict):
        """Send a JSON message to the server."""
        if self.ws:
            await self.ws.send(json.dumps(message))

    async def _send_full_status(self):
        """Send comprehensive status update."""
        sys_info = get_system_info()
        battery = get_battery_info()
        network = get_network_info()

        await self._send({
            "type": "STATUS_UPDATE",
            "data": {
                **sys_info,
                "battery_level": battery.get("battery_level"),
                "is_charging": battery.get("is_charging"),
                **network,
            },
        })

    def stop(self):
        """Stop the agent."""
        logger.info("Stopping TrackGuard Agent...")
        self.running = False
        for task in self._tasks:
            task.cancel()


# ─── Windows Startup Installation ────────────────────────────
def install_startup():
    """Install the agent as a Windows startup task."""
    if platform.system() != "Windows":
        print("This command is only available on Windows.")
        return

    import os
    import subprocess

    agent_path = os.path.abspath(__file__)
    python_path = sys.executable
    task_name = "TrackGuardAgent"

    # Create a scheduled task that runs at login
    cmd = [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", f'"{python_path}" "{agent_path}"',
        "/sc", "onlogon",
        "/rl", "highest",
        "/f",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ TrackGuard Agent installed as startup task: {task_name}")
            print(f"   Agent path: {agent_path}")
            print(f"   Python: {python_path}")
        else:
            print(f"❌ Failed to create startup task: {result.stderr}")
    except Exception as e:
        print(f"❌ Error: {e}")


# ─── Main Entry Point ───────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="TrackGuard Windows Agent")
    parser.add_argument("--pair", type=str, help="Pair with a pairing code")
    parser.add_argument("--server", type=str, help="Server URL (e.g., http://localhost:8000)")
    parser.add_argument("--install-startup", action="store_true", help="Install as Windows startup task")
    args = parser.parse_args()

    if args.install_startup:
        install_startup()
        return

    if args.server:
        config = load_config()
        config["server_url"] = args.server
        config["ws_url"] = args.server.replace("http://", "ws://").replace("https://", "wss://")
        save_config(config)
        print(f"Server URL set to: {args.server}")

    if args.pair:
        config = load_config()
        server_url = config.get("server_url", "http://localhost:8000")
        print(f"Pairing with server: {server_url}")
        result = await pair_device(server_url, args.pair)
        if result:
            print(f"✅ Device paired: {result.get('name', 'Unknown')}")
            print(f"   Device ID: {result.get('device_id')}")
        else:
            print("[X] Pairing failed. Check the code and try again.")
            return

    if not is_registered():
        print("="*50)
        print("TrackGuard Agent — Not Registered")
        print("="*50)
        print()
        print("To pair this device:")
        print("  1. Open TrackGuard Dashboard")
        print("  2. Go to Devices → Add Device")
        print("  3. Generate a pairing code")
        print("  4. Run: python agent.py --pair YOUR_CODE")
        print()
        return

    # Run the agent
    agent = TrackGuardAgent()

    # Handle graceful shutdown
    def shutdown_handler(sig, frame):
        agent.stop()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
