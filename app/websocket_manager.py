import json
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps user_id -> Set[WebSocket] for dashboard clients
        self.dashboard_connections: Dict[str, Set[WebSocket]] = {}
        # Maps device_id -> WebSocket for agent clients
        self.device_connections: Dict[str, WebSocket] = {}

    async def connect_dashboard(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.dashboard_connections:
            self.dashboard_connections[user_id] = set()
        self.dashboard_connections[user_id].add(websocket)
        logger.info(f"Dashboard client connected for user {user_id}")

    def disconnect_dashboard(self, websocket: WebSocket, user_id: str):
        if user_id in self.dashboard_connections:
            self.dashboard_connections[user_id].discard(websocket)
            if not self.dashboard_connections[user_id]:
                del self.dashboard_connections[user_id]

    async def connect_device(self, websocket: WebSocket, device_id: str):
        await websocket.accept()
        self.device_connections[device_id] = websocket
        logger.info(f"Device agent connected: {device_id}")

    def disconnect_device(self, device_id: str):
        if device_id in self.device_connections:
            del self.device_connections[device_id]
            logger.info(f"Device agent disconnected: {device_id}")

    async def send_to_dashboard(self, user_id: str, message: dict):
        if user_id in self.dashboard_connections:
            text = json.dumps(message)
            dead_sockets = set()
            for ws in self.dashboard_connections[user_id]:
                try:
                    await ws.send_text(text)
                except Exception:
                    dead_sockets.add(ws)
            for ws in dead_sockets:
                self.dashboard_connections[user_id].discard(ws)

    async def send_to_device(self, device_id: str, message: dict) -> bool:
        if device_id in self.device_connections:
            try:
                await self.device_connections[device_id].send_text(json.dumps(message))
                return True
            except Exception:
                self.disconnect_device(device_id)
        return False

manager = ConnectionManager()
