"""
TrackGuard Windows Agent — Device Authentication & Pairing
"""
import logging
import httpx
from config import load_config, save_config

logger = logging.getLogger(__name__)


async def pair_device(server_url: str, pairing_code: str) -> dict | None:
    """
    Register the device using a pairing code.
    Returns the device credentials (device_id, device_token) on success.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{server_url}/api/devices/pair/activate?code={pairing_code}",
            )

            if resp.status_code == 200:
                data = resp.json()
                device_id = data.get("id")
                device_token = data.get("device_token")

                if device_id and device_token:
                    # Save credentials
                    config = load_config()
                    config["device_id"] = device_id
                    config["device_token"] = device_token
                    config["server_url"] = server_url
                    config["ws_url"] = server_url.replace("http://", "ws://").replace("https://", "wss://")
                    save_config(config)

                    logger.info(f"Device paired successfully. ID: {device_id}")
                    return {
                        "device_id": device_id,
                        "device_token": device_token,
                        "name": data.get("name", ""),
                    }

            logger.error(f"Pairing failed: {resp.status_code} - {resp.text}")
            return None

    except Exception as e:
        logger.error(f"Pairing error: {e}")
        return None
