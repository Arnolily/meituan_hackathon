import hashlib
import json
from pathlib import Path
from typing import Sequence

from planner.schemas import EventCommentGroup, EventPOIGroup


def build_comment_cache_key(
    *,
    poi_groups: Sequence[EventPOIGroup],
    review_file: Path,
    tip_file: Path,
    max_reviews_per_poi: int,
    max_tips_per_poi: int,
) -> str:
    payload = {
        "events": [
            {
                "event_index": group.event_index,
                "event_goal": group.event_goal,
                "business_ids": [poi.business_id for poi in group.pois],
            }
            for group in poi_groups
        ],
        "review_file": str(review_file.resolve()),
        "tip_file": str(tip_file.resolve()),
        "max_reviews_per_poi": max_reviews_per_poi,
        "max_tips_per_poi": max_tips_per_poi,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def get_comment_cache_path(
    *,
    cache_dir: Path,
    poi_groups: Sequence[EventPOIGroup],
    review_file: Path,
    tip_file: Path,
    max_reviews_per_poi: int,
    max_tips_per_poi: int,
) -> Path:
    cache_key = build_comment_cache_key(
        poi_groups=poi_groups,
        review_file=review_file,
        tip_file=tip_file,
        max_reviews_per_poi=max_reviews_per_poi,
        max_tips_per_poi=max_tips_per_poi,
    )
    return cache_dir / "comments" / f"{cache_key}.json"


def save_cached_comments(
    comment_groups: Sequence[EventCommentGroup],
    *,
    cache_dir: Path,
    poi_groups: Sequence[EventPOIGroup],
    review_file: Path,
    tip_file: Path,
    max_reviews_per_poi: int,
    max_tips_per_poi: int,
) -> Path:
    cache_path = get_comment_cache_path(
        cache_dir=cache_dir,
        poi_groups=poi_groups,
        review_file=review_file,
        tip_file=tip_file,
        max_reviews_per_poi=max_reviews_per_poi,
        max_tips_per_poi=max_tips_per_poi,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [group.model_dump() for group in comment_groups]
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path = cache_dir / "comments" / "latest_comments.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache_path
