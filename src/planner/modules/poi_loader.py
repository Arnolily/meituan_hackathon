import ast
import json
from pathlib import Path
from typing import Any, Optional

from planner.schemas import GeoPoint, Intent, RawPOI, SpatialConstraint
from planner.utils.geo import anchor_to_point, estimate_travel_minutes, haversine_distance_km
from planner.vocab import GOAL_CATEGORY_HINTS, POI_TYPE_CATEGORY_HINTS


def load_candidate_pois(
    intent: Intent,
    *,
    business_file: Path,
    max_pois: Optional[int] = None,
    spatial_constraint: Optional[SpatialConstraint] = None,
) -> list[RawPOI]:
    candidates: list[RawPOI] = []
    with business_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            poi = normalize_business_record(record)
            scored_poi = _score_against_intent(poi, intent)
            if scored_poi.retrieval_score <= 0:
                continue
            if spatial_constraint is not None:
                scored_poi = _annotate_spatial_fields(scored_poi, spatial_constraint)
                if not _matches_spatial_constraint(scored_poi, spatial_constraint):
                    continue
            candidates.append(scored_poi)

    candidates.sort(
        key=lambda poi: (
            -poi.retrieval_score,
            poi.distance_to_anchor_km is None,
            poi.distance_to_anchor_km if poi.distance_to_anchor_km is not None else float("inf"),
            -poi.review_count,
            -poi.stars,
            poi.name,
        )
    )
    if max_pois is not None:
        return candidates[:max_pois]
    return candidates


def normalize_business_record(record: dict[str, Any]) -> RawPOI:
    categories = _parse_categories(record.get("categories"))
    attributes = _parse_attributes(record.get("attributes"))
    hours = _parse_hours(record.get("hours"))
    price_tier = _extract_price_tier(attributes)

    return RawPOI(
        business_id=record["business_id"],
        name=record.get("name") or "",
        address=record.get("address") or "",
        city=record.get("city") or "",
        state=record.get("state") or "",
        postal_code=record.get("postal_code") or "",
        latitude=float(record["latitude"]),
        longitude=float(record["longitude"]),
        stars=float(record.get("stars", 0.0)),
        review_count=int(record.get("review_count", 0)),
        is_open=bool(record.get("is_open", 0)),
        categories=categories,
        attributes=attributes,
        hours=hours,
        price_tier=price_tier,
        price_level=_price_level_from_tier(price_tier),
    )


def _score_against_intent(poi: RawPOI, intent: Intent) -> RawPOI:
    score = 0.0
    reasons: list[str] = []

    if intent.city and poi.city.lower() != intent.city.lower():
        return poi.model_copy(update={"retrieval_score": 0.0, "retrieval_reasons": ["city_mismatch"]})

    poi_categories = {category.lower() for category in poi.categories}
    if intent.categories:
        category_hits = 0
        for wanted in intent.categories:
            wanted_lower = wanted.lower()
            if wanted_lower in poi_categories:
                category_hits += 1
                reasons.append(f"category={wanted}")
            elif any(wanted_lower in category for category in poi_categories):
                category_hits += 1
                reasons.append(f"category_partial={wanted}")
        if category_hits == 0:
            return poi.model_copy(update={"retrieval_score": 0.0, "retrieval_reasons": ["no_category_match"]})
        score += 10.0 + (2.0 * category_hits)

    if intent.poi_types:
        poi_type_hits = 0
        for poi_type in intent.poi_types:
            hints = POI_TYPE_CATEGORY_HINTS.get(poi_type, set())
            if hints and poi_categories.intersection(hints):
                poi_type_hits += 1
                reasons.append(f"poi_type={poi_type}")
        score += 2.0 * poi_type_hits

    if intent.goals:
        goal_hits = 0
        for goal in intent.goals:
            hints = GOAL_CATEGORY_HINTS.get(goal.lower(), set())
            if hints and poi_categories.intersection(hints):
                goal_hits += 1
                reasons.append(f"goal={goal}")
        score += 1.5 * goal_hits

    if intent.target_area:
        area_text = f"{poi.name} {poi.address}".lower()
        if intent.target_area.lower() in area_text:
            score += 3.0
            reasons.append("target_area_match")

    score += _budget_score(intent, poi, reasons)
    score += _soft_preference_score(intent, poi, poi_categories, reasons)
    score += _hard_constraint_score(intent, poi, poi_categories, reasons)

    quality_score = min(poi.stars, 5.0) * 0.4 + min(poi.review_count, 1000) / 1000.0
    score += quality_score
    if poi.price_level is None:
        score -= 0.25
        reasons.append("price_unknown")

    return poi.model_copy(update={"retrieval_score": round(score, 3), "retrieval_reasons": reasons})


def _budget_score(intent: Intent, poi: RawPOI, reasons: list[str]) -> float:
    if intent.budget_level == "unknown" or poi.price_tier is None:
        return 0.0
    if intent.budget_level == "low":
        if poi.price_tier == 1:
            reasons.append("budget_match_low")
            return 3.0
        if poi.price_tier == 2:
            reasons.append("budget_near_low")
            return 1.0
        reasons.append("budget_penalty_high_cost")
        return -3.0
    if intent.budget_level == "medium":
        if poi.price_tier == 2:
            reasons.append("budget_match_medium")
            return 3.0
        if poi.price_tier in {1, 3}:
            reasons.append("budget_near_medium")
            return 1.0
        return -1.5
    if intent.budget_level == "high":
        if poi.price_tier >= 3:
            reasons.append("budget_match_high")
            return 4.0
        if poi.price_tier == 2:
            reasons.append("budget_penalty_not_premium")
            return -1.5
        reasons.append("budget_penalty_low_cost")
        return -3.0
    return 0.0


