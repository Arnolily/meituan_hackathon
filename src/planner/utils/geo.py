import math

from planner.schemas import AnchorPoint, GeoPoint


EARTH_RADIUS_KM = 6371.0
MODE_SPEED_KMH = {
    "walking": 4.5,
    "driving": 25.0,
    "transit": 18.0,
}


def haversine_distance_km(a: GeoPoint, b: GeoPoint) -> float:
    lat1 = math.radians(a.latitude)
    lon1 = math.radians(a.longitude)
    lat2 = math.radians(b.latitude)
    lon2 = math.radians(b.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    sin_dlat = math.sin(dlat / 2.0)
    sin_dlon = math.sin(dlon / 2.0)
    hav = sin_dlat * sin_dlat + math.cos(lat1) * math.cos(lat2) * sin_dlon * sin_dlon
    arc = 2.0 * math.atan2(math.sqrt(hav), math.sqrt(1.0 - hav))
    return EARTH_RADIUS_KM * arc


def estimate_travel_minutes(distance_km: float, mode: str) -> float:
    speed_kmh = MODE_SPEED_KMH.get(mode, MODE_SPEED_KMH["walking"])
    if speed_kmh <= 0:
        raise ValueError("Speed must be positive.")
    return (distance_km / speed_kmh) * 60.0


def anchor_to_point(anchor: AnchorPoint) -> GeoPoint:
    return GeoPoint(latitude=anchor.latitude, longitude=anchor.longitude)
