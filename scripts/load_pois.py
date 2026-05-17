#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Optional

from planner.config import DEFAULT_CACHE_DIR, DEFAULT_INTERIM_DIR
from planner.io.intent_cache import load_intent_json
from planner.io.poi_cache import save_cached_pois
from planner.modules.poi_loader import load_candidate_pois
from planner.schemas import AnchorPoint, Intent, SpatialConstraint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load normalized POI candidates from a city subset.")
    parser.add_argument("--intent-json", help="Intent JSON string.")
    parser.add_argument(
        "--intent-file",
        type=Path,
        default=DEFAULT_CACHE_DIR / "intents" / "latest_intent.json",
        help="Path to an intent JSON file. Defaults to the latest cached intent.",
    )
    parser.add_argument("--business-file", type=Path, help="Path to subset business JSONL file.")
    parser.add_argument("--max-pois", type=int, default=10, help="Maximum number of POIs to print.")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Cache directory for POI JSON artifacts.",
    )
    parser.add_argument("--anchor-lat", type=float, help="Anchor latitude for spatial filtering.")
    parser.add_argument("--anchor-lng", type=float, help="Anchor longitude for spatial filtering.")
    parser.add_argument("--anchor-name", default="anchor", help="Optional anchor name.")
    parser.add_argument("--max-radius-km", type=float, help="Optional max straight-line radius in kilometers.")
    parser.add_argument("--max-travel-min", type=float, help="Optional max estimated travel time in minutes.")
    parser.add_argument(
        "--mode",
        choices=["walking", "driving", "transit"],
        default="walking",
        help="Travel mode for straight-line time estimation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    intent = load_intent(args.intent_json, args.intent_file)
    business_file = args.business_file or resolve_business_file(intent)
    spatial_constraint = build_spatial_constraint(args)
    pois = load_candidate_pois(
        intent,
        business_file=business_file,
        max_pois=args.max_pois,
        spatial_constraint=spatial_constraint,
    )
    cache_path = save_cached_pois(
        pois,
        cache_dir=args.cache_dir,
        intent=intent,
        business_file=business_file,
        max_pois=args.max_pois,
    )
    print(
        json.dumps(
            {
                "count": len(pois),
                "business_file": str(business_file),
                "spatial_filter": spatial_constraint.model_dump() if spatial_constraint is not None else None,
                "cache_path": str(cache_path),
                "latest_path": str(args.cache_dir / "pois" / "latest_pois.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def load_intent(intent_json: Optional[str], intent_file: Path) -> Intent:
    if intent_json:
        return load_intent_json(intent_json)
    if intent_file.exists():
        return load_intent_json(intent_file.read_text(encoding="utf-8"))
    raise SystemExit(f"Intent not provided and default intent file not found: {intent_file}")


def resolve_business_file(intent: Intent) -> Path:
    if not intent.city:
        raise SystemExit("Business file not provided and intent.city is empty, so no subset can be resolved automatically.")

    metadata_files = sorted(DEFAULT_INTERIM_DIR.glob("*/metadata.json"))
    matches: list[Path] = []
    for metadata_file in metadata_files:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        if (metadata.get("city") or "").lower() == intent.city.lower():
            matches.append(metadata_file.parent / "yelp_academic_dataset_business.json")

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SystemExit(
            f"No subset business file found for city '{intent.city}'. Pass --business-file explicitly or build that city subset first."
        )
    raise SystemExit(
        f"Multiple subset business files found for city '{intent.city}'. Pass --business-file explicitly."
    )


def build_spatial_constraint(args: argparse.Namespace) -> Optional[SpatialConstraint]:
    if args.anchor_lat is None and args.anchor_lng is None:
        return None
    if args.anchor_lat is None or args.anchor_lng is None:
        raise SystemExit("Both --anchor-lat and --anchor-lng are required for spatial filtering.")
    return SpatialConstraint(
        anchor=AnchorPoint(name=args.anchor_name, latitude=args.anchor_lat, longitude=args.anchor_lng),
        max_radius_km=args.max_radius_km,
        max_travel_min=args.max_travel_min,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()
