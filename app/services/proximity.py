import math
from datetime import datetime, timedelta, timezone

from app.models import Device

FRESHNESS_LIMIT_MINUTES = 10
MAX_FIX_SKEW_MINUTES = 5
MOVING_STATES = {"DRIVING", "WALKING", "CYCLING", "MOVING", "RUNNING"}
STATIONARY_STATES = {"STATIONARY", "IDLE"}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def distance_meters(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    earth_radius_meters = 6_371_000
    lat1, lat2 = math.radians(first_latitude), math.radians(second_latitude)
    delta_latitude = lat2 - lat1
    delta_longitude = math.radians(second_longitude - first_longitude)
    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_longitude / 2) ** 2
    )
    haversine = min(1, max(0, haversine))
    return earth_radius_meters * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def _valid_coordinates(device: Device) -> bool:
    latitude = device.last_latitude
    longitude = device.last_longitude
    return (
        latitude is not None
        and longitude is not None
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def _valid_fix(device: Device, now: datetime) -> bool:
    timestamp = device.last_location_time
    if not _valid_coordinates(device) or timestamp is None:
        return False
    age_seconds = (now - _utc(timestamp)).total_seconds()
    return -120 <= age_seconds <= FRESHNESS_LIMIT_MINUTES * 60


def build_proximity_pair(
    first: Device,
    second: Device,
    *,
    now: datetime,
    threshold_meters: int,
) -> dict:
    first_valid = _valid_fix(first, now)
    second_valid = _valid_fix(second, now)
    distance = None
    status = "UNKNOWN"
    left_behind_name = None

    if (
        _valid_coordinates(first)
        and _valid_coordinates(second)
    ):
        distance = distance_meters(
            first.last_latitude,
            first.last_longitude,
            second.last_latitude,
            second.last_longitude,
        )

    fixes_synchronized = (
        first.last_location_time is not None
        and second.last_location_time is not None
        and abs(
            (_utc(first.last_location_time) - _utc(second.last_location_time)).total_seconds()
        ) <= MAX_FIX_SKEW_MINUTES * 60
    )
    if first_valid and second_valid and fixes_synchronized and distance is not None:
        status = "UNCERTAIN"
        if (
            first.last_accuracy is not None
            and second.last_accuracy is not None
            and first.last_accuracy >= 0
            and second.last_accuracy >= 0
        ):
            combined_accuracy = first.last_accuracy + second.last_accuracy
            if math.isfinite(combined_accuracy) and distance + combined_accuracy <= threshold_meters:
                status = "NEAR"
            elif (
                math.isfinite(combined_accuracy)
                and max(0, distance - combined_accuracy) > threshold_meters
            ):
                status = "SEPARATED"

        first_movement = (first.last_movement_state or "").upper()
        second_movement = (second.last_movement_state or "").upper()
        if status == "SEPARATED":
            if first_movement in MOVING_STATES and second_movement in STATIONARY_STATES:
                left_behind_name = second.name
            elif second_movement in MOVING_STATES and first_movement in STATIONARY_STATES:
                left_behind_name = first.name

    return {
        "first_device_id": first.id,
        "first_device_name": first.name,
        "first_location_time": first.last_location_time,
        "first_accuracy_meters": first.last_accuracy,
        "first_movement_state": first.last_movement_state,
        "second_device_id": second.id,
        "second_device_name": second.name,
        "second_location_time": second.last_location_time,
        "second_accuracy_meters": second.last_accuracy,
        "second_movement_state": second.last_movement_state,
        "last_known_distance_meters": round(distance, 1) if distance is not None else None,
        "threshold_meters": threshold_meters,
        "status": status,
        "possible_left_behind_device_name": left_behind_name,
    }


def build_proximity_snapshot(devices: list[Device], *, now: datetime, threshold_meters: int) -> dict:
    ordered = sorted(devices, key=lambda device: (device.name.casefold(), device.id))
    pairs = [
        build_proximity_pair(first, second, now=now, threshold_meters=threshold_meters)
        for index, first in enumerate(ordered)
        for second in ordered[index + 1 :]
    ]
    return {
        "generated_at": _utc(now),
        "threshold_meters": threshold_meters,
        "freshness_limit_minutes": FRESHNESS_LIMIT_MINUTES,
        "max_fix_skew_minutes": MAX_FIX_SKEW_MINUTES,
        "pairs": pairs,
    }
