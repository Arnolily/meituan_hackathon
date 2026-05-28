from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from planner.schemas import RouteLeg, RouteStop, RouteTravelMode


ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions"
ORS_PROFILES: dict[RouteTravelMode, str] = {
    "walking": "foot-walking",
    "driving": "driving-car",
    "cycling": "cycling-regular",
}


class OpenRouteServiceClientError(RuntimeError):
    pass


class OpenRouteServiceDirectionClient:
    def __init__(self, *, api_key: str, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def route(self, *, stops: list[RouteStop], mode: RouteTravelMode) -> list[RouteLeg]:
        if mode not in ORS_PROFILES:
            raise OpenRouteServiceClientError(f"OpenRouteService does not support mode: {mode}")
        if len(stops) < 2:
            return []

        profile = ORS_PROFILES[mode]
        legs: list[RouteLeg] = []
        for origin, destination in zip(stops, stops[1:]):
            response = self._request(
                profile=profile,
                origin=origin,
                destination=destination,
            )
            legs.extend(parse_ors_route(response, stops=[origin, destination], mode=mode))
        return legs

    def _request(self, *, profile: str, origin: RouteStop, destination: RouteStop) -> dict[str, Any]:
        query = urlencode(
            {
                "api_key": self.api_key,
                "start": _format_coordinate(origin),
                "end": _format_coordinate(destination),
            }
        )
        request = Request(
            f"{ORS_BASE_URL}/{profile}?{query}",
            headers={
                "Accept": "application/geo+json, application/json",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenRouteServiceClientError(f"ORS HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # pragma: no cover - exercised through caller behavior.
            raise OpenRouteServiceClientError(f"ORS request failed: {exc}") from exc


def parse_ors_route(payload: dict[str, Any], *, stops: list[RouteStop], mode: RouteTravelMode) -> list[RouteLeg]:
    features = payload.get("features") or []
    if not features:
        return _failed_legs(stops=stops, mode=mode, message="ORS response did not include a route feature")

    feature = features[0]
    properties = feature.get("properties") or {}
    segments = properties.get("segments") or []
    geometry = feature.get("geometry") or {}
    route_polyline = _parse_geojson_coordinates(geometry.get("coordinates") or [])

    legs: list[RouteLeg] = []
    for index, (origin, destination) in enumerate(zip(stops, stops[1:])):
        segment = segments[index] if index < len(segments) and isinstance(segments[index], dict) else {}
        legs.append(
            RouteLeg(
                origin_name=origin.name,
                destination_name=destination.name,
                mode=mode,
                distance_meters=_to_float(segment.get("distance")),
                duration_seconds=_to_float(segment.get("duration")),
                polyline=route_polyline if index == 0 else [],
                provider="openrouteservice",
                provider_status="ok",
                raw_path_count=1,
            )
        )
    return legs


def _failed_legs(*, stops: list[RouteStop], mode: RouteTravelMode, message: str) -> list[RouteLeg]:
    return [
        RouteLeg(
            origin_name=origin.name,
            destination_name=destination.name,
            mode=mode,
            provider="openrouteservice",
            provider_status="failed",
            provider_info=message,
        )
        for origin, destination in zip(stops, stops[1:])
    ]


def _parse_geojson_coordinates(coordinates: list[Any]) -> list[list[float]]:
    points: list[list[float]] = []
    for coordinate in coordinates:
        if not isinstance(coordinate, list) or len(coordinate) < 2:
            continue
        try:
            longitude = float(coordinate[0])
            latitude = float(coordinate[1])
        except (TypeError, ValueError):
            continue
        points.append([latitude, longitude])
    return points


def _format_coordinate(stop: RouteStop) -> str:
    return f"{stop.longitude:.8f},{stop.latitude:.8f}"


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
