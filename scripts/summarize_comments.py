#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from planner.config import DEFAULT_CACHE_DIR, load_env_file
from planner.io.comment_summary_cache import save_cached_comment_summaries
from planner.io.intent_cache import load_intent_json
from planner.llm.client import OpenAICompatibleClient
from planner.modules.comment_summarizer import summarize_event_comment_groups
from planner.schemas import EventCommentGroup, Intent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize cached POI comments with an intent-conditioned LLM call.")
    parser.add_argument(
        "--intent-file",
        type=Path,
        default=DEFAULT_CACHE_DIR / "intents" / "latest_intent.json",
        help="Path to the cached intent JSON file.",
    )
    parser.add_argument(
        "--comments-file",
        type=Path,
        default=DEFAULT_CACHE_DIR / "comments" / "latest_comments.json",
        help="Path to the cached grouped comment JSON file.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Cache directory for comment summary JSON artifacts.",
    )
    parser.add_argument("--max-summaries-per-event", type=int, default=10, help="Maximum POIs to summarize per event.")
    parser.add_argument("--batch-size", type=int, default=7, help="Number of POIs to summarize per LLM call.")
    parser.add_argument("--max-parallel-batches", type=int, default=2, help="Maximum LLM batch requests to run at once.")
    parser.add_argument("--batch-retries", type=int, default=3, help="Number of times to retry a failed batch.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env_settings = load_env_file()
    api_key = env_settings.get("OPENAI_API_KEY")
    model = env_settings.get("OPENAI_MODEL")
    base_url = env_settings.get("OPENAI_BASE_URL")
    timeout = float(env_settings.get("OPENAI_TIMEOUT_SEC", "60"))
    if not api_key or not model:
        raise SystemExit("Missing OPENAI_API_KEY or OPENAI_MODEL in .env.local.")

    intent = load_intent_json(args.intent_file.read_text(encoding="utf-8"))
    comment_groups = load_comment_groups(args.comments_file)
    client = OpenAICompatibleClient(api_key=api_key, base_url=base_url, model=model, timeout=timeout)
    planned_count = sum(min(len(group.bundles), args.max_summaries_per_event) for group in comment_groups)
    print(
        json.dumps(
            {
                "message": "Starting comment summarization",
                "event_count": len(comment_groups),
                "planned_summary_count": planned_count,
                "max_summaries_per_event": args.max_summaries_per_event,
                "batch_size": args.batch_size,
                "max_parallel_batches": args.max_parallel_batches,
                "batch_retries": args.batch_retries,
                "timeout_sec": timeout,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    summary_groups = summarize_event_comment_groups(
        intent,
        comment_groups,
        llm_client=client,
        max_bundles_per_event=args.max_summaries_per_event,
        batch_size=args.batch_size,
        max_parallel_batches=args.max_parallel_batches,
        batch_retries=args.batch_retries,
        progress_callback=lambda update: print(
            json.dumps(
                {
                    "progress": f'{update["completed"]}/{update["total"]}',
                    "event": update["event_name"],
                    "poi": update["poi_name"],
                },
                ensure_ascii=False,
            )
        ),
    )
    cache_path = save_cached_comment_summaries(
        summary_groups,
        cache_dir=args.cache_dir,
        intent=intent,
        comment_groups=comment_groups,
        model=model,
        base_url=base_url,
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


def load_comment_groups(path: Path) -> list[EventCommentGroup]:
    if not path.exists():
        raise SystemExit(f"Comments file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [EventCommentGroup.model_validate(item) for item in payload]


if __name__ == "__main__":
    main()
