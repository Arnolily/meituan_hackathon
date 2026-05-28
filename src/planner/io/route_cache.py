from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

from planner.schemas import AnchorPoint, EventAggregatedPOIGroup, Intent, RouteCandidate, RouteTravelMode


def build_route_cache_key(
    *,
    intent: Intent,
    aggregated_groups: Sequence[EventAggregatedPOIGroup],
    mode: RouteTravelMode,
    anchor: AnchorPoint | None,
    max_pois_per_event: int,
    max_candidates: int,
    dwell_minutes_per_event: float,
    require_return: bool,
) -> str:
    payload = {
        "intent": {
            "raw_query": intent.raw_query,
            "city": intent.city,
            "events": [event.model_dump() for event in intent.events],
            "start_time": intent.start_time,
            "end_time": intent.end_time,
            "return_location": intent.return_location,
        },
        "aggregated_groups": [
            {
                "event_index": group.event_index,
                "event_goal": group.event_goal,
                "pois": [
                    {
                        "business_id": poi.business_id,
                        "latitude": poi.latitude,
                        "longitude": poi.longitude,
                        "aggregate_score": poi.aggregate_score,
                    }
                    for poi in group.pois
                ],
            }
            for group in aggregated_groups
        ],
        "mode": mode,
        "anchor": anchor.model_dump() if anchor is not None else None,
        "max_pois_per_event": max_pois_per_event,
        "max_candidates": max_candidates,
        "dwell_minutes_per_event": dwell_minutes_per_event,
        "require_return": require_return,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def get_route_cache_path(
    *,
    cache_dir: Path,
    intent: Intent,
    aggregated_groups: Sequence[EventAggregatedPOIGroup],
    mode: RouteTravelMode,
    anchor: AnchorPoint | None,
    max_pois_per_event: int,
    max_candidates: int,
    dwell_minutes_per_event: float,
    require_return: bool,
) -> Path:
    cache_key = build_route_cache_key(
        intent=intent,
        aggregated_groups=aggregated_groups,
        mode=mode,
        anchor=anchor,
        max_pois_per_event=max_pois_per_event,
        max_candidates=max_candidates,
        dwell_minutes_per_event=dwell_minutes_per_event,
        require_return=require_return,
    )
    return cache_dir / "routes" / f"{cache_key}.json"


def save_cached_routes(
    routes: Sequence[RouteCandidate],
    *,
    cache_dir: Path,
    intent: Intent,
    aggregated_groups: Sequence[EventAggregatedPOIGroup],
    mode: RouteTravelMode,
    anchor: AnchorPoint | None,
    max_pois_per_event: int,
    max_candidates: int,
    dwell_minutes_per_event: float,
    require_return: bool,
) -> Path:
    cache_path = get_route_cache_path(
        cache_dir=cache_dir,
        intent=intent,
        aggregated_groups=aggregated_groups,
        mode=mode,
        anchor=anchor,
        max_pois_per_event=max_pois_per_event,
        max_candidates=max_candidates,
        dwell_minutes_per_event=dwell_minutes_per_event,
        require_return=require_return,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [route.model_dump() for route in routes]
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path = cache_dir / "routes" / "latest_routes.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache_path
