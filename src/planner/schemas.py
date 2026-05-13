from collections import Counter
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


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

