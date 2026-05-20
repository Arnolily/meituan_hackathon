import hashlib
import json
from pathlib import Path
from typing import Sequence

from planner.schemas import EventPOIGroup, Intent, RawPOI


def build_poi_cache_key(*, intent: Intent, business_file: Path, max_pois: int) -> str:
    payload = {
        "raw_query": intent.raw_query,
        "city": intent.city,
        "events": [event.model_dump() for event in intent.events],
        "business_file": str(business_file.resolve()),
        "max_pois": max_pois,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def get_poi_cache_path(*, cache_dir: Path, intent: Intent, business_file: Path, max_pois: int) -> Path:
    cache_key = build_poi_cache_key(intent=intent, business_file=business_file, max_pois=max_pois)
    return cache_dir / "pois" / f"{cache_key}.json"


def save_cached_pois(
    poi_groups: Sequence[EventPOIGroup],
    *,
    cache_dir: Path,
    intent: Intent,
    business_file: Path,
    max_pois: int,
) -> Path:
    cache_path = get_poi_cache_path(
        cache_dir=cache_dir,
        intent=intent,
        business_file=business_file,
        max_pois=max_pois,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [group.model_dump() for group in poi_groups]
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_path = cache_dir / "pois" / "latest_pois.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache_path
