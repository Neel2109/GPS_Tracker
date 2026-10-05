"""
TrackGuard Windows Agent — System Information
"""
import logging
import platform
import psutil

logger = logging.getLogger(__name__)


def get_system_info() -> dict:
    """Gather system hardware and OS information."""
    try:
        uname = platform.uname()
        cpu_freq = psutil.cpu_freq()
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        return {
            "platform": uname.system,
            "os_version": f"{uname.system} {uname.release} (Build {uname.version})",
            "model": f"{uname.node}",
            "cpu_info": _get_cpu_name() or f"{uname.processor}",
            "ram_total": f"{vm.total // (1024**3)} GB",
            "storage_total": f"{disk.total // (1024**3)} GB",
            "cpu_cores": psutil.cpu_count(logical=True),
            "cpu_freq_mhz": int(cpu_freq.current) if cpu_freq else None,
        }
    except Exception as e:
        logger.warning(f"System info error: {e}")
        return {
            "platform": platform.system(),
            "os_version": platform.platform(),
            "model": platform.node(),
            "cpu_info": "Unknown",
            "ram_total": "Unknown",
            "storage_total": "Unknown",
        }


def _get_cpu_name() -> str | None:
    """Try to get the CPU brand name on Windows."""
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return name.strip()
    except Exception:
        pass
    return None


def get_device_name() -> str:
    """Get the computer's name."""
    return platform.node()
