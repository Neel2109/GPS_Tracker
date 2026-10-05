import asyncio
import base64
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas, security
from app.database import get_db

router = APIRouter(prefix="/api/devices", tags=["devices"])

def generate_pairing_code():
    return secrets.token_urlsafe(32)

def make_installer_executable(pairing_code: str, device_name: str, server_url: str) -> bytes:
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="Windows installer generation must run on a Windows server")

    project_root = Path(__file__).resolve().parents[2]
    agent_dir = project_root / "agent"
    setup_script = project_root / "installer" / "TrackGuardSetup.pyw"
    builder_python = project_root / ".venv" / "Scripts" / "python.exe"
    if not builder_python.is_file():
        builder_python = Path(sys.executable)

    if not agent_dir.is_dir() or not setup_script.is_file():
        raise HTTPException(status_code=500, detail="Windows agent installer files are missing")

    with tempfile.TemporaryDirectory(prefix="trackguard-installer-") as temp_dir:
        build_dir = Path(temp_dir)
        payload_dir = build_dir / "payload"
        payload_dir.mkdir()
        bundled_agent_dir = build_dir / "agent"
        bundled_agent_dir.mkdir()
        for source in agent_dir.glob("*.py"):
            shutil.copy2(source, bundled_agent_dir / source.name)
        (payload_dir / "installer_payload.json").write_text(
            json.dumps({
                "server_url": server_url,
                "pairing_code": pairing_code,
                "device_name": device_name,
            }),
            encoding="utf-8",
        )
        executable_path = build_dir / "dist" / "TrackGuardSetup.exe"
        command = [
            str(builder_python),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile",
            "--windowed",
            "--name",
            "TrackGuardSetup",
            "--distpath",
            str(build_dir / "dist"),
            "--workpath",
            str(build_dir / "work"),
            "--specpath",
            str(build_dir / "spec"),
            "--paths",
            str(bundled_agent_dir),
            "--add-data",
            f"{bundled_agent_dir};agent",
            "--add-data",
            f"{payload_dir / 'installer_payload.json'};.",
            "--hidden-import",
            "websockets",
            "--hidden-import",
            "httpx",
            "--hidden-import",
            "psutil",
            str(setup_script),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=503,
                detail="The Windows EXE builder is unavailable. Install installer/requirements-build.txt on the server.",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise HTTPException(status_code=504, detail="Windows installer build timed out; please try again") from error

        if result.returncode != 0 or not executable_path.is_file():
            build_output = (result.stderr or result.stdout or "PyInstaller did not produce an executable").strip()
            raise HTTPException(status_code=500, detail=f"Windows installer build failed: {build_output[-1800:]}")

        return executable_path.read_bytes()

@router.get("", response_model=List[schemas.DeviceResponse])
async def list_devices(
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(models.Device.user_id == current_user.id))
    return result.scalars().all()

@router.post("/pair/generate", response_model=schemas.PairingCodeResponse)
async def generate_code(
    device_info: schemas.DeviceBase,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    code = generate_pairing_code()
    expires = datetime.utcnow() + timedelta(minutes=10)
    
    db_code = models.PairingCode(
        code=code,
        user_id=current_user.id,
        device_name=device_info.name,
        device_type=device_info.device_type,
        expires_at=expires
    )
    db.add(db_code)
    await db.commit()
    await db.refresh(db_code)
    return db_code

@router.post("/pair/installer", response_model=schemas.DeviceInstallerResponse)
async def generate_device_installer(
    installer_info: schemas.DeviceInstallerRequest,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    server_url = installer_info.server_url.strip().rstrip("/")
    try:
        parsed_server_url = urlsplit(server_url)
        valid_port = parsed_server_url.port is None or 1 <= parsed_server_url.port <= 65535
    except ValueError:
        valid_port = False
        parsed_server_url = urlsplit("")
    if (
        parsed_server_url.scheme not in ("http", "https")
        or not parsed_server_url.hostname
        or parsed_server_url.username is not None
        or parsed_server_url.password is not None
        or parsed_server_url.query
        or parsed_server_url.fragment
        or parsed_server_url.path not in ("", "/")
        or not valid_port
        or any(char.isspace() for char in server_url)
    ):
        raise HTTPException(status_code=422, detail="Server address must start with http:// or https://")

    code = generate_pairing_code()
    expires = datetime.utcnow() + timedelta(hours=24)
    pairing = models.PairingCode(
        code=code,
        user_id=current_user.id,
        device_name=installer_info.name.strip(),
        device_type=installer_info.device_type,
        expires_at=expires,
    )
    installer = await asyncio.to_thread(
        make_installer_executable,
        code,
        pairing.device_name,
        server_url,
    )
    db.add(pairing)
    await db.commit()

    filename = f"TrackGuard-{''.join(c for c in pairing.device_name if c.isalnum() or c in '-_') or 'Device'}-Setup.exe"
    return {
        "filename": filename,
        "content_base64": base64.b64encode(installer).decode("ascii"),
        "device_name": pairing.device_name,
        "expires_at": expires,
    }

@router.post("/pair/activate", response_model=schemas.DevicePairingResponse)
async def activate_device(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    # Find active pairing code
    result = await db.execute(select(models.PairingCode).where(
        models.PairingCode.code == code,
        models.PairingCode.expires_at > datetime.utcnow()
    ))
    pairing = result.scalar_one_or_none()
    
    if not pairing:
        raise HTTPException(status_code=400, detail="Invalid or expired pairing code")
        
    # Create the device
    device_id = str(uuid.uuid4())
    db_device = models.Device(
        id=device_id,
        user_id=pairing.user_id,
        name=pairing.device_name,
        device_type=pairing.device_type,
        status="offline"
    )
    db.add(db_device)
    
    # Remove the pairing code so it can't be used again
    await db.delete(pairing)
    await db.commit()
    
    # Create device token
    # We use a special token format for devices to distinguish them from users
    access_token = security.create_access_token(data={"sub": device_id, "is_device": True}, expires_delta=timedelta(days=3650))
    
    # The agent stores these credentials for its authenticated WebSocket connection.
    return {
        "id": device_id,
        "device_token": access_token,
        "name": db_device.name,
    }

@router.get("/{device_id}", response_model=schemas.DeviceResponse)
async def get_device(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    await db.delete(device)
    await db.commit()
    return {"message": "Device deleted"}

@router.post("/{device_id}/lost-mode/enable")
async def enable_lost_mode(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    device.is_lost_mode = True
    await db.commit()
    
    from app.websocket_manager import manager
    await manager.send_to_dashboard(current_user.id, {"type": "LOST_MODE_ENABLED", "device_id": device_id})
    await manager.send_to_device(device_id, {"type": "ENABLE_LOST_MODE", "data": {"interval": 10}})
    
    return {"message": "Lost mode enabled", "is_lost_mode": True}

@router.post("/{device_id}/lost-mode/disable")
async def disable_lost_mode(
    device_id: str,
    current_user: models.User = Depends(security.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(models.Device).where(
        models.Device.id == device_id,
        models.Device.user_id == current_user.id
    ))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    device.is_lost_mode = False
    await db.commit()
    
    from app.websocket_manager import manager
    await manager.send_to_dashboard(current_user.id, {"type": "LOST_MODE_DISABLED", "device_id": device_id})
    await manager.send_to_device(device_id, {"type": "DISABLE_LOST_MODE"})
    
    return {"message": "Lost mode disabled", "is_lost_mode": False}
