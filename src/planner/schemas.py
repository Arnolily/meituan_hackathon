from collections import Counter
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from planner.vocab import ALLOWED_CATEGORIES, ALLOWED_GOALS, ALLOWED_POI_TYPES


class CitySubsetConfig(BaseModel):
    city: str
    state: str
    source_dir: Path
    output_dir: Path
    category_substring: Optional[str] = None
    include_users: bool = True


class RecordCounts(BaseModel):
    businesses: int = 0
    reviews: int = 0
    tips: int = 0
    checkins: int = 0
    users: int = 0


class CoverageMetrics(BaseModel):
    missing_hours_ratio: float = 0.0
    missing_attributes_ratio: float = 0.0


class CitySubsetMetadata(BaseModel):
    city: str
    state: str
    category_substring: Optional[str] = None
    counts: RecordCounts = Field(default_factory=RecordCounts)
    business_ids: list[str] = Field(default_factory=list)
    user_ids: list[str] = Field(default_factory=list)
    top_categories: list[tuple[str, int]] = Field(default_factory=list)
    coverage: CoverageMetrics = Field(default_factory=CoverageMetrics)


class CitySubsetAccumulator:
    """Mutable helper used while streaming the raw Yelp files."""

    def __init__(self) -> None:
        self.business_count = 0
        self.review_count = 0
        self.tip_count = 0
        self.checkin_count = 0
        self.user_count = 0
        self.business_ids: set[str] = set()
        self.user_ids: set[str] = set()
        self.category_counter: Counter[str] = Counter()
        self.missing_hours = 0
        self.missing_attributes = 0

    def to_metadata(
        self,
        *,
        city: str,
        state: str,
        category_substring: Optional[str],
    ) -> CitySubsetMetadata:
        business_count = self.business_count or 1
        return CitySubsetMetadata(
            city=city,
            state=state,
            category_substring=category_substring,
            counts=RecordCounts(
                businesses=self.business_count,
                reviews=self.review_count,
                tips=self.tip_count,
                checkins=self.checkin_count,
                users=self.user_count,
            ),
            business_ids=sorted(self.business_ids),
            user_ids=sorted(self.user_ids),
            top_categories=self.category_counter.most_common(20),
            coverage=CoverageMetrics(
                missing_hours_ratio=self.missing_hours / business_count,
                missing_attributes_ratio=self.missing_attributes / business_count,
            ),
        )


BudgetLevel = Literal["low", "medium", "high", "unknown"]
IntentParseMethod = Literal["llm"]


class Intent(BaseModel):
    raw_query: str
    city: Optional[str] = None
    target_area: Optional[str] = None
    goals: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    poi_types: list[str] = Field(default_factory=list)
    budget_level: BudgetLevel = "unknown"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    return_location: Optional[str] = None
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    parse_method: IntentParseMethod = "llm"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("goals")
    @classmethod
    def validate_goals(cls, value: list[str]) -> list[str]:
        invalid = [item for item in value if item not in ALLOWED_GOALS]
        if invalid:
            raise ValueError(f"Invalid goals: {invalid}. Allowed goals: {ALLOWED_GOALS}")
        return value

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: list[str]) -> list[str]:
        invalid = [item for item in value if item not in ALLOWED_CATEGORIES]
        if invalid:
            raise ValueError(f"Invalid categories: {invalid}. Allowed categories: {ALLOWED_CATEGORIES}")
        return value

    @field_validator("poi_types")
    @classmethod
    def validate_poi_types(cls, value: list[str]) -> list[str]:
        invalid = [item for item in value if item not in ALLOWED_POI_TYPES]
        if invalid:
            raise ValueError(f"Invalid poi_types: {invalid}. Allowed poi_types: {ALLOWED_POI_TYPES}")
        return value

    @classmethod
    def from_llm_payload(cls, payload: dict[str, Any], *, raw_query: str) -> "Intent":
        payload = dict(payload)
        payload["raw_query"] = raw_query
        payload["parse_method"] = "llm"
        return cls.model_validate(payload)


class RawPOI(BaseModel):
    business_id: str
    name: str
    address: str = ""
    city: str
    state: str
    postal_code: str = ""
    latitude: float
    longitude: float
    stars: float
    review_count: int
    is_open: bool
    categories: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    hours: dict[str, str] = Field(default_factory=dict)
    price_tier: Optional[int] = None
    price_level: Optional[str] = None
    distance_to_anchor_km: Optional[float] = None
    estimated_travel_minutes: Optional[float] = None
    retrieval_score: float = 0.0
    retrieval_reasons: list[str] = Field(default_factory=list)


class ReviewComment(BaseModel):
    review_id: str
    business_id: str
    user_id: str
    stars: float
    useful: int = 0
    funny: int = 0
    cool: int = 0
    text: str
    date: str


class TipComment(BaseModel):
    business_id: str
    user_id: str
    text: str
    date: str
    compliment_count: int = 0


class POICommentBundle(BaseModel):
    business_id: str
    name: str
    city: str
    review_count_loaded: int = 0
    tip_count_loaded: int = 0
    reviews: list[ReviewComment] = Field(default_factory=list)
    tips: list[TipComment] = Field(default_factory=list)


class GeoPoint(BaseModel):
    latitude: float
    longitude: float


class AnchorPoint(BaseModel):
    name: str = "anchor"
    latitude: float
    longitude: float


class SpatialConstraint(BaseModel):
    anchor: AnchorPoint
    max_radius_km: Optional[float] = None
    max_travel_min: Optional[float] = None
    mode: Literal["walking", "driving", "transit"] = "walking"
