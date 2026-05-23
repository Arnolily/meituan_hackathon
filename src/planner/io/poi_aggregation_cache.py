import hashlib
import json
from pathlib import Path
from typing import Sequence

from planner.schemas import EventAggregatedPOIGroup, EventCommentSummaryGroup, EventPOIGroup


def build_poi_aggregation_cache_key(
    *,
    poi_groups: Sequence[EventPOIGroup],
    summary_groups: Sequence[EventCommentSummaryGroup],
) -> str:
    payload = {
        "poi_groups": [
            {
                "event_index": group.event_index,
                "event_goal": group.event_goal,
                "pois": [
                    {
                        "business_id": poi.business_id,
                        "retrieval_score": poi.retrieval_score,
                        "distance_to_anchor_km": poi.distance_to_anchor_km,
                        "estimated_travel_minutes": poi.estimated_travel_minutes,
                    }
                    for poi in group.pois
                ],
            }
            for group in poi_groups
        ],
        "summary_groups": [
            {
                "event_index": group.event_index,
                "event_goal": group.event_goal,
                "summaries": [
                    {
                        "business_id": summary.business_id,
                        "confidence": summary.confidence,
                        "keywords": summary.keywords,
                        "pros": summary.pros,
                        "cons": summary.cons,
                        "notable_risks": summary.notable_risks,
                    }
                    for summary in group.summaries
                ],
            }
            for group in summary_groups
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def get_poi_aggregation_cache_path(
    *,
    cache_dir: Path,
    poi_groups: Sequence[EventPOIGroup],
    summary_groups: Sequence[EventCommentSummaryGroup],
) -> Path:
    cache_key = build_poi_aggregation_cache_key(poi_groups=poi_groups, summary_groups=summary_groups)
    return cache_dir / "aggregated_pois" / f"{cache_key}.json"


def save_cached_aggregated_pois(
    aggregated_groups: Sequence[EventAggregatedPOIGroup],
    *,
    cache_dir: Path,
    poi_groups: Sequence[EventPOIGroup],
    summary_groups: Sequence[EventCommentSummaryGroup],
) -> Path:
    cache_path = get_poi_aggregation_cache_path(
        cache_dir=cache_dir,
        poi_groups=poi_groups,
        summary_groups=summary_groups,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [group.model_dump() for group in aggregated_groups]
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path = cache_dir / "aggregated_pois" / "latest_aggregated_pois.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache_path
