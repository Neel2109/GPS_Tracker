import asyncio
import json
import jwt
import math
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.future import select
from app import models, schemas, security
from app.database import SessionLocal
from app.services.admin_live import queue_authorized_admin_location_updates
from app.services.geofences import record_geofence_transitions
from app.services.incidents import synchronize_device_incidents
from app.websocket_manager import manager

router = APIRouter(tags=["websocket"])


def update_device_tracking_state(device, *, reason: str = "heartbeat"):
    device.last_seen = datetime.utcnow()
    device.status = models.resolve_device_status(
        status=device.status,
        last_seen=device.last_seen,
        last_online=device.last_online,
        last_offline=device.last_offline,
        offline_since=device.offline_since,
        last_location_time=device.last_location_time,
        last_latitude=device.last_latitude,
        last_longitude=device.last_longitude,
        connection_state=device.connection_state,
    )
    device.connection_state = device.status

    if device.status == "online":
        device.last_online = device.last_online or device.last_seen
        device.offline_since = None
    elif device.offline_since is None:
        device.offline_since = device.last_seen

    if device.status in {"offline", "recently_offline", "sleeping", "powered_off", "location_unavailable", "unknown"}:
        device.last_offline = device.last_offline or device.last_seen

    if device.battery_level is not None:
        device.last_battery = device.battery_level
    if device.public_ip is not None:
        device.last_ip = device.public_ip
    elif device.local_ip is not None:
        device.last_ip = device.local_ip
    if device.network_type is not None:
        device.last_network = device.network_type

    return device


