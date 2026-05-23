import ast
import json
from pathlib import Path
from typing import Any, Optional

from planner.schemas import EventIntent, EventPOIGroup, GeoPoint, Intent, RawPOI, SpatialConstraint
from planner.utils.geo import anchor_to_point, estimate_travel_minutes, haversine_distance_km
from planner.vocab import GOAL_CATEGORY_HINTS, POI_TYPE_CATEGORY_HINTS


def load_candidate_pois(
    intent: Intent,
    *,
    business_file: Path,
    max_pois: Optional[int] = None,
    spatial_constraint: Optional[SpatialConstraint] = None,
) -> list[RawPOI]:
    groups = load_candidate_poi_groups(
        intent,
        business_file=business_file,
        max_pois=max_pois,
        spatial_constraint=spatial_constraint,
    )
    deduped: dict[str, RawPOI] = {}
    for group in groups:
        for poi in group.pois:
            current = deduped.get(poi.business_id)
            if current is None or poi.retrieval_score > current.retrieval_score:
                deduped[poi.business_id] = poi
    return sorted(
        deduped.values(),
        key=lambda poi: (
            -poi.retrieval_score,
            poi.distance_to_anchor_km is None,
            poi.distance_to_anchor_km if poi.distance_to_anchor_km is not None else float("inf"),
            -poi.review_count,
            -poi.stars,
            poi.name,
        ),
    )


def load_candidate_poi_groups(
    intent: Intent,
    *,
    business_file: Path,
    max_pois: Optional[int] = None,
    spatial_constraint: Optional[SpatialConstraint] = None,
) -> list[EventPOIGroup]:
    groups: list[EventPOIGroup] = []
    for index, event in enumerate(intent.events, start=1):
        pois = _load_candidate_pois_for_event(
            intent,
            event=event,
            business_file=business_file,
            max_pois=max_pois,
            spatial_constraint=spatial_constraint,
        )
        groups.append(
            EventPOIGroup(
                event_index=index,
                event_name=event.name or f"event_{index}",
                event_goal=event.goal,
                pois=pois,
            )
        )
    return groups


