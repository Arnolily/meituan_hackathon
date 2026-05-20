import hashlib
import json
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from planner.schemas import Intent
from planner.vocab import ALLOWED_GOALS


LEGACY_GOAL_ALIASES = {
    "budget_meal": "dinner",
    "fine dining": "dinner",
    "brunch": "breakfast",
    "coffee_shop": "coffee",
    "coffee shop": "coffee",
    "bar": "nightlife",
    "bars": "nightlife",
}


def build_intent_cache_key(
    *,
    query: str,
    default_city: Optional[str],
    model: str,
    base_url: Optional[str],
) -> str:
    payload = {
        "query": query,
        "default_city": default_city,
        "model": model,
        "base_url": base_url or "",
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def get_intent_cache_path(
    *,
    cache_dir: Path,
    query: str,
    default_city: Optional[str],
    model: str,
    base_url: Optional[str],
) -> Path:
    cache_key = build_intent_cache_key(
        query=query,
        default_city=default_city,
        model=model,
        base_url=base_url,
    )
    return cache_dir / "intents" / f"{cache_key}.json"


def load_cached_intent(
    *,
    cache_dir: Path,
    query: str,
    default_city: Optional[str],
    model: str,
    base_url: Optional[str],
) -> Optional[Intent]:
    cache_path = get_intent_cache_path(
        cache_dir=cache_dir,
        query=query,
        default_city=default_city,
        model=model,
        base_url=base_url,
    )
    if not cache_path.exists():
        return None
    return load_intent_json(cache_path.read_text(encoding="utf-8"))


def load_intent_json(raw_json: str) -> Intent:
    try:
        return Intent.model_validate_json(raw_json)
    except ValidationError as exc:
        payload = json.loads(raw_json)
        sanitized_payload = sanitize_legacy_intent_payload(payload)
        if sanitized_payload == payload:
            raise exc
        return Intent.model_validate(sanitized_payload)


def sanitize_legacy_intent_payload(payload: dict) -> dict:
    sanitized = dict(payload)
    raw_goals = sanitized.get("goals")
    if isinstance(raw_goals, list):
        normalized_goals: list[str] = []
        for goal in raw_goals:
            if not isinstance(goal, str):
                continue
            mapped_goal = LEGACY_GOAL_ALIASES.get(goal, goal)
            if mapped_goal in ALLOWED_GOALS and mapped_goal not in normalized_goals:
                normalized_goals.append(mapped_goal)
        sanitized["goals"] = normalized_goals

    raw_events = sanitized.get("events")
    if isinstance(raw_events, list):
        normalized_events: list[dict] = []
        for index, event in enumerate(raw_events):
            if not isinstance(event, dict):
                continue
            normalized_event = dict(event)
            raw_goal = normalized_event.get("goal")
            if isinstance(raw_goal, str):
                normalized_goal = LEGACY_GOAL_ALIASES.get(raw_goal, raw_goal)
                if normalized_goal in ALLOWED_GOALS:
                    normalized_event["goal"] = normalized_goal
                else:
                    continue
            else:
                continue
            normalized_event.setdefault("name", f"event_{index + 1}")
            normalized_event.setdefault("categories", [])
            normalized_event.setdefault("poi_types", [])
            normalized_event.setdefault("budget_level", "unknown")
            normalized_event.setdefault("hard_constraints", [])
            normalized_event.setdefault("soft_preferences", [])
            normalized_events.append(normalized_event)
        sanitized["events"] = normalized_events

    if not sanitized.get("overall_goal"):
        sanitized["overall_goal"] = sanitized.get("raw_query") or "route planning"
    return sanitized


def save_cached_intent(
    intent: Intent,
    *,
    cache_dir: Path,
    query: str,
    default_city: Optional[str],
    model: str,
    base_url: Optional[str],
) -> Path:
    cache_path = get_intent_cache_path(
        cache_dir=cache_dir,
        query=query,
        default_city=default_city,
        model=model,
        base_url=base_url,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(intent.model_dump_json(indent=2), encoding="utf-8")

    latest_path = cache_dir / "intents" / "latest_intent.json"
    latest_path.write_text(intent.model_dump_json(indent=2), encoding="utf-8")
    return cache_path