def haversine_distance(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')
    R = 6371000  # radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

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
                
            device.status = "online"
            device.connection_state = "online"
            device.last_seen = datetime.utcnow()
            device.last_online = device.last_online or device.last_seen
            device.last_offline = device.last_offline
            lost_mode_enabled = device.is_lost_mode
            connection_alerts = await synchronize_device_incidents(
                db,
                device,
                connected=True,
            )
            await db.commit()
            
            # Notify dashboard
            await manager.send_to_dashboard(device.user_id, {
                "type": "DEVICE_STATUS",
                "device_id": device_id,
                "status": "online",
                "last_seen": device.last_seen.isoformat()
            })
            for alert in connection_alerts:
                await db.refresh(alert)
                await manager.send_to_dashboard(device.user_id, {
                    "type": "ALERT_CREATED" if alert.status == "OPEN" else "ALERT_UPDATED",
                    "device_id": alert.device_id,
                    "data": schemas.AlertResponse.model_validate(alert).model_dump(mode="json"),
                })
            
        await manager.connect_device(websocket, device_id)
        await manager.send_to_device(device_id, {"type": "COMMAND", "command": "GET_STATUS"})
        await manager.send_to_device(
            device_id,
            {"type": "ENABLE_LOST_MODE" if lost_mode_enabled else "DISABLE_LOST_MODE"},
        )
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

                        pending_alerts: list[models.Alert] = []
                        admin_live_updates: list[tuple[str, dict]] = []
                            
                        device.last_seen = datetime.utcnow()
                        if msg_type == "HEARTBEAT":
                            device = update_device_tracking_state(device)
                            
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

                            if "battery_level" in payload and payload["battery_level"] is not None:
                                device.last_battery = payload["battery_level"]
                            if "network_type" in payload and payload["network_type"] is not None:
                                device.last_network = payload["network_type"]
                            if "public_ip" in payload and payload["public_ip"] is not None:
                                device.last_ip = payload["public_ip"]
                            elif "local_ip" in payload and payload["local_ip"] is not None:
                                device.last_ip = payload["local_ip"]

                            device = update_device_tracking_state(device)

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

                            if "battery_level" in payload and payload["battery_level"] is not None:
                                device.last_battery = payload["battery_level"]

                            device = update_device_tracking_state(device)

                            await manager.send_to_dashboard(device.user_id, {
                                "type": "BATTERY_UPDATE",
                                "device_id": device_id,
                                "data": payload,
                            })
                            
                        elif msg_type == "LOCATION_UPDATE":
                            loc = msg.get("data", {})
                            if "latitude" in loc and "longitude" in loc:
                                location_time = datetime.utcnow()
                                raw_timestamp = loc.get("timestamp")
                                if isinstance(raw_timestamp, str):
                                    try:
                                        parsed_timestamp = datetime.fromisoformat(
                                            raw_timestamp.replace("Z", "+00:00")
                                        )
                                        location_time = (
                                            parsed_timestamp.astimezone(timezone.utc).replace(tzinfo=None)
                                            if parsed_timestamp.tzinfo is not None
                                            else parsed_timestamp
                                        )
                                    except ValueError:
                                        pass
                                movement_state = "STATIONARY"
                                speed = loc.get("speed", 0)
                                heading = loc.get("heading")

                                if speed is not None and speed > 2:
                                    if speed > 30:
                                        movement_state = "DRIVING"
                                    elif speed > 8:
                                        movement_state = "CYCLING"
                                    else:
                                        movement_state = "WALKING"

                                device.last_latitude = loc["latitude"]
                                device.last_longitude = loc["longitude"]
                                device.last_accuracy = loc.get("accuracy")
                                device.last_location_source = loc.get("source")
                                device.last_location_time = location_time
                                device.last_movement_state = movement_state
                                device.last_speed = speed
                                device.last_heading = heading
                                device.status = "online"
                                device.connection_state = "online"
                                if device.last_online is None:
                                    device.last_online = location_time
                                
                                latest_location_result = await db.execute(
                                    select(models.Location)
                                    .where(models.Location.device_id == device_id)
                                    .order_by(models.Location.timestamp.desc())
                                    .limit(1)
                                )
                                latest_location = latest_location_result.scalar_one_or_none()

                                should_save = False

                                if latest_location is None:
                                    should_save = True
                                else:
                                    distance = haversine_distance(
                                        loc["latitude"], loc["longitude"],
                                        latest_location.latitude, latest_location.longitude
                                    )
                                    time_diff = location_time - latest_location.timestamp

                                    # Save if distance > 10 meters OR time difference > 5 minutes
                                    if distance > 10 or time_diff >= timedelta(minutes=5):
                                        should_save = True

                                if should_save:
                                    location = models.Location(
                                        device_id=device_id,
                                        latitude=loc["latitude"],
                                        longitude=loc["longitude"],
                                        accuracy=loc.get("accuracy"),
                                        altitude=loc.get("altitude"),
                                        speed=speed,
                                        heading=heading,
                                        source=loc.get("source"),
                                        movement_state=movement_state,
                                        timestamp=location_time,
                                    )
                                    db.add(location)
                                    pending_alerts = await record_geofence_transitions(
                                        db,
                                        device,
                                        [location],
                                    )
                                
                                device = update_device_tracking_state(device)

                                await manager.send_to_dashboard(device.user_id, {
                                    "type": "LOCATION_UPDATE",
                                    "device_id": device_id,
                                    "data": {**loc, "movement_state": movement_state}
                                })
                                admin_live_updates.extend(
                                    await queue_authorized_admin_location_updates(
                                        db,
                                        device,
                                        {
                                            "latitude": device.last_latitude,
                                            "longitude": device.last_longitude,
                                            "accuracy": device.last_accuracy,
                                            "source": device.last_location_source,
                                            "timestamp": (
                                                device.last_location_time.isoformat()
                                                if device.last_location_time
                                                else None
                                            ),
                                            "movement_state": movement_state,
                                            "speed": device.last_speed,
                                        },
                                    )
                                )
                                
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
                                if cmd.user_id != device.user_id:
                                    requester = await db.get(models.User, cmd.user_id)
                                    if (
                                        requester
                                        and requester.account_status == "ACTIVE"
                                        and requester.role in {"ADMIN", "SUPER_ADMIN"}
                                    ):
                                        db.add(models.AdminAuditEvent(
                                            actor_user_id=requester.id,
                                            action="ADMIN_DEVICE_COMMAND_RESULT_RECEIVED",
                                            target_user_id=device.user_id,
                                            target_device_id=device.id,
                                            details=(
                                                f"command_id={cmd.id}; command={cmd.command}; "
                                                f"status={status}"
                                            ),
                                        ))
                                        await manager.send_to_dashboard(requester.id, {
                                            "type": "ADMIN_COMMAND_RESULT",
                                            "device_id": device.id,
                                            "command_id": cmd.id,
                                            "command": cmd.command,
                                            "status": status,
                                            "result": result_text,
                                        })
                        if msg_type in {
                            "HEARTBEAT",
                            "STATUS_UPDATE",
                            "BATTERY_UPDATE",
                            "LOCATION_UPDATE",
                        }:
                            pending_alerts.extend(
                                await synchronize_device_incidents(
                                    db,
                                    device,
                                    connected=True,
                                )
                            )

                        await db.commit()
                        for admin_user_id, live_update in admin_live_updates:
                            await manager.send_to_dashboard(admin_user_id, live_update)
                        for alert in pending_alerts:
                            await db.refresh(alert)
                            await manager.send_to_dashboard(device.user_id, {
                                "type": "ALERT_CREATED" if alert.status == "OPEN" else "ALERT_UPDATED",
                                "device_id": alert.device_id,
                                "data": schemas.AlertResponse.model_validate(alert).model_dump(mode="json"),
                            })
                        
                except json.JSONDecodeError:
                    if data == "ping":
                        await websocket.send_text("pong")
                        
        except WebSocketDisconnect:
            manager.disconnect_device(device_id)
            async with SessionLocal() as db:
                result = await db.execute(select(models.Device).where(models.Device.id == device_id))
                device = result.scalar_one_or_none()
                if device:
                    device.last_seen = datetime.utcnow()
                    device.last_offline = device.last_offline or device.last_seen
                    device.offline_since = device.offline_since or device.last_seen
                    device.status = models.resolve_device_status(
                        status="offline",
                        last_seen=device.last_seen,
                        last_online=device.last_online,
                        last_offline=device.last_offline,
                        offline_since=device.offline_since,
                        last_location_time=device.last_location_time,
                        last_latitude=device.last_latitude,
                        last_longitude=device.last_longitude,
                        connection_state="offline",
                    )
                    device.connection_state = device.status

                    if device.battery_level is not None:
                        device.last_battery = device.battery_level
                    if device.public_ip is not None:
                        device.last_ip = device.public_ip
                    elif device.local_ip is not None:
                        device.last_ip = device.local_ip
                    if device.network_type is not None:
                        device.last_network = device.network_type

                    db.add(models.OfflineSession(
                        device_id=device.id,
                        started_at=device.last_online or device.last_seen,
                        ended_at=device.last_seen,
                        reason="SERVER_CONNECTION_LOST",
                        last_known_latitude=device.last_latitude,
                        last_known_longitude=device.last_longitude,
                        last_known_accuracy=device.last_accuracy,
                        last_known_battery=device.last_battery,
                        last_known_ip=device.last_ip,
                    ))
                    offline_alerts = await synchronize_device_incidents(
                        db,
                        device,
                        connected=False,
                    )
                    await db.commit()

                    await manager.send_to_dashboard(device.user_id, {
                        "type": "DEVICE_STATUS",
                        "device_id": device_id,
                        "status": device.status,
                        "last_seen": device.last_seen.isoformat()
                    })
                    for alert in offline_alerts:
                        await db.refresh(alert)
                        await manager.send_to_dashboard(device.user_id, {
                            "type": "ALERT_CREATED" if alert.status == "OPEN" else "ALERT_UPDATED",
                            "device_id": alert.device_id,
                            "data": schemas.AlertResponse.model_validate(alert).model_dump(mode="json"),
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
