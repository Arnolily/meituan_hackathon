from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from planner.io.yelp_reader import iter_jsonl
from planner.schemas import EventCommentGroup, EventPOIGroup, POICommentBundle, RawPOI, ReviewComment, TipComment


def load_comment_bundles(
    pois: Sequence[RawPOI],
    *,
    review_file: Path,
    tip_file: Path,
    max_reviews_per_poi: int = 20,
    max_tips_per_poi: int = 10,
) -> list[POICommentBundle]:
    business_map = {poi.business_id: poi for poi in pois}
    bundles = {
        poi.business_id: POICommentBundle(
            business_id=poi.business_id,
            name=poi.name,
            city=poi.city,
        )
        for poi in pois
    }

    for record in iter_jsonl(review_file):
        business_id = record.get("business_id")
        if business_id not in business_map:
            continue
        bundles[business_id].reviews.append(normalize_review_record(record))

    for record in iter_jsonl(tip_file):
        business_id = record.get("business_id")
        if business_id not in business_map:
            continue
        bundles[business_id].tips.append(normalize_tip_record(record))

    ordered_bundles: list[POICommentBundle] = []
    for poi in pois:
        bundle = bundles[poi.business_id]
        sorted_reviews = sorted(
            bundle.reviews,
            key=lambda review: (review.useful, review.date, review.review_id),
            reverse=True,
        )[:max_reviews_per_poi]
        sorted_tips = sorted(
            bundle.tips,
            key=lambda tip: (tip.date, tip.compliment_count, tip.user_id),
            reverse=True,
        )[:max_tips_per_poi]
        ordered_bundles.append(
            bundle.model_copy(
                update={
                    "reviews": sorted_reviews,
                    "tips": sorted_tips,
                    "review_count_loaded": len(sorted_reviews),
                    "tip_count_loaded": len(sorted_tips),
                }
            )
        )
    return ordered_bundles


def load_event_comment_groups(
    poi_groups: Sequence[EventPOIGroup],
    *,
    review_file: Path,
    tip_file: Path,
    max_reviews_per_poi: int = 20,
    max_tips_per_poi: int = 10,
) -> list[EventCommentGroup]:
    return [
        EventCommentGroup(
            event_index=group.event_index,
            event_name=group.event_name,
            event_goal=group.event_goal,
            bundles=load_comment_bundles(
                group.pois,
                review_file=review_file,
                tip_file=tip_file,
                max_reviews_per_poi=max_reviews_per_poi,
                max_tips_per_poi=max_tips_per_poi,
            ),
        )
        for group in poi_groups
    ]


def normalize_review_record(record: dict) -> ReviewComment:
    return ReviewComment(
        review_id=str(record.get("review_id") or ""),
        business_id=str(record.get("business_id") or ""),
        user_id=str(record.get("user_id") or ""),
        stars=float(record.get("stars", 0.0)),
        useful=int(record.get("useful", 0)),
        funny=int(record.get("funny", 0)),
        cool=int(record.get("cool", 0)),
        text=str(record.get("text") or ""),
        date=str(record.get("date") or ""),
    )


def normalize_tip_record(record: dict) -> TipComment:
    return TipComment(
        business_id=str(record.get("business_id") or ""),
        user_id=str(record.get("user_id") or ""),
        text=str(record.get("text") or ""),
        date=str(record.get("date") or ""),
        compliment_count=int(record.get("compliment_count", 0)),
    )


def load_pois_json(pois_payload: Iterable[dict]) -> list[RawPOI]:
    return [RawPOI.model_validate(item) for item in pois_payload]


def load_poi_groups_json(groups_payload: Iterable[dict]) -> list[EventPOIGroup]:
    items = list(groups_payload)
    if items and "business_id" in items[0]:
        return [
            EventPOIGroup(
                event_index=1,
                event_name="event_1",
                event_goal="sightseeing",
                pois=load_pois_json(items),
            )
        ]
    return [EventPOIGroup.model_validate(item) for item in items]
