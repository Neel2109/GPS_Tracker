import asyncio
import json
import jwt
from datetime import datetime, timedelta
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.future import select
from app import models, security
from app.database import SessionLocal
from app.websocket_manager import manager

router = APIRouter(tags=["websocket"])


async def request_live_locations(device_id: str, user_id: str, response_received: asyncio.Event):
    while True:
        if manager.dashboard_connections.get(user_id):
            sent = await manager.send_to_device(device_id, {
                "type": "COMMAND",
                "command": "GET_LOCATION",
            })
            if not sent:
                return
            try:
                await asyncio.wait_for(response_received.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
            response_received.clear()
        await asyncio.sleep(1)

@router.websocket("/ws/dashboard/{user_id}")
async def dashboard_websocket(websocket: WebSocket, user_id: str, token: str = Query(...)):
    try:
        payload = jwt.decode(token, security.settings.jwt_secret, algorithms=[security.settings.jwt_algorithm])
        token_user_id = payload.get("sub")
        if token_user_id != user_id or payload.get("type") != "access":
            await websocket.close(code=1008)
            return
            
        async with SessionLocal() as db:
            result = await db.execute(select(models.User).where(models.User.id == user_id))
            if not result.scalar_one_or_none():
                await websocket.close(code=1008)
                return
                
        await manager.connect_dashboard(websocket, user_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                # Dashboard generally just receives data, but could send pings
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            manager.disconnect_dashboard(websocket, user_id)
            
    except Exception as e:
        await websocket.close(code=1008)

@router.websocket("/ws/device/{device_id}")
async def device_websocket(websocket: WebSocket, device_id: str, token: str = Query(...)):
    try:
        # Validate device token
        payload = jwt.decode(token, security.settings.jwt_secret, algorithms=[security.settings.jwt_algorithm])
        token_device_id = payload.get("sub")
        if token_device_id != device_id or not payload.get("is_device"):
            await websocket.close(code=1008)
            return
            
        async with SessionLocal() as db:
            result = await db.execute(select(models.Device).where(models.Device.id == device_id))
            device = result.scalar_one_or_none()
            if not device:
                await websocket.close(code=1008)
                return
                
            # Update status to online
            device.status = "online"
            device.last_seen = datetime.utcnow()
            await db.commit()
            
            # Notify dashboard
            await manager.send_to_dashboard(device.user_id, {
                "type": "DEVICE_STATUS",
                "device_id": device_id,
                "status": "online",
                "last_seen": device.last_seen.isoformat()
            })
            
        await manager.connect_device(websocket, device_id)
        await manager.send_to_device(device_id, {"type": "COMMAND", "command": "GET_STATUS"})
        location_response_received = asyncio.Event()
        location_task = asyncio.create_task(
            request_live_locations(device_id, device.user_id, location_response_received)
        )
        
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    msg_type = msg.get("type")
                    
                    async with SessionLocal() as db:
                        result = await db.execute(select(models.Device).where(models.Device.id == device_id))
                        device = result.scalar_one_or_none()
                        
                        if not device:
                            continue
                            
                        device.last_seen = datetime.utcnow()
                        
                        if msg_type == "HEARTBEAT":
                            pass # Just update last_seen
                            
                        elif msg_type == "STATUS_UPDATE":
                            payload = msg.get("data", {})
                            for key in [
                                "battery_level", "is_charging", "wifi_connected",
                                "network_type", "local_ip", "public_ip", "mac_address",
                                "platform", "model", "os_version", "cpu_info",
                                "ram_total", "storage_total",
                            ]:
                                if key in payload:
                                    setattr(device, key, payload[key])
                                    
                            await manager.send_to_dashboard(device.user_id, {
                                "type": "DEVICE_UPDATE",
                                "device_id": device_id,
                                "data": payload
                            })

                        elif msg_type == "BATTERY_UPDATE":
                            payload = msg.get("data", {})
                            for key in ["battery_level", "is_charging"]:
                                if key in payload:
                                    setattr(device, key, payload[key])

                            await manager.send_to_dashboard(device.user_id, {
                                "type": "BATTERY_UPDATE",
                                "device_id": device_id,
                                "data": payload,
                            })
                            
                        elif msg_type == "LOCATION_UPDATE":
                            loc = msg.get("data", {})
                            if "latitude" in loc and "longitude" in loc:
                                location_time = datetime.utcnow()
                                device.last_latitude = loc["latitude"]
                                device.last_longitude = loc["longitude"]
                                device.last_accuracy = loc.get("accuracy")
                                device.last_location_source = loc.get("source")
                                device.last_location_time = location_time
                                
                                latest_location_result = await db.execute(
                                    select(models.Location.timestamp)
                                    .where(models.Location.device_id == device_id)
                                    .order_by(models.Location.timestamp.desc())
                                    .limit(1)
                                )
                                latest_location_time = latest_location_result.scalar_one_or_none()
                                if (
                                    latest_location_time is None
                                    or location_time - latest_location_time >= timedelta(minutes=1)
                                ):
                                    db.add(models.Location(
                                        device_id=device_id,
                                        latitude=loc["latitude"],
                                        longitude=loc["longitude"],
                                        accuracy=loc.get("accuracy"),
                                        source=loc.get("source"),
                                    ))
                                
                                await manager.send_to_dashboard(device.user_id, {
                                    "type": "LOCATION_UPDATE",
                                    "device_id": device_id,
                                    "data": loc
                                })
                                
                        elif msg_type == "COMMAND_RESULT":
                            result_data = msg.get("data", msg)
                            cmd_id = result_data.get("command_id")
                            status = result_data.get("status")
                            result_text = result_data.get("result")

                            if result_data.get("command") == "GET_LOCATION":
                                location_response_received.set()
                            
                            cmd_result = await db.execute(select(models.Command).where(models.Command.id == cmd_id))
                            cmd = cmd_result.scalar_one_or_none()
                            if cmd:
                                cmd.status = status
                                cmd.result = result_text
                                cmd.executed_at = datetime.utcnow()
                                
                                await manager.send_to_dashboard(device.user_id, {
                                    "type": "COMMAND_RESULT",
                                    "device_id": device_id,
                                    "command_id": cmd_id,
                                    "status": status,
                                    "result": result_text
                                })
                                
                        await db.commit()
                        
                except json.JSONDecodeError:
                    if data == "ping":
                        await websocket.send_text("pong")
                        
        except WebSocketDisconnect:
            manager.disconnect_device(device_id)
            async with SessionLocal() as db:
                result = await db.execute(select(models.Device).where(models.Device.id == device_id))
                device = result.scalar_one_or_none()
                if device:
                    device.status = "offline"
                    device.last_seen = datetime.utcnow()
                    await db.commit()
                    
                    await manager.send_to_dashboard(device.user_id, {
                        "type": "DEVICE_STATUS",
                        "device_id": device_id,
                        "status": "offline",
                        "last_seen": device.last_seen.isoformat()
                    })
        finally:
            if not location_task.done():
                location_task.cancel()
            try:
                await location_task
            except asyncio.CancelledError:
                pass
                    
    except Exception as e:
        await websocket.close(code=1008)