def _load_candidate_pois_for_event(
    intent: Intent,
    *,
    event: EventIntent,
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
            scored_poi = _score_against_event(poi, intent, event)
            if _failed_semantic_gate(scored_poi):
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


def _score_against_event(poi: RawPOI, intent: Intent, event: EventIntent) -> RawPOI:
    score = 0.0
    reasons: list[str] = []
    breakdown: dict[str, float] = {}
    trace: list[dict[str, Any]] = []

    if intent.city and poi.city.lower() != intent.city.lower():
        return poi.model_copy(
            update={
                "retrieval_score": 0.0,
                "retrieval_reasons": ["city_mismatch"],
                "retrieval_breakdown": {},
                "retrieval_trace": [{"component": "city_gate", "delta": 0.0, "reason": "city_mismatch"}],
            }
        )

    poi_categories = {category.lower() for category in poi.categories}
    if event.categories:
        category_hits = 0
        for wanted in event.categories:
            wanted_lower = wanted.lower()
            if wanted_lower in poi_categories:
                category_hits += 1
                reasons.append(f"category={wanted}")
            elif any(wanted_lower in category for category in poi_categories):
                category_hits += 1
                reasons.append(f"category_partial={wanted}")
        if category_hits == 0:
            return poi.model_copy(
                update={
                    "retrieval_score": 0.0,
                    "retrieval_reasons": ["no_category_match"],
                    "retrieval_breakdown": {},
                    "retrieval_trace": [{"component": "category_gate", "delta": 0.0, "reason": "no_category_match"}],
                }
            )
        category_score = 10.0 + (2.0 * category_hits)
        score += category_score
        _add_contribution(
            breakdown,
            trace,
            component="category_match",
            delta=category_score,
            reason=f"{category_hits} category hit(s)",
        )

    if event.poi_types:
        poi_type_hits = 0
        for poi_type in event.poi_types:
            hints = POI_TYPE_CATEGORY_HINTS.get(poi_type, set())
            if hints and poi_categories.intersection(hints):
                poi_type_hits += 1
                reasons.append(f"poi_type={poi_type}")
        poi_type_score = 2.0 * poi_type_hits
        score += poi_type_score
        if poi_type_score:
            _add_contribution(
                breakdown,
                trace,
                component="poi_type_match",
                delta=poi_type_score,
                reason=f"{poi_type_hits} poi_type hit(s)",
            )

    hints = GOAL_CATEGORY_HINTS.get(event.goal.lower(), set())
    if hints and poi_categories.intersection(hints):
        score += 1.5
        reasons.append(f"goal={event.goal}")
        _add_contribution(breakdown, trace, component="goal_match", delta=1.5, reason=f"goal={event.goal}")

    if event.target_area:
        area_text = f"{poi.name} {poi.address}".lower()
        if event.target_area.lower() in area_text:
            score += 3.0
            reasons.append("target_area_match")
            _add_contribution(breakdown, trace, component="target_area_match", delta=3.0, reason="target_area_match")

    score += _budget_score(event, poi, reasons, breakdown, trace)
    score += _soft_preference_score(intent, event, poi, poi_categories, reasons, breakdown, trace)
    score += _hard_constraint_score(intent, event, poi, poi_categories, reasons, breakdown, trace)

    quality_score = min(poi.stars, 5.0) * 0.4 + min(poi.review_count, 1000) / 1000.0
    score += quality_score
    _add_contribution(
        breakdown,
        trace,
        component="quality_prior",
        delta=round(quality_score, 3),
        reason=f"stars={poi.stars}, reviews={poi.review_count}",
    )
    rounded_score = round(score, 3)
    rounded_breakdown = {key: round(value, 3) for key, value in breakdown.items()}
    rounded_trace = [{**item, "delta": round(float(item["delta"]), 3)} for item in trace]
    return poi.model_copy(
        update={
            "retrieval_score": rounded_score,
            "retrieval_reasons": reasons,
            "retrieval_breakdown": rounded_breakdown,
            "retrieval_trace": rounded_trace,
        }
    )


def _failed_semantic_gate(poi: RawPOI) -> bool:
    return any(reason in {"city_mismatch", "no_category_match"} for reason in poi.retrieval_reasons)


def _budget_score(
    event: EventIntent,
    poi: RawPOI,
    reasons: list[str],
    breakdown: dict[str, float],
    trace: list[dict[str, Any]],
) -> float:
    if event.budget_level == "unknown":
        return 0.0
    if poi.price_tier is None:
        reasons.append("price_unknown")
        _add_contribution(breakdown, trace, component="budget_fit", delta=-20.0, reason="price_unknown")
        return -20.0
    if event.budget_level == "low":
        if poi.price_tier == 1:
            reasons.append("budget_match_low")
            _add_contribution(breakdown, trace, component="budget_fit", delta=100.0, reason="budget_match_low")
            return 100.0
        if poi.price_tier == 2:
            reasons.append("budget_near_low")
            _add_contribution(breakdown, trace, component="budget_fit", delta=-30.0, reason="budget_near_low")
            return -30.0
        reasons.append("budget_penalty_high_cost")
        _add_contribution(breakdown, trace, component="budget_fit", delta=-100.0, reason="budget_penalty_high_cost")
        return -100.0
    if event.budget_level == "medium":
        if poi.price_tier == 2:
            reasons.append("budget_match_medium")
            _add_contribution(breakdown, trace, component="budget_fit", delta=100.0, reason="budget_match_medium")
            return 100.0
        if poi.price_tier in {1, 3}:
            reasons.append("budget_near_medium")
            _add_contribution(breakdown, trace, component="budget_fit", delta=20.0, reason="budget_near_medium")
            return 20.0
        reasons.append("budget_penalty_far_medium")
        _add_contribution(breakdown, trace, component="budget_fit", delta=-60.0, reason="budget_penalty_far_medium")
        return -60.0
    if event.budget_level == "high":
        if poi.price_tier >= 3:
            reasons.append("budget_match_high")
            _add_contribution(breakdown, trace, component="budget_fit", delta=100.0, reason="budget_match_high")
            return 100.0
        if poi.price_tier == 2:
            reasons.append("budget_penalty_not_premium")
            _add_contribution(breakdown, trace, component="budget_fit", delta=-30.0, reason="budget_penalty_not_premium")
            return -30.0
        reasons.append("budget_penalty_low_cost")
        _add_contribution(breakdown, trace, component="budget_fit", delta=-80.0, reason="budget_penalty_low_cost")
        return -80.0
    return 0.0


def _soft_preference_score(
    intent: Intent,
    event: EventIntent,
    poi: RawPOI,
    poi_categories: set[str],
    reasons: list[str],
    breakdown: dict[str, float],
    trace: list[dict[str, Any]],
) -> float:
    score = 0.0
    attributes = poi.attributes
    soft_prefs = {pref.lower() for pref in intent.soft_preferences}
    soft_prefs.update(pref.lower() for pref in event.soft_preferences)

    if "premium_experience" in soft_prefs:
        if poi.price_tier and poi.price_tier >= 3:
            score += 3.0
            reasons.append("pref_premium_price")
            _add_contribution(breakdown, trace, component="soft_preference", delta=3.0, reason="pref_premium_price")
        ambience = attributes.get("Ambience")
        if isinstance(ambience, dict) and any(ambience.get(flag) for flag in ["classy", "upscale", "intimate", "trendy"]):
            score += 1.5
            reasons.append("pref_premium_ambience")
            _add_contribution(breakdown, trace, component="soft_preference", delta=1.5, reason="pref_premium_ambience")
        if attributes.get("RestaurantsReservations") is True:
            score += 0.75
            reasons.append("pref_reservations")
            _add_contribution(breakdown, trace, component="soft_preference", delta=0.75, reason="pref_reservations")

    if "high_quality_food" in soft_prefs:
        if "restaurants" in poi_categories:
            score += 1.0
            reasons.append("pref_food_category")
            _add_contribution(breakdown, trace, component="soft_preference", delta=1.0, reason="pref_food_category")
        if poi.stars >= 4.3:
            score += 1.5
            reasons.append("pref_high_rating")
            _add_contribution(breakdown, trace, component="soft_preference", delta=1.5, reason="pref_high_rating")

    if "high_end_atmosphere" in soft_prefs:
        ambience = attributes.get("Ambience")
        if isinstance(ambience, dict) and any(ambience.get(flag) for flag in ["classy", "upscale", "romantic", "trendy"]):
            score += 1.5
            reasons.append("pref_atmosphere")
            _add_contribution(breakdown, trace, component="soft_preference", delta=1.5, reason="pref_atmosphere")
        if "bars" in poi_categories or "cocktail bars" in poi_categories:
            score += 0.75
            reasons.append("pref_bar_atmosphere")
            _add_contribution(breakdown, trace, component="soft_preference", delta=0.75, reason="pref_bar_atmosphere")

    if "budget_sensitive" in soft_prefs and poi.price_tier is not None:
        if poi.price_tier == 1:
            score += 2.0
            reasons.append("pref_budget_value")
            _add_contribution(breakdown, trace, component="soft_preference", delta=2.0, reason="pref_budget_value")
        elif poi.price_tier >= 3:
            score -= 2.0
            reasons.append("pref_budget_penalty")
            _add_contribution(breakdown, trace, component="soft_preference", delta=-2.0, reason="pref_budget_penalty")

    if "good_view" in soft_prefs and attributes.get("OutdoorSeating") is True:
        score += 0.5
        reasons.append("pref_outdoor")
        _add_contribution(breakdown, trace, component="soft_preference", delta=0.5, reason="pref_outdoor")

    return score


def _hard_constraint_score(
    intent: Intent,
    event: EventIntent,
    poi: RawPOI,
    poi_categories: set[str],
    reasons: list[str],
    breakdown: dict[str, float],
    trace: list[dict[str, Any]],
) -> float:
    score = 0.0
    hard_constraints = " ".join(intent.hard_constraints + event.hard_constraints).lower()

    if "must_include_dinner" in hard_constraints and "restaurants" in poi_categories:
        score += 2.0
        reasons.append("constraint_dinner")
        _add_contribution(breakdown, trace, component="hard_constraint", delta=2.0, reason="constraint_dinner")

    if "minor present" in hard_constraints or "non-alcoholic" in hard_constraints:
        if poi.attributes.get("GoodForKids") is True:
            score += 1.0
            reasons.append("constraint_minor_friendly")
            _add_contribution(breakdown, trace, component="hard_constraint", delta=1.0, reason="constraint_minor_friendly")
        if "coffee & tea" in poi_categories or "cafes" in poi_categories:
            score += 1.0
            reasons.append("constraint_non_alcoholic_option")
            _add_contribution(
                breakdown,
                trace,
                component="hard_constraint",
                delta=1.0,
                reason="constraint_non_alcoholic_option",
            )

    return score


def _add_contribution(
    breakdown: dict[str, float],
    trace: list[dict[str, Any]],
    *,
    component: str,
    delta: float,
    reason: str,
) -> None:
    breakdown[component] = breakdown.get(component, 0.0) + delta
    trace.append({"component": component, "delta": delta, "reason": reason})


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
