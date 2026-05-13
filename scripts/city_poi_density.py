#!/usr/bin/env python3
"""Rank Yelp cities by POI density proxies.

This script reads the Yelp `business.json` dump line by line and computes:
1. POI count per city
2. Bounding-box area per city from lat/lng
3. Rough density = POI count / bounding-box area

The area proxy is intentionally simple. It is good enough for picking a city
subset for experiments, but it is not a real urban density measure.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CityStats:
    count: int = 0
    min_lat: float = math.inf
    max_lat: float = -math.inf
    min_lon: float = math.inf
    max_lon: float = -math.inf
    review_count_sum: int = 0
    stars_sum: float = 0.0

    def update(self, lat: float, lon: float, review_count: int, stars: float) -> None:
        self.count += 1
        self.min_lat = min(self.min_lat, lat)
        self.max_lat = max(self.max_lat, lat)
        self.min_lon = min(self.min_lon, lon)
        self.max_lon = max(self.max_lon, lon)
        self.review_count_sum += review_count
        self.stars_sum += stars

    @property
    def avg_stars(self) -> float:
        return self.stars_sum / self.count if self.count else 0.0

    @property
    def avg_review_count(self) -> float:
        return self.review_count_sum / self.count if self.count else 0.0


def bbox_area_km2(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> float:
    """Approximate rectangular area in km^2 around the city's center latitude."""
    if not all(math.isfinite(v) for v in (min_lat, max_lat, min_lon, max_lon)):
        return 0.0

    lat_km = 111.32 * max(0.0, max_lat - min_lat)
    center_lat_rad = math.radians((min_lat + max_lat) / 2.0)
    lon_km = 111.32 * math.cos(center_lat_rad) * max(0.0, max_lon - min_lon)
    return max(lat_km * lon_km, 0.0)


def normalize_city(city: str, state: str) -> str:
    city = (city or "").strip()
    state = (state or "").strip()
    if state:
        return f"{city}, {state}"
    return city


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
        default=20,
        help="Number of rows to print for each ranking.",
    )
    parser.add_argument(
        "--min-pois",
        type=int,
        default=200,
        help="Minimum POI count for the density ranking.",
    )
    parser.add_argument(
        "--state",
        type=str,
        default="",
        help="Optional state filter, for example `PA`.",
    )
    parser.add_argument(
        "--category-substring",
        type=str,
        default="",
        help="Optional case-insensitive category filter, for example `Restaurants`.",
    )
    return parser.parse_args()


def load_city_stats(
    business_file: Path,
    state_filter: str = "",
    category_substring: str = "",
) -> dict[str, CityStats]:
    stats: dict[str, CityStats] = defaultdict(CityStats)
    category_substring = category_substring.lower().strip()
    state_filter = state_filter.strip().upper()

    with business_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            city = normalize_city(record.get("city", ""), record.get("state", ""))
            if not city:
                continue

            state = (record.get("state") or "").strip().upper()
            if state_filter and state != state_filter:
                continue

            categories = record.get("categories") or ""
            if category_substring and category_substring not in categories.lower():
                continue

            lat = record.get("latitude")
            lon = record.get("longitude")
            if lat is None or lon is None:
                continue

            stats[city].update(
                lat=float(lat),
                lon=float(lon),
                review_count=int(record.get("review_count", 0)),
                stars=float(record.get("stars", 0.0)),
            )

    return stats


def format_rows(rows: list[tuple[str, CityStats, float]]) -> str:
    header = (
        f"{'city':30} {'pois':>8} {'bbox_km2':>12} "
        f"{'pois/km2':>10} {'avg_reviews':>12} {'avg_stars':>10}"
    )
    parts = [header, "-" * len(header)]
    for city, stat, area in rows:
        density = stat.count / area if area > 0 else 0.0
        parts.append(
            f"{city[:30]:30} {stat.count:8d} {area:12.2f} "
            f"{density:10.3f} {stat.avg_review_count:12.2f} {stat.avg_stars:10.2f}"
        )
    return "\n".join(parts)


def main() -> None:
    args = parse_args()
    stats = load_city_stats(
        business_file=args.business_file,
        state_filter=args.state,
        category_substring=args.category_substring,
    )

    if not stats:
        raise SystemExit("No matching businesses found for the given filters.")

    by_count = sorted(stats.items(), key=lambda item: item[1].count, reverse=True)

    density_candidates: list[tuple[str, CityStats, float]] = []
    for city, stat in stats.items():
        if stat.count < args.min_pois:
            continue
        area = bbox_area_km2(stat.min_lat, stat.max_lat, stat.min_lon, stat.max_lon)
        if area <= 0:
            continue
        density_candidates.append((city, stat, area))

    by_density = sorted(
        density_candidates,
        key=lambda item: item[1].count / item[2],
        reverse=True,
    )

    top_count_rows = [
        (city, stat, bbox_area_km2(stat.min_lat, stat.max_lat, stat.min_lon, stat.max_lon))
        for city, stat in by_count[: args.top]
    ]

    print("Top cities by POI count")
    print(format_rows(top_count_rows))
    print()
    print(f"Top cities by POI density proxy (min_pois={args.min_pois})")
    print(format_rows(by_density[: args.top]))
    print()
    print("Notes:")
    print("- `bbox_km2` is the city's business bounding-box area, not the true city area.")
    print("- `pois/km2` is a ranking proxy for dataset compactness, not a map-grade metric.")
    print("- Use this ranking to choose a dense city subset for v1 experiments.")


if __name__ == "__main__":
    main()
