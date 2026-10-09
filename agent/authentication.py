"""
TrackGuard Windows Agent — Device Authentication & Pairing
"""
import logging
import httpx
from config import load_config, save_config

logger = logging.getLogger(__name__)


async def pair_device(
    server_url: str,
    pin: str,
    device_name: str,
    device_type: str = "laptop",
) -> dict | None:
    """
    Register this device after PIN-authenticating the local owner.
    Returns the device credentials (device_id, device_token) on success.
    """
    server_url = server_url.strip().rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            login = await client.post(
                f"{server_url}/api/auth/unlock",
                json={"pin": pin},
            )
            if login.status_code != 200:
                logger.error("Device pairing PIN login failed: HTTP %s", login.status_code)
                return None

            owner_token = login.json().get("access_token")
            if not owner_token:
                logger.error("Device pairing PIN login response did not include an access token")
                return None

            pairing = await client.post(
                f"{server_url}/api/devices/pair/generate",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"name": device_name.strip(), "device_type": device_type},
            )
            if pairing.status_code != 200:
                logger.error("Device pairing code request failed: HTTP %s", pairing.status_code)
                return None

            pairing_code = pairing.json().get("code")
            if not pairing_code:
                logger.error("Device pairing response did not include a pairing code")
                return None

            resp = await client.post(
                f"{server_url}/api/devices/pair/activate",
                params={"code": pairing_code},
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
                    config["device_name"] = device_name.strip()
                    config["device_type"] = device_type
                    save_config(config)

                    logger.info(f"Device paired successfully. ID: {device_id}")
                    return {
                        "device_id": device_id,
                        "device_token": device_token,
                        "name": data.get("name", ""),
                    }

            logger.error("Device activation failed: HTTP %s", resp.status_code)
            return None

    except Exception as e:
        logger.error("Device pairing request failed: %s", e)
        return None
