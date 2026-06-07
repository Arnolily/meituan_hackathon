from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Protocol

from planner.modules.ors_client import OpenRouteServiceClientError
from planner.schemas import (
    AggregatedPOI,
    AnchorPoint,
    EventAggregatedPOIGroup,
    Intent,
    RouteCandidate,
    RouteLeg,
    RouteStop,
    RouteTravelMode,
)
from planner.utils.geo import haversine_distance_km


EventOption = tuple[EventAggregatedPOIGroup, AggregatedPOI]


class DirectionClient(Protocol):
    def route(self, *, stops: list[RouteStop], mode: RouteTravelMode) -> list[RouteLeg]: ...


def find_route_candidates(
    *,
    intent: Intent,
    aggregated_groups: list[EventAggregatedPOIGroup],
    direction_client: DirectionClient,
    mode: RouteTravelMode = "walking",
    anchor: AnchorPoint | None = None,
    max_pois_per_event: int = 5,
    max_candidates: int = 20,
    dwell_minutes_per_event: float = 45.0,
    require_return: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[RouteCandidate]:
    grouped_options = [_top_pois_for_event(group, max_pois_per_event) for group in aggregated_groups]
    grouped_options = [options for options in grouped_options if options]
    if not grouped_options:
        return []

    candidates: list[RouteCandidate] = []
    route_options = _rank_route_options(
        grouped_options=grouped_options,
        anchor=anchor,
        require_return=require_return,
        limit=max_candidates,
    )
    def build_candidate(poi_tuple: tuple[EventOption, ...]) -> RouteCandidate:
        stops = _build_stops(
            poi_tuple,
            anchor=anchor,
            dwell_minutes_per_event=dwell_minutes_per_event,
            require_return=require_return,
        )
        legs = _build_legs(stops, direction_client=direction_client, mode=mode)
        return _score_candidate(stops=stops, legs=legs, mode=mode)

    total = len(route_options)
    with ThreadPoolExecutor(max_workers=min(3, total)) as executor:
        futures = [executor.submit(build_candidate, poi_tuple) for poi_tuple in route_options]
        for completed, future in enumerate(as_completed(futures), start=1):
            candidates.append(future.result())
            if progress_callback is not None:
                progress_callback(completed, total)

    candidates.sort(key=lambda candidate: (-candidate.feasible, -candidate.score, candidate.total_travel_seconds))
    return candidates


def _top_pois_for_event(group: EventAggregatedPOIGroup, limit: int) -> list[EventOption]:
    pois = sorted(
        group.pois,
        key=lambda poi: (
            -poi.aggregate_score,
            -poi.retrieval_score,
            -poi.review_count,
            poi.name,
        ),
    )
    return [(group, poi) for poi in pois[: max(limit, 1)]]


def _rank_route_options(
    *,
    grouped_options: list[list[EventOption]],
    anchor: AnchorPoint | None,
    require_return: bool,
    limit: int,
) -> list[tuple[EventOption, ...]]:
    beam_width = max(limit * 4, 20)
    partials: list[tuple[tuple[EventOption, ...], float]] = [(tuple(), 0.0)]
    for options in grouped_options:
        expanded: list[tuple[tuple[EventOption, ...], float]] = []
        for current, _ in partials:
            for option in options:
                route = current + (option,)
                expanded.append((route, _estimate_route_quality(route, anchor=anchor, require_return=require_return)))
        expanded.sort(key=lambda item: item[1], reverse=True)
        partials = expanded[:beam_width]
    return [route for route, _ in partials[: max(limit, 1)]]


def _estimate_route_quality(
    route: tuple[EventOption, ...],
    *,
    anchor: AnchorPoint | None,
    require_return: bool,
) -> float:
    poi_score = sum(poi.aggregate_score for _, poi in route)
    distance_km = 0.0
    previous = anchor
    for _, poi in route:
        if previous is not None:
            distance_km += haversine_distance_km(previous, poi)
        previous = poi
    if require_return and anchor is not None and previous is not None:
        distance_km += haversine_distance_km(previous, anchor)
    return poi_score - distance_km


def _build_stops(
    pois: tuple[EventOption, ...],
    *,
    anchor: AnchorPoint | None,
    dwell_minutes_per_event: float,
    require_return: bool,
) -> list[RouteStop]:
    stops: list[RouteStop] = []
    if anchor is not None:
        stops.append(
            RouteStop(
                kind="anchor",
                name=anchor.name,
                latitude=anchor.latitude,
                longitude=anchor.longitude,
            )
        )

    for group, poi in pois:
        stops.append(
            RouteStop(
                kind="poi",
                name=poi.name,
                latitude=poi.latitude,
                longitude=poi.longitude,
                business_id=poi.business_id,
                event_index=group.event_index,
                event_name=group.event_name,
                dwell_minutes=dwell_minutes_per_event,
                aggregate_score=poi.aggregate_score,
            )
        )

    if require_return and anchor is not None:
        stops.append(
            RouteStop(
                kind="anchor",
                name=anchor.name,
                latitude=anchor.latitude,
                longitude=anchor.longitude,
            )
        )
    return stops


def _build_legs(
    stops: list[RouteStop],
    *,
    direction_client: DirectionClient,
    mode: RouteTravelMode,
) -> list[RouteLeg]:
    try:
        return direction_client.route(stops=stops, mode=mode)
    except OpenRouteServiceClientError as exc:
        return [
            RouteLeg(
                origin_name=origin.name,
                destination_name=destination.name,
                mode=mode,
                provider="openrouteservice",
                provider_status="failed",
                provider_info=str(exc),
            )
            for origin, destination in zip(stops, stops[1:])
        ]


def _score_candidate(*, stops: list[RouteStop], legs: list[RouteLeg], mode: RouteTravelMode) -> RouteCandidate:
    warnings: list[str] = []
    total_distance = 0.0
    total_travel = 0.0
    for leg in legs:
        if leg.provider_status != "ok":
            warnings.append(f"{leg.origin_name} -> {leg.destination_name}: {leg.provider_info or leg.provider_status}")
        if leg.distance_meters is not None:
            total_distance += leg.distance_meters
        if leg.duration_seconds is not None:
            total_travel += leg.duration_seconds
        else:
            warnings.append(f"{leg.origin_name} -> {leg.destination_name}: missing travel duration")

    total_dwell = sum(stop.dwell_minutes for stop in stops)
    total_poi_score = sum(stop.aggregate_score for stop in stops if stop.kind == "poi")
    feasible = not warnings
    travel_penalty = total_travel / 600.0
    distance_penalty = total_distance / 5000.0
    feasibility_penalty = 50.0 if warnings else 0.0
    score = round(total_poi_score - travel_penalty - distance_penalty - feasibility_penalty, 3)
    route_id = _build_route_id(stops=stops, mode=mode)
    poi_names = [stop.name for stop in stops if stop.kind == "poi"]
    explanation = (
        f"{' -> '.join(poi_names)}; travel {round(total_travel / 60.0, 1)} min, "
        f"dwell {round(total_dwell, 1)} min, POI score {round(total_poi_score, 2)}."
    )
    if warnings:
        explanation += " Provider warnings need review."

    return RouteCandidate(
        route_id=route_id,
        mode=mode,
        stops=stops,
        legs=legs,
        total_distance_meters=round(total_distance, 2),
        total_travel_seconds=round(total_travel, 2),
        total_dwell_minutes=round(total_dwell, 2),
        total_poi_score=round(total_poi_score, 3),
        score=score,
        feasible=feasible,
        feasibility_warnings=warnings,
        explanation=explanation,
    )


def _build_route_id(*, stops: list[RouteStop], mode: RouteTravelMode) -> str:
    payload = {
        "mode": mode,
        "stops": [
            {
                "kind": stop.kind,
                "name": stop.name,
                "business_id": stop.business_id,
                "lat": round(stop.latitude, 6),
                "lng": round(stop.longitude, 6),
            }
            for stop in stops
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]
