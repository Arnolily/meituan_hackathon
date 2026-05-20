#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Optional

from planner.config import DEFAULT_CACHE_DIR, DEFAULT_INTERIM_DIR
from planner.io.comment_cache import save_cached_comments
from planner.modules.comment_loader import load_event_comment_groups, load_poi_groups_json
from planner.schemas import EventPOIGroup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load raw reviews and tips for cached POI candidates.")
    parser.add_argument("--pois-json", help="POIs JSON string.")
    parser.add_argument(
        "--pois-file",
        type=Path,
        default=DEFAULT_CACHE_DIR / "pois" / "latest_pois.json",
        help="Path to a POIs JSON file. Defaults to the latest cached POIs.",
    )
    parser.add_argument("--review-file", type=Path, help="Path to subset review JSONL file.")
    parser.add_argument("--tip-file", type=Path, help="Path to subset tip JSONL file.")
    parser.add_argument("--max-reviews-per-poi", type=int, default=20, help="Maximum reviews to keep per POI.")
    parser.add_argument("--max-tips-per-poi", type=int, default=10, help="Maximum tips to keep per POI.")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Cache directory for comment JSON artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    poi_groups = load_pois(args.pois_json, args.pois_file)
    review_file, tip_file = resolve_comment_files(poi_groups, args.review_file, args.tip_file)
    comment_groups = load_event_comment_groups(
        poi_groups,
        review_file=review_file,
        tip_file=tip_file,
        max_reviews_per_poi=args.max_reviews_per_poi,
        max_tips_per_poi=args.max_tips_per_poi,
    )
    cache_path = save_cached_comments(
        comment_groups,
        cache_dir=args.cache_dir,
        poi_groups=poi_groups,
        review_file=review_file,
        tip_file=tip_file,
        max_reviews_per_poi=args.max_reviews_per_poi,
        max_tips_per_poi=args.max_tips_per_poi,
    )
    print(
        json.dumps(
            {
                "event_count": len(comment_groups),
                "total_bundle_count": sum(len(group.bundles) for group in comment_groups),
                "review_file": str(review_file),
                "tip_file": str(tip_file),
                "cache_path": str(cache_path),
                "latest_path": str(args.cache_dir / "comments" / "latest_comments.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def load_pois(pois_json: Optional[str], pois_file: Path) -> list[EventPOIGroup]:
    if pois_json:
        return load_poi_groups_json(json.loads(pois_json))
    if pois_file.exists():
        return load_poi_groups_json(json.loads(pois_file.read_text(encoding="utf-8")))
    raise SystemExit(f"POIs not provided and default POIs file not found: {pois_file}")


def resolve_comment_files(
    poi_groups: list[EventPOIGroup],
    review_file: Optional[Path],
    tip_file: Optional[Path],
) -> tuple[Path, Path]:
    if review_file is not None and tip_file is not None:
        return review_file, tip_file
    all_pois = [poi for group in poi_groups for poi in group.pois]
    if not all_pois:
        raise SystemExit("No POIs provided, so review/tip files cannot be resolved automatically.")

    city = all_pois[0].city
    metadata_files = sorted(DEFAULT_INTERIM_DIR.glob("*/metadata.json"))
    matches: list[Path] = []
    for metadata_file in metadata_files:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        if (metadata.get("city") or "").lower() == city.lower():
            matches.append(metadata_file.parent)

    if len(matches) != 1:
        if not matches:
            raise SystemExit(
                f"No subset files found for city '{city}'. Pass --review-file and --tip-file explicitly or build that city subset first."
            )
        raise SystemExit(f"Multiple subset directories found for city '{city}'. Pass --review-file and --tip-file explicitly.")

    subset_dir = matches[0]
    return (
        review_file or subset_dir / "yelp_academic_dataset_review.json",
        tip_file or subset_dir / "yelp_academic_dataset_tip.json",
    )


if __name__ == "__main__":
    main()
