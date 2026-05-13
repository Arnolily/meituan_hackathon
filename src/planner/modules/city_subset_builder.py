import json
from pathlib import Path
from typing import Iterable, Optional

from planner.schemas import CitySubsetAccumulator, CitySubsetConfig, CitySubsetMetadata


BUSINESS_FILE = "yelp_academic_dataset_business.json"
REVIEW_FILE = "yelp_academic_dataset_review.json"
TIP_FILE = "yelp_academic_dataset_tip.json"
CHECKIN_FILE = "yelp_academic_dataset_checkin.json"
USER_FILE = "yelp_academic_dataset_user.json"


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _record_matches_city(record: dict, *, city: str, state: str) -> bool:
    return (
        _normalize_text(record.get("city")) == _normalize_text(city)
        and _normalize_text(record.get("state")) == _normalize_text(state)
    )


def _record_matches_category(record: dict, category_substring: Optional[str]) -> bool:
    if not category_substring:
        return True
    categories = _normalize_text(record.get("categories"))
    return _normalize_text(category_substring) in categories


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_matching_records(
    source_path: Path,
    output_path: Path,
    *,
    key: str,
    allowed_values: set[str],
    accumulator_field: str,
    user_ids: Optional[set[str]] = None,
) -> int:
    count = 0
    with source_path.open("r", encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as target:
        for line in source:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get(key) not in allowed_values:
                continue
            target.write(json.dumps(record, ensure_ascii=True))
            target.write("\n")
            count += 1
            if user_ids is not None and "user_id" in record:
                user_ids.add(record["user_id"])
    return count


def build_city_subset(config: CitySubsetConfig) -> CitySubsetMetadata:
    source_dir = config.source_dir
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name in [BUSINESS_FILE, REVIEW_FILE, TIP_FILE, CHECKIN_FILE, USER_FILE]:
        (output_dir / file_name).touch()

    accumulator = CitySubsetAccumulator()

    business_output = output_dir / BUSINESS_FILE
    with (source_dir / BUSINESS_FILE).open("r", encoding="utf-8") as source, business_output.open(
        "w", encoding="utf-8"
    ) as target:
        for line in source:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not _record_matches_city(record, city=config.city, state=config.state):
                continue
            if not _record_matches_category(record, config.category_substring):
                continue

            target.write(json.dumps(record, ensure_ascii=True))
            target.write("\n")

            accumulator.business_count += 1
            business_id = record["business_id"]
            accumulator.business_ids.add(business_id)

            categories = record.get("categories") or ""
            for category in categories.split(","):
                category = category.strip()
                if category:
                    accumulator.category_counter[category] += 1

            if not record.get("hours"):
                accumulator.missing_hours += 1
            if not record.get("attributes"):
                accumulator.missing_attributes += 1

    allowed_business_ids = accumulator.business_ids
    if not allowed_business_ids:
        metadata = accumulator.to_metadata(
            city=config.city,
            state=config.state,
            category_substring=config.category_substring,
        )
        _write_metadata(output_dir, metadata)
        return metadata

    user_ids: set[str] = set()
    accumulator.review_count = _write_matching_records(
        source_dir / REVIEW_FILE,
        output_dir / REVIEW_FILE,
        key="business_id",
        allowed_values=allowed_business_ids,
        accumulator_field="review_count",
        user_ids=user_ids,
    )
    accumulator.tip_count = _write_matching_records(
        source_dir / TIP_FILE,
        output_dir / TIP_FILE,
        key="business_id",
        allowed_values=allowed_business_ids,
        accumulator_field="tip_count",
        user_ids=user_ids,
    )
    accumulator.checkin_count = _write_matching_records(
        source_dir / CHECKIN_FILE,
        output_dir / CHECKIN_FILE,
        key="business_id",
        allowed_values=allowed_business_ids,
        accumulator_field="checkin_count",
    )

    if config.include_users and user_ids:
        accumulator.user_ids = user_ids
        accumulator.user_count = _write_matching_records(
            source_dir / USER_FILE,
            output_dir / USER_FILE,
            key="user_id",
            allowed_values=user_ids,
            accumulator_field="user_count",
        )
    elif config.include_users:
        (output_dir / USER_FILE).write_text("", encoding="utf-8")

    metadata = accumulator.to_metadata(
        city=config.city,
        state=config.state,
        category_substring=config.category_substring,
    )
    _write_metadata(output_dir, metadata)
    return metadata


def _write_metadata(output_dir: Path, metadata: CitySubsetMetadata) -> None:
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
