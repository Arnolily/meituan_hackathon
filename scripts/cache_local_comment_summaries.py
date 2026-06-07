#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from planner.api import _local_comment_summary_groups
from planner.config import DEFAULT_CACHE_DIR
from planner.io.comment_summary_cache import save_cached_comment_summaries
from planner.io.intent_cache import load_intent_json
from planner.schemas import EventCommentGroup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Precompute cached comment summaries without calling a live model.")
    parser.add_argument("--intent-file", type=Path, default=DEFAULT_CACHE_DIR / "intents" / "latest_intent.json")
    parser.add_argument("--comments-file", type=Path, default=DEFAULT_CACHE_DIR / "comments" / "latest_comments.json")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    intent = load_intent_json(args.intent_file.read_text(encoding="utf-8"))
    comment_groups = [
        EventCommentGroup.model_validate(item)
        for item in json.loads(args.comments_file.read_text(encoding="utf-8"))
    ]
    summary_groups = _local_comment_summary_groups(intent=intent, comment_groups=comment_groups)
    cache_path = save_cached_comment_summaries(
        summary_groups,
        cache_dir=args.cache_dir,
        intent=intent,
        comment_groups=comment_groups,
        model="local_cache",
        base_url=None,
    )
    print(
        json.dumps(
            {
                "event_count": len(summary_groups),
                "total_summary_count": sum(len(group.summaries) for group in summary_groups),
                "cache_path": str(cache_path),
                "latest_path": str(args.cache_dir / "comment_summaries" / "latest_comment_summaries.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
