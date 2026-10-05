"""
TrackGuard Windows Agent — Remote Command Executor
Only explicitly supported commands are allowed.
"""
import asyncio
import ctypes
import logging
import subprocess
import sys
import platform

logger = logging.getLogger(__name__)

# ─── Allowed Commands ───────────────────────────────────────
ALLOWED_COMMANDS = {"LOCK", "SLEEP", "RESTART", "SHUTDOWN", "GET_STATUS", "GET_LOCATION", "PING"}


async def execute_command(command: str) -> dict:
    """
    Execute a permitted remote command.
    Returns a result dict with status and message.
    """
    command = command.upper()

    if command not in ALLOWED_COMMANDS:
        logger.warning(f"Rejected unknown command: {command}")
        return {
            "status": "failed",
            "result": f"Unknown command: {command}",
        }

    logger.info(f"Executing command: {command}")

    try:
        if command == "LOCK":
            return await _lock_workstation()
        elif command == "SLEEP":
            return await _sleep_computer()
        elif command == "RESTART":
            return await _restart_computer()
        elif command == "SHUTDOWN":
            return await _shutdown_computer()
        elif command == "PING":
            return {"status": "success", "result": "pong"}
        elif command in ("GET_STATUS", "GET_LOCATION"):
            # These are handled by the main agent loop
            return {"status": "success", "result": f"{command} requested"}
        else:
            return {"status": "failed", "result": "Not implemented"}

    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return {"status": "failed", "result": str(e)}


async def _lock_workstation() -> dict:
    """Lock the Windows workstation."""
    if platform.system() != "Windows":
        return {"status": "failed", "result": "Not a Windows system"}

    try:
        ctypes.windll.user32.LockWorkStation()
        return {"status": "success", "result": "Workstation locked"}
    except Exception as e:
        return {"status": "failed", "result": f"Lock failed: {e}"}


async def _sleep_computer() -> dict:
    """Put the computer to sleep."""
    if platform.system() != "Windows":
        return {"status": "failed", "result": "Not a Windows system"}

    try:
        proc = await asyncio.create_subprocess_exec(
            "rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        await proc.wait()
        return {"status": "success", "result": "Computer entering sleep mode"}
    except Exception as e:
        return {"status": "failed", "result": f"Sleep failed: {e}"}


async def _restart_computer() -> dict:
    """Restart the computer."""
    if platform.system() != "Windows":
        return {"status": "failed", "result": "Not a Windows system"}

    try:
        proc = await asyncio.create_subprocess_exec(
            "shutdown", "/r", "/t", "5", "/c", "TrackGuard: Remote restart initiated",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        await proc.wait()
        return {"status": "success", "result": "Restart initiated (5 seconds)"}
    except Exception as e:
        return {"status": "failed", "result": f"Restart failed: {e}"}


async def _shutdown_computer() -> dict:
    """Shut down the computer."""
    if platform.system() != "Windows":
        return {"status": "failed", "result": "Not a Windows system"}

    try:
        proc = await asyncio.create_subprocess_exec(
            "shutdown", "/s", "/t", "5", "/c", "TrackGuard: Remote shutdown initiated",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        await proc.wait()
        return {"status": "success", "result": "Shutdown initiated (5 seconds)"}
    except Exception as e:
        return {"status": "failed", "result": f"Shutdown failed: {e}"}
