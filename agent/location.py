"""
TrackGuard Windows Agent — Location Provider
Uses the location source reported by Windows, then falls back to approximate
IP geolocation when Windows Location Services is unavailable.
"""
import asyncio
import logging
import json
import subprocess
import sys
import platform

logger = logging.getLogger(__name__)


async def get_location() -> dict:
    """
    Get the best available location from Windows.
    Returns dict with latitude, longitude, accuracy, source.
    """
    # Try Windows Location API via PowerShell
    location = await _try_windows_location_api()
    if location:
        return location

    # Fallback: IP-based geolocation
    location = await _try_ip_geolocation()
    if location:
        return location

    return {
        "latitude": None,
        "longitude": None,
        "accuracy": None,
        "source": "unavailable",
    }


async def _try_windows_location_api() -> dict | None:
    """
    Try to get location using Windows Location Services via PowerShell.
    This uses the Windows.Devices.Geolocation API and reports its actual
    PositionSource instead of inferring a source from the reported accuracy.
    """
    if platform.system() != "Windows":
        return None

    ps_script = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

Function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Devices.Geolocation.Geolocator, Windows.Devices.Geolocation, ContentType=WindowsRuntime] | Out-Null
$geolocator = New-Object Windows.Devices.Geolocation.Geolocator
$geolocator.DesiredAccuracyInMeters = 100

try {
    $accessStatus = [Windows.Devices.Geolocation.Geolocator]::RequestAccessAsync()
    $access = Await $accessStatus ([Windows.Devices.Geolocation.GeolocationAccessStatus])

    if ($access -eq [Windows.Devices.Geolocation.GeolocationAccessStatus]::Allowed) {
        $geoTask = $geolocator.GetGeopositionAsync()
        $position = Await $geoTask ([Windows.Devices.Geolocation.Geoposition])
        $coord = $position.Coordinate

        $positionSource = "Default"
        try {
            $positionSource = $coord.PositionSource.ToString()
        } catch {}

        $source = switch ($positionSource) {
            "Satellite" { "gps"; break }
            "WiFi" { "wifi_location"; break }
            "Cellular" { "cellular_location"; break }
            "IPAddress" { "ip_geolocation"; break }
            default { "windows_location" }
        }

        $result = @{
            latitude = $coord.Point.Position.Latitude
            longitude = $coord.Point.Position.Longitude
            accuracy = $coord.Accuracy
            source = $source
        }
        $result | ConvertTo-Json
    } else {
        Write-Output '{"error": "access_denied"}'
    }
} catch {
    Write-Output ('{"error": "' + $_.Exception.Message + '"}')
}
"""

    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode("utf-8", errors="ignore").strip()

        if output:
            data = json.loads(output)
            latitude = data.get("latitude")
            longitude = data.get("longitude")
            if (
                "error" not in data
                and isinstance(latitude, (int, float))
                and isinstance(longitude, (int, float))
                and -90 <= latitude <= 90
                and -180 <= longitude <= 180
            ):
                return data
    except asyncio.TimeoutError:
        logger.warning("Windows Location API timed out")
    except Exception as e:
        logger.warning(f"Windows Location API error: {e}")

    return None


async def _try_ip_geolocation() -> dict | None:
    """Fallback: coarse IP geolocation; it is not a GPS fix."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://ipapi.co/json/")
            resp.raise_for_status()
            data = resp.json()
            lat = data.get("latitude")
            lon = data.get("longitude")
            if (
                isinstance(lat, (int, float))
                and isinstance(lon, (int, float))
                and -90 <= lat <= 90
                and -180 <= lon <= 180
            ):
                return {
                    "latitude": lat,
                    "longitude": lon,
                    "accuracy": None,
                    "source": "ip_geolocation",
                }
            logger.warning("IP geolocation returned no usable coordinates")
    except Exception as e:
        logger.warning(f"IP geolocation failed: {e}")

    return None
