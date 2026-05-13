import json
from pathlib import Path

from planner.modules.city_subset_builder import build_city_subset
from planner.schemas import CitySubsetConfig


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")


def test_build_city_subset_filters_and_writes_linked_records(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    source_dir.mkdir()

    _write_jsonl(
        source_dir / "yelp_academic_dataset_business.json",
        [
            {
                "business_id": "b1",
                "name": "Cafe One",
                "city": "Philadelphia",
                "state": "PA",
                "categories": "Restaurants, Coffee & Tea",
                "hours": {"Monday": "8:0-17:0"},
                "attributes": {"OutdoorSeating": "True"},
            },
            {
                "business_id": "b2",
                "name": "Shop Two",
                "city": "Philadelphia",
                "state": "PA",
                "categories": "Shopping",
                "hours": None,
                "attributes": None,
            },
            {
                "business_id": "b3",
                "name": "Other City",
                "city": "Tampa",
                "state": "FL",
                "categories": "Restaurants",
                "hours": None,
                "attributes": None,
            },
        ],
    )
    _write_jsonl(
        source_dir / "yelp_academic_dataset_review.json",
        [
            {"review_id": "r1", "business_id": "b1", "user_id": "u1", "text": "Great"},
            {"review_id": "r2", "business_id": "b3", "user_id": "u2", "text": "Nope"},
        ],
    )
    _write_jsonl(
        source_dir / "yelp_academic_dataset_tip.json",
        [
            {"business_id": "b1", "user_id": "u3", "text": "Try brunch"},
            {"business_id": "b2", "user_id": "u4", "text": "Nice store"},
        ],
    )
    _write_jsonl(
        source_dir / "yelp_academic_dataset_checkin.json",
        [
            {"business_id": "b1", "date": "2020-01-01 09:00:00"},
            {"business_id": "b3", "date": "2020-01-01 10:00:00"},
        ],
    )
    _write_jsonl(
        source_dir / "yelp_academic_dataset_user.json",
        [
            {"user_id": "u1", "name": "Alice"},
            {"user_id": "u3", "name": "Bob"},
            {"user_id": "u9", "name": "Unused"},
        ],
    )

    metadata = build_city_subset(
        CitySubsetConfig(
            city="Philadelphia",
            state="PA",
            source_dir=source_dir,
            output_dir=output_dir,
            category_substring="Restaurants",
        )
    )

    assert metadata.counts.businesses == 1
    assert metadata.counts.reviews == 1
    assert metadata.counts.tips == 1
    assert metadata.counts.checkins == 1
    assert metadata.counts.users == 2
    assert metadata.business_ids == ["b1"]
    assert metadata.user_ids == ["u1", "u3"]
    assert metadata.coverage.missing_hours_ratio == 0.0
    assert metadata.coverage.missing_attributes_ratio == 0.0

    business_lines = (output_dir / "yelp_academic_dataset_business.json").read_text(encoding="utf-8").strip().splitlines()
    review_lines = (output_dir / "yelp_academic_dataset_review.json").read_text(encoding="utf-8").strip().splitlines()
    user_lines = (output_dir / "yelp_academic_dataset_user.json").read_text(encoding="utf-8").strip().splitlines()
    metadata_json = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))

    assert len(business_lines) == 1
    assert len(review_lines) == 1
    assert len(user_lines) == 2
    assert metadata_json["counts"]["businesses"] == 1


def test_build_city_subset_handles_empty_match(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    source_dir.mkdir()

    for file_name in [
        "yelp_academic_dataset_business.json",
        "yelp_academic_dataset_review.json",
        "yelp_academic_dataset_tip.json",
        "yelp_academic_dataset_checkin.json",
        "yelp_academic_dataset_user.json",
    ]:
        (source_dir / file_name).write_text("", encoding="utf-8")

    metadata = build_city_subset(
        CitySubsetConfig(
            city="Philadelphia",
            state="PA",
            source_dir=source_dir,
            output_dir=output_dir,
        )
    )

    assert metadata.counts.businesses == 0
    assert json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))["counts"]["businesses"] == 0
