import hashlib
import json
from pathlib import Path
from typing import Optional, Sequence

from planner.schemas import EventCommentGroup, EventCommentSummaryGroup, Intent


def build_comment_summary_cache_key(
    *,
    intent: Intent,
    comment_groups: Sequence[EventCommentGroup],
    model: str,
    base_url: Optional[str],
) -> str:
    payload = {
        "raw_query": intent.raw_query,
        "overall_goal": intent.overall_goal,
        "events": [event.model_dump() for event in intent.events],
        "comment_groups": [
            {
                "event_index": group.event_index,
                "event_goal": group.event_goal,
                "business_ids": [bundle.business_id for bundle in group.bundles],
            }
            for group in comment_groups
        ],
        "model": model,
        "base_url": base_url or "",
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def get_comment_summary_cache_path(
    *,
    cache_dir: Path,
    intent: Intent,
    comment_groups: Sequence[EventCommentGroup],
    model: str,
    base_url: Optional[str],
) -> Path:
    cache_key = build_comment_summary_cache_key(
        intent=intent,
        comment_groups=comment_groups,
        model=model,
        base_url=base_url,
    )
    return cache_dir / "comment_summaries" / f"{cache_key}.json"


def save_cached_comment_summaries(
    summary_groups: Sequence[EventCommentSummaryGroup],
    *,
    cache_dir: Path,
    intent: Intent,
    comment_groups: Sequence[EventCommentGroup],
    model: str,
    base_url: Optional[str],
) -> Path:
    cache_path = get_comment_summary_cache_path(
        cache_dir=cache_dir,
        intent=intent,
        comment_groups=comment_groups,
        model=model,
        base_url=base_url,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [group.model_dump() for group in summary_groups]
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path = cache_dir / "comment_summaries" / "latest_comment_summaries.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache_path
