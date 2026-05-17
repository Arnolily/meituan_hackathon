#!/usr/bin/env python3
"""Count Yelp business categories with overlap preserved.

Each business can contribute to multiple categories because Yelp stores
comma-separated category labels on the business record.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--business-file",
        type=Path,
        default=Path("yelp_dataset/yelp_academic_dataset_business.json"),
        help="Path to Yelp business JSON lines file.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=100,
        help="Number of categories to print.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Minimum business count required for a category to be shown.",
    )
    parser.add_argument(
        "--city",
        type=str,
        default="",
        help="Optional city filter, for example `Philadelphia`.",
    )
    parser.add_argument(
        "--state",
        type=str,
        default="",
        help="Optional state filter, for example `PA`.",
    )
    parser.add_argument(
        "--contains",
        type=str,
        default="",
        help="Optional case-insensitive substring filter over category labels.",
    )
    return parser.parse_args()


def normalize(value: str) -> str:
    return (value or "").strip().lower()


def load_category_counts(
    business_file: Path,
    *,
    city_filter: str = "",
    state_filter: str = "",
    contains_filter: str = "",
) -> tuple[Counter[str], int]:
    counter: Counter[str] = Counter()
    matched_businesses = 0

    city_filter = normalize(city_filter)
    state_filter = normalize(state_filter)
    contains_filter = normalize(contains_filter)

    with business_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)

            city = normalize(record.get("city", ""))
            state = normalize(record.get("state", ""))
            if city_filter and city != city_filter:
                continue
            if state_filter and state != state_filter:
                continue

            categories_text = record.get("categories") or ""
            if not categories_text.strip():
                continue

            raw_categories = [category.strip() for category in categories_text.split(",")]
            categories = [category for category in raw_categories if category]
            if not categories:
                continue

            if contains_filter:
                categories = [category for category in categories if contains_filter in category.lower()]
                if not categories:
                    continue

            matched_businesses += 1
            counter.update(categories)

    return counter, matched_businesses


def main() -> None:
    args = parse_args()
    counter, matched_businesses = load_category_counts(
        args.business_file,
        city_filter=args.city,
        state_filter=args.state,
        contains_filter=args.contains,
    )

    rows = [(category, count) for category, count in counter.most_common() if count >= args.min_count]
    rows = rows[: args.top]

    print(f"Matched businesses: {matched_businesses}")
    print(f"Distinct categories: {len(counter)}")
    print()
    print(f"{'category':40} {'business_count':>14}")
    print("-" * 56)
    for category, count in rows:
        print(f"{category[:40]:40} {count:14d}")

    print()
    print("Notes:")
    print("- Counts are overlapping by design: one business can increment multiple categories.")
    print("- Categories come from Yelp's comma-separated `categories` field on each business record.")


if __name__ == "__main__":
    main()