def _soft_preference_score(intent: Intent, poi: RawPOI, poi_categories: set[str], reasons: list[str]) -> float:
    score = 0.0
    attributes = poi.attributes
    soft_prefs = {pref.lower() for pref in intent.soft_preferences}

    if "premium_experience" in soft_prefs:
        if poi.price_tier and poi.price_tier >= 3:
            score += 3.0
            reasons.append("pref_premium_price")
        ambience = attributes.get("Ambience")
        if isinstance(ambience, dict) and any(ambience.get(flag) for flag in ["classy", "upscale", "intimate", "trendy"]):
            score += 1.5
            reasons.append("pref_premium_ambience")
        if attributes.get("RestaurantsReservations") is True:
            score += 0.75
            reasons.append("pref_reservations")

    if "high_quality_food" in soft_prefs:
        if "restaurants" in poi_categories:
            score += 1.0
            reasons.append("pref_food_category")
        if poi.stars >= 4.3:
            score += 1.5
            reasons.append("pref_high_rating")

    if "high_end_atmosphere" in soft_prefs:
        ambience = attributes.get("Ambience")
        if isinstance(ambience, dict) and any(ambience.get(flag) for flag in ["classy", "upscale", "romantic", "trendy"]):
            score += 1.5
            reasons.append("pref_atmosphere")
        if "bars" in poi_categories or "cocktail bars" in poi_categories:
            score += 0.75
            reasons.append("pref_bar_atmosphere")

    if "budget_sensitive" in soft_prefs and poi.price_tier is not None:
        if poi.price_tier == 1:
            score += 2.0
            reasons.append("pref_budget_value")
        elif poi.price_tier >= 3:
            score -= 2.0
            reasons.append("pref_budget_penalty")

    if "good_view" in soft_prefs and attributes.get("OutdoorSeating") is True:
        score += 0.5
        reasons.append("pref_outdoor")

    return score


def _hard_constraint_score(intent: Intent, poi: RawPOI, poi_categories: set[str], reasons: list[str]) -> float:
    score = 0.0
    hard_constraints = " ".join(intent.hard_constraints).lower()

    if "must_include_dinner" in hard_constraints and "restaurants" in poi_categories:
        score += 2.0
        reasons.append("constraint_dinner")

    if "minor present" in hard_constraints or "non-alcoholic" in hard_constraints:
        if poi.attributes.get("GoodForKids") is True:
            score += 1.0
            reasons.append("constraint_minor_friendly")
        if "coffee & tea" in poi_categories or "cafes" in poi_categories:
            score += 1.0
            reasons.append("constraint_non_alcoholic_option")

    return score


def _annotate_spatial_fields(poi: RawPOI, spatial_constraint: SpatialConstraint) -> RawPOI:
    poi_point = GeoPoint(latitude=poi.latitude, longitude=poi.longitude)
    anchor_point = anchor_to_point(spatial_constraint.anchor)
    distance_km = haversine_distance_km(anchor_point, poi_point)
    travel_minutes = estimate_travel_minutes(distance_km, spatial_constraint.mode)
    return poi.model_copy(
        update={
            "distance_to_anchor_km": round(distance_km, 3),
            "estimated_travel_minutes": round(travel_minutes, 2),
        }
    )


def _matches_spatial_constraint(poi: RawPOI, spatial_constraint: SpatialConstraint) -> bool:
    if (
        spatial_constraint.max_radius_km is not None
        and poi.distance_to_anchor_km is not None
        and poi.distance_to_anchor_km > spatial_constraint.max_radius_km
    ):
        return False
    if (
        spatial_constraint.max_travel_min is not None
        and poi.estimated_travel_minutes is not None
        and poi.estimated_travel_minutes > spatial_constraint.max_travel_min
    ):
        return False
    return True


def _parse_categories(value: Any) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _parse_hours(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(val) for key, val in value.items()}
    return {}


def _parse_attributes(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    parsed: dict[str, Any] = {}
    for key, raw in value.items():
        parsed[key] = _coerce_attribute_value(raw)
    return parsed


def _coerce_attribute_value(value: Any) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if stripped in {"True", "False"}:
        return stripped == "True"
    if stripped == "None":
        return None
    if stripped.isdigit():
        try:
            return int(stripped)
        except ValueError:
            pass

    cleaned = stripped.replace("u'", "'").replace('u"', '"')
    if cleaned.startswith("{") or cleaned.startswith("[") or cleaned.startswith("(") or cleaned.startswith("'"):
        try:
            return ast.literal_eval(cleaned)
        except (ValueError, SyntaxError):
            return cleaned.strip("'").strip('"')
    return cleaned.strip("'").strip('"')


def _extract_price_tier(attributes: dict[str, Any]) -> Optional[int]:
    raw = attributes.get("RestaurantsPriceRange2")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _price_level_from_tier(price_tier: Optional[int]) -> Optional[str]:
    if price_tier is None:
        return None
    if price_tier <= 1:
        return "low"
    if price_tier == 2:
        return "medium"
    return "high"
