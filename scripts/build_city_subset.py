#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from planner.config import DEFAULT_INTERIM_DIR, DEFAULT_YELP_DATASET_DIR
from planner.modules.city_subset_builder import build_city_subset
from planner.schemas import CitySubsetConfig

print('loading modules...')
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a one-city Yelp subset for planner experiments.")
    parser.add_argument("--city", required=True, help="City name, for example Philadelphia")
    parser.add_argument("--state", required=True, help="State code, for example PA")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_YELP_DATASET_DIR,
        help="Directory containing raw Yelp JSONL files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to data/interim/city_subsets/<city_state>/",
    )
    parser.add_argument(
        "--category-substring",
        default=None,
        help="Optional case-insensitive category substring, for example Restaurants.",
    )
    parser.add_argument(
        "--skip-users",
        action="store_true",
        help="Skip filtering user.json for faster subset generation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    slug = f"{args.city.strip().lower().replace(' ', '_')}_{args.state.strip().lower()}"
    output_dir = args.output_dir or (DEFAULT_INTERIM_DIR / slug)

    config = CitySubsetConfig(
        city=args.city,
        state=args.state,
        source_dir=args.source_dir,
        output_dir=output_dir,
        category_substring=args.category_substring,
        include_users=not args.skip_users,
    )
    metadata = build_city_subset(config)
    summary = {
        "city": metadata.city,
        "state": metadata.state,
        "category_substring": metadata.category_substring,
        "counts": metadata.counts.model_dump(),
        "top_categories": metadata.top_categories[:10],
        "coverage": metadata.coverage.model_dump(),
        "output_dir": str(output_dir),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
