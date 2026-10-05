"""
TrackGuard Windows Agent — Network Monitor
Collects network information including MAC addresses, IP addresses,
and connection type for device identification and monitoring.
"""
import logging
import socket
import uuid as _uuid
import psutil

logger = logging.getLogger(__name__)


def get_mac_address() -> str | None:
    """
    Get the primary MAC address of this machine.
    Uses the active network interface if possible, falls back to uuid.getnode().
    """
    try:
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()

        for iface_name, stats in net_if_stats.items():
            if not stats.isup:
                continue
            name_lower = iface_name.lower()
            if "loopback" in name_lower or name_lower == "lo":
                continue

            if iface_name in net_if_addrs:
                for addr in net_if_addrs[iface_name]:
                    # AF_LINK (macOS) or AF_PACKET (Linux) — psutil uses family=-1 on Windows
                    if addr.family == psutil.AF_LINK:
                        mac = addr.address
                        if mac and mac != "00:00:00:00:00:00":
                            return mac.upper()
    except Exception:
        pass

    # Fallback: derive from uuid.getnode()
    try:
        node = _uuid.getnode()
        mac = ":".join(f"{(node >> (8 * i)) & 0xFF:02X}" for i in reversed(range(6)))
        if mac != "00:00:00:00:00:00":
            return mac
    except Exception:
        pass

    return None


def get_all_mac_addresses() -> list[dict]:
    """
    Get MAC addresses for all active network interfaces.
    Returns a list of {interface, mac, type} dicts.
    """
    macs = []
    try:
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()

        for iface_name, stats in net_if_stats.items():
            if not stats.isup:
                continue
            name_lower = iface_name.lower()
            if "loopback" in name_lower or name_lower == "lo":
                continue

            if iface_name in net_if_addrs:
                for addr in net_if_addrs[iface_name]:
                    if addr.family == psutil.AF_LINK:
                        mac = addr.address
                        if mac and mac != "00:00:00:00:00:00":
                            iface_type = "unknown"
                            if "wi-fi" in name_lower or "wifi" in name_lower or "wlan" in name_lower:
                                iface_type = "wifi"
                            elif "ethernet" in name_lower or "eth" in name_lower:
                                iface_type = "ethernet"
                            macs.append({
                                "interface": iface_name,
                                "mac": mac.upper(),
                                "type": iface_type,
                            })
    except Exception as e:
        logger.warning(f"MAC collection error: {e}")

    return macs


def get_network_info() -> dict:
    """Get current network information including MAC, IP, and connection type."""
    try:
        info = {
            "wifi_connected": False,
            "network_type": "disconnected",
            "local_ip": None,
            "public_ip": None,
            "mac_address": None,
        }

        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()

        for iface_name, stats in net_if_stats.items():
            if not stats.isup:
                continue
            name_lower = iface_name.lower()
            if "loopback" in name_lower or name_lower == "lo":
                continue

            # Determine connection type
            if "wi-fi" in name_lower or "wifi" in name_lower or "wlan" in name_lower or "wireless" in name_lower:
                info["wifi_connected"] = True
                info["network_type"] = "wifi"
            elif "ethernet" in name_lower or "eth" in name_lower or "lan" in name_lower:
                if info["network_type"] == "disconnected":
                    info["network_type"] = "ethernet"

            # Get IP and MAC from interface
            if iface_name in net_if_addrs:
                for addr in net_if_addrs[iface_name]:
                    if addr.family == socket.AF_INET and not addr.address.startswith("169.254"):
                        info["local_ip"] = addr.address
                    if addr.family == psutil.AF_LINK:
                        mac = addr.address
                        if mac and mac != "00:00:00:00:00:00":
                            info["mac_address"] = mac.upper()

        # Get primary MAC if not found from active interface
        if not info["mac_address"]:
            info["mac_address"] = get_mac_address()

        # Get public IP
        info["public_ip"] = _get_public_ip()

        return info

    except Exception as e:
        logger.warning(f"Network info error: {e}")
        return {
            "wifi_connected": False,
            "network_type": "unknown",
            "local_ip": None,
            "public_ip": None,
            "mac_address": None,
        }


def _get_public_ip() -> str | None:
    """Get public IP address."""
    try:
        import httpx
        resp = httpx.get("https://api.ipify.org", timeout=5)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    return None


def is_connected() -> bool:
    """Check if the computer has internet connectivity."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False
