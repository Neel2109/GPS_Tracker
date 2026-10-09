import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import authentication


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses, calls):
        self.responses = iter(responses)
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def test_pair_device_uses_pin_then_owner_pairing_code_and_saves_device_credentials(monkeypatch):
    calls = []
    saved_config = {}
    responses = [
        FakeResponse(200, {"access_token": "owner-token"}),
        FakeResponse(200, {"code": "one-time-code"}),
        FakeResponse(200, {"id": "device-id", "device_token": "device-token", "name": "Laptop"}),
    ]
    monkeypatch.setattr(
        authentication.httpx,
        "AsyncClient",
        lambda timeout: FakeClient(responses, calls),
    )
    monkeypatch.setattr(authentication, "load_config", lambda: {})
    monkeypatch.setattr(authentication, "save_config", lambda config: saved_config.update(config))

    result = asyncio.run(
        authentication.pair_device(" http://trackguard.local:8000/ ", "123456", " Laptop ")
    )

    assert result == {"device_id": "device-id", "device_token": "device-token", "name": "Laptop"}
    assert calls[0] == (
        "http://trackguard.local:8000/api/auth/unlock",
        {"json": {"pin": "123456"}},
    )
    assert calls[1][0] == "http://trackguard.local:8000/api/devices/pair/generate"
    assert calls[1][1]["headers"] == {"Authorization": "Bearer owner-token"}
    assert calls[1][1]["json"] == {"name": "Laptop", "device_type": "laptop"}
    assert calls[2] == (
        "http://trackguard.local:8000/api/devices/pair/activate",
        {"params": {"code": "one-time-code"}},
    )
    assert saved_config == {
        "device_id": "device-id",
        "device_token": "device-token",
        "server_url": "http://trackguard.local:8000",
        "ws_url": "http://trackguard.local:8000".replace("http://", "ws://"),
        "device_name": "Laptop",
        "device_type": "laptop",
    }


def test_pair_device_does_not_create_pairing_code_when_pin_is_rejected(monkeypatch):
    calls = []
    saved_config = {}
    monkeypatch.setattr(
        authentication.httpx,
        "AsyncClient",
        lambda timeout: FakeClient([FakeResponse(401, {"detail": "Incorrect PIN"})], calls),
    )
    monkeypatch.setattr(authentication, "load_config", lambda: {})
    monkeypatch.setattr(authentication, "save_config", lambda config: saved_config.update(config))

    result = asyncio.run(authentication.pair_device("http://trackguard.local:8000", "000000", "Laptop"))

    assert result is None
    assert len(calls) == 1
    assert saved_config == {}
