"""
TrackGuard Windows Agent — Battery Monitor
"""
import logging
import psutil

logger = logging.getLogger(__name__)


def get_battery_info() -> dict:
    """Get current battery information."""
    try:
        battery = psutil.sensors_battery()
        if battery:
            return {
                "battery_level": int(battery.percent),
                "is_charging": battery.power_plugged,
                "time_remaining": (
                    int(battery.secsleft / 60) if battery.secsleft > 0 else None
                ),
                "status": _get_battery_status(battery),
            }
    except Exception as e:
        logger.warning(f"Battery info error: {e}")

    return {
        "battery_level": None,
        "is_charging": None,
        "time_remaining": None,
        "status": "unknown",
    }


def _get_battery_status(battery) -> str:
    """Determine battery status string."""
    if battery.power_plugged:
        if battery.percent >= 100:
            return "full"
        return "charging"
    if battery.percent <= 20:
        return "low"
    return "discharging"
