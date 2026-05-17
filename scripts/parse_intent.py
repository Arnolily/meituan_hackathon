#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from planner.config import DEFAULT_CACHE_DIR, load_env_file
from planner.io.intent_cache import load_cached_intent, save_cached_intent
from planner.llm.client import OpenAICompatibleClient
from planner.modules.intent_parser import parse_intent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse a route-planning query into structured intent.")
    parser.add_argument("query", help="User route-planning query.")
    parser.add_argument("--default-city", default=None, help="Fallback city when the query does not specify one.")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Cache directory for parsed intent JSON artifacts.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore any saved cached intent and call the API again.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env_settings = load_env_file()
    api_key = env_settings.get("OPENAI_API_KEY")
    base_url = env_settings.get("OPENAI_BASE_URL")
    model = env_settings.get("OPENAI_MODEL")

    if not model:
        raise SystemExit("Missing model. Set PLANNER_LLM_MODEL or OPENAI_MODEL in .env.local.")
    if not args.refresh_cache:
        cached = load_cached_intent(
            cache_dir=args.cache_dir,
            query=args.query,
            default_city=args.default_city,
            model=model,
            base_url=base_url,
        )
        if cached is not None:
            print(json.dumps(cached.model_dump(), ensure_ascii=False, indent=2))
            return
    if not api_key:
        raise SystemExit("Missing API key. Set PLANNER_LLM_API_KEY or OPENAI_API_KEY in .env.local.")

    llm_client = OpenAICompatibleClient(api_key=api_key, base_url=base_url, model=model)

    intent = parse_intent(args.query, default_city=args.default_city, llm_client=llm_client)
    save_cached_intent(
        intent,
        cache_dir=args.cache_dir,
        query=args.query,
        default_city=args.default_city,
        model=model,
        base_url=base_url,
    )
    print(json.dumps(intent.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
