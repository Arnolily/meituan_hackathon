# V1 Engineering Plan

## Goal

Build the first data-centric version of the route-planning agent.

V1 does not solve full map routing yet. Its goal is to turn the raw Yelp dataset into high-quality candidate POI cards that can later feed route generation.

V1 scope:
1. City Subset Builder
2. Intent Parser
3. POI Loader
4. Comment Loader
5. Comment Summarizer
6. POI Feature Aggregator
7. Hard Constraint Filter

Although this is seven named steps, `City Subset Builder` is an offline preprocessing step. The first six online modules remain:

```text
Intent Parser
-> POI Loader
-> Comment Loader
-> Comment Summarizer
-> POI Feature Aggregator
-> Hard Constraint Filter
```

## Reference Repo Lessons

### From `novel_agent`

Use a staged workflow.

`novel_agent` separates a large generation task into stages such as Bible, Outline, Chapter Outline, Section List, and Writing. We should copy this idea: each stage has a clear input, a clear output, and can be inspected independently.

For this project:
- every module writes an inspectable artifact
- downstream modules consume structured outputs, not raw prompt text
- users can debug or review intermediate results

### From `openclaw`

Use explicit contracts and module boundaries.

`openclaw` uses schemas, package boundaries, tests, and clear runtime/config separation. We should copy this idea: each planner module should expose a small interface and validate its inputs/outputs.

For this project:
- define schemas before implementing logic
- keep provider-specific LLM code outside planner logic
- write tests for module contracts and data transforms

## Recommended V1 Stack

Use Python for V1 data engineering.

Reason:
- Yelp files are large JSONL files
- preprocessing, filtering, aggregation, and sampling are easier in Python
- the existing density script is already Python
- the output can be written to SQLite/Parquet and consumed later by a web app

Recommended dependencies:
- `pydantic`: data contracts
- `duckdb`: analytics over large local files
- `sqlite-utils` or Python `sqlite3`: local query store
- `pytest`: tests
- `ruff`: linting and formatting
- optional `openai` or other LLM SDK: intent parsing and comment summarization

Avoid depending on a web framework in V1. Add Next.js only after the data pipeline is stable.

## Proposed Directory Structure

```text
meituan/
├── architecture.md
├── v1_engineering_plan.md
├── scripts/
│   ├── city_poi_density.py
│   ├── build_city_subset.py
│   ├── run_v1_pipeline.py
│   └── inspect_outputs.py
├── src/
│   └── planner/
│       ├── __init__.py
│       ├── config.py
│       ├── schemas.py
│       ├── io/
│       │   ├── yelp_reader.py
│       │   └── artifact_store.py
│       ├── modules/
│       │   ├── intent_parser.py
│       │   ├── poi_loader.py
│       │   ├── comment_loader.py
│       │   ├── comment_summarizer.py
│       │   ├── poi_feature_aggregator.py
│       │   └── hard_constraint_filter.py
│       ├── llm/
│       │   ├── client.py
│       │   └── prompts.py
│       └── utils/
│           ├── geo.py
│           └── time.py
├── data/
│   ├── raw/
│   │   └── yelp_dataset/
│   ├── interim/
│   │   └── city_subsets/
│   └── processed/
│       └── v1/
└── tests/
    ├── test_schemas.py
    ├── test_city_subset_builder.py
    ├── test_poi_loader.py
    ├── test_comment_loader.py
    ├── test_poi_feature_aggregator.py
    └── test_hard_constraint_filter.py
```

Current local Yelp data is in `yelp_dataset/`. We can either keep it there or symlink/copy it under `data/raw/yelp_dataset/` later.

## Data Contracts

Define all module I/O in `src/planner/schemas.py`.

### `Intent`

```python
class Intent(BaseModel):
    raw_query: str
    city: str | None
    target_area: str | None
    goals: list[str]
    categories: list[str]
    budget_level: Literal["low", "medium", "high", "unknown"]
    start_time: str | None
    end_time: str | None
    hard_constraints: list[str]
    soft_preferences: list[str]
```

### `RawPOI`

```python
class RawPOI(BaseModel):
    business_id: str
    name: str
    city: str
    state: str
    latitude: float
    longitude: float
    stars: float
    review_count: int
    categories: list[str]
    attributes: dict[str, Any]
    hours: dict[str, str] | None
    is_open: bool
```

### `CommentBundle`

```python
class CommentBundle(BaseModel):
    business_id: str
    reviews: list[str]
    tips: list[str]
    review_stars: list[float]
```

### `CommentSignal`

```python
class CommentSignal(BaseModel):
    business_id: str
    tags: list[str]
    positive_signals: list[str]
    negative_signals: list[str]
    short_summary: str
    confidence: float
```

### `CheckinFeatures`

```python
class CheckinFeatures(BaseModel):
    business_id: str
    checkin_count: int
    peak_hours: list[int]
    night_active: bool
    weekend_busy: bool
```

### `POICard`

```python
class POICard(BaseModel):
    business_id: str
    name: str
    city: str
    state: str
    latitude: float
    longitude: float
    categories: list[str]
    stars: float
    review_count: int
    hours: dict[str, str] | None
    price_level: str | None
    comment_signal: CommentSignal | None
    checkin_features: CheckinFeatures | None
    derived_tags: list[str]
```

### `FilteredPOIResult`

```python
class FilteredPOIResult(BaseModel):
    kept: list[POICard]
    rejected: list[dict[str, str]]
```

The `rejected` list is important for XAI. It records why each POI was removed.

## Storage Plan

V1 should produce both machine-readable artifacts and human-inspectable samples.

Recommended outputs:
- `data/interim/city_subsets/{city}/business.jsonl`
- `data/interim/city_subsets/{city}/review.jsonl`
- `data/interim/city_subsets/{city}/tip.jsonl`
- `data/interim/city_subsets/{city}/user.jsonl`
- `data/interim/city_subsets/{city}/checkin.jsonl`
- `data/processed/v1/{city}/poi_cards.jsonl`
- `data/processed/v1/{city}/filtered_pois.json`
- `data/processed/v1/{city}/pipeline_trace.json`

Use JSONL first. Add SQLite only when retrieval speed becomes a bottleneck.

## Module Plan

## 0. City Subset Builder

File:
- `scripts/build_city_subset.py`
- `src/planner/io/yelp_reader.py`

Input:
- raw Yelp JSONL files
- selected `city`
- selected `state`
- optional category filter

Output:
- city-level JSONL files
- city-level metadata report

Responsibilities:
- filter `business.json` by city/state
- collect valid `business_id`
- filter `review.json`, `tip.json`, and `checkin.json` by `business_id`
- filter `user.json` by users appearing in city reviews/tips, if feasible
- write counts and coverage metrics

Required metrics:
- number of POIs
- number of reviews
- number of tips
- number of check-in records
- number of users
- top categories
- missing hours ratio
- missing attributes ratio

Implementation notes:
- stream JSONL line by line
- do not load full `review.json` into memory
- write deterministic outputs

Tests:
- small fixture with 3 businesses, 4 reviews, 2 tips, 1 check-in
- verify only linked records are kept

## 1. Intent Parser

File:
- `src/planner/modules/intent_parser.py`

Input:
- raw user query
- optional default city

Output:
- `Intent`

Responsibilities:
- extract city/area if present
- extract activity goals
- split hard constraints and soft preferences
- map user language to Yelp category hints

For V1, implement two modes:
- `rule_based_parse()`: deterministic baseline
- `llm_parse()`: optional LLM parser with schema validation

Examples:
- "cheap dinner near downtown before 8pm" -> categories include `Restaurants`, budget is `low`, end_time is `20:00`
- "scenic coffee place" -> categories include `Coffee & Tea`, soft preference includes `good_view`

Implementation notes:
- the LLM must return JSON only
- validate with Pydantic
- fall back to rule-based parsing if LLM output fails validation

Tests:
- fixed prompts with expected structured fields
- invalid LLM JSON fallback test

## 2. POI Loader

File:
- `src/planner/modules/poi_loader.py`

Input:
- `Intent`
- city subset `business.jsonl`

Output:
- list of `RawPOI`

Responsibilities:
- load candidate POIs from selected city
- filter by category hints
- keep coordinates, hours, attributes, stars, review count
- normalize categories from comma-separated string to list
- parse common service attributes

Yelp fields to preserve:
- `business_id`
- `name`
- `address`
- `city`
- `state`
- `latitude`
- `longitude`
- `stars`
- `review_count`
- `is_open`
- `attributes`
- `categories`
- `hours`

Implementation notes:
- do not discard low-star POIs in this module
- do not summarize reviews here
- this module answers: "which places are candidates?"

Tests:
- category matching
- open/closed parsing
- missing fields handling

## 3. Comment Loader

File:
- `src/planner/modules/comment_loader.py`

Input:
- candidate `business_id` list
- city subset `review.jsonl`
- city subset `tip.jsonl`

Output:
- list of `CommentBundle`

Responsibilities:
- collect top-N reviews per POI
- collect top-N tips per POI
- preserve review stars
- optionally prefer recent or high-useful reviews

Default selection policy:
- max 20 reviews per POI
- max 10 tips per POI
- sort reviews by `useful`, then recency
- keep both positive and negative examples when possible

Implementation notes:
- reviews are long; cap text length before LLM summarization
- tips are short and should be included when available
- this module answers: "what raw UGC is attached to this POI?"

Tests:
- top-N selection
- no-comment POI handling
- review/tip merge by `business_id`

## 4. Comment Summarizer

File:
- `src/planner/modules/comment_summarizer.py`
- `src/planner/llm/prompts.py`

Input:
- `CommentBundle`

Output:
- `CommentSignal`

Responsibilities:
- convert raw reviews/tips into compact tags
- separate positive and negative signals
- produce short summary
- record confidence

Recommended tag vocabulary:
- `cheap`
- `expensive`
- `fast_service`
- `slow_service`
- `crowded`
- `good_for_groups`
- `good_for_family`
- `romantic`
- `good_view`
- `photo_friendly`
- `local_specialty`
- `tourist_trap`
- `good_dinner`
- `good_breakfast`
- `outdoor_seating`
- `parking_easy`
- `parking_hard`

For V1, implement two modes:
- `keyword_summarize()`: deterministic baseline
- `llm_summarize()`: optional higher-quality summarizer

Implementation notes:
- output must be schema-validated
- cache summaries by `business_id` and source text hash
- keep the raw evidence IDs or text snippets used for summary

Tests:
- keyword mapping test
- schema validation test
- cache hit test

## 5. POI Feature Aggregator

File:
- `src/planner/modules/poi_feature_aggregator.py`

Input:
- `RawPOI`
- `CommentSignal`
- `checkin.jsonl`

Output:
- `POICard`

Responsibilities:
- merge structured POI data with UGC signals
- compute check-in features
- derive planning tags
- preserve explanation-relevant fields

Check-in feature logic:
- `checkin_count`: total timestamps
- `peak_hours`: top 3 hours by count
- `night_active`: true if many check-ins happen after 18:00
- `weekend_busy`: true if Saturday/Sunday share is high

Derived tag examples:
- if category includes `Restaurants` and comment tags include `good_dinner`, add `dinner_candidate`
- if stars >= 4.5 and review_count >= 100, add `high_confidence_quality`
- if comment tags include `crowded` and weekend_busy is true, add `queue_risk`
- if hours missing, add `hours_unknown`

Implementation notes:
- the aggregator should not filter yet
- every derived tag should be explainable from source fields
- this module produces the main artifact for later route generation

Tests:
- check-in timestamp parsing
- derived tag generation
- missing comment/check-in handling

## 6. Hard Constraint Filter

File:
- `src/planner/modules/hard_constraint_filter.py`

Input:
- `Intent`
- list of `POICard`

Output:
- `FilteredPOIResult`

Responsibilities:
- remove POIs violating hard constraints
- preserve rejection reasons
- leave soft preferences for later scoring

Hard constraints in V1:
- city mismatch
- category mismatch when the user requires a specific activity
- closed business if `is_open` is false
- opening hours incompatible with requested time, when hours are available
- missing coordinates

Do not filter directly on:
- low stars
- expensive
- crowded
- weak preference match

Those are scoring factors for V2.

Implementation notes:
- every rejection must include `business_id`, `name`, and `reason`
- if data is unknown, prefer keeping with a warning tag instead of rejecting

Tests:
- closed POI rejection
- missing coordinates rejection
- unknown hours kept with warning
- rejection reason correctness

## Pipeline Runner

File:
- `scripts/run_v1_pipeline.py`

CLI:

```bash
python3 scripts/run_v1_pipeline.py \
  --city "Philadelphia" \
  --state "PA" \
  --query "cheap dinner with good view before 8pm" \
  --max-pois 100
```

Responsibilities:
- load config
- run modules in order
- write each stage artifact
- write final filtered POIs
- write trace file

Trace structure:

```json
{
  "query": "...",
  "intent": {},
  "candidate_count": 100,
  "comment_bundle_count": 100,
  "summary_count": 100,
  "poi_card_count": 100,
  "kept_count": 72,
  "rejected_count": 28
}
```

## LLM Boundary

Only two V1 modules should optionally call an LLM:
- `Intent Parser`
- `Comment Summarizer`

All other modules should be deterministic.

Provider interface:

```python
class LLMClient(Protocol):
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        ...
```

Rules:
- planner modules depend on `LLMClient`, not a specific provider SDK
- LLM outputs are validated by Pydantic
- failed validation falls back to deterministic mode
- prompts live in `src/planner/llm/prompts.py`

This follows the same engineering idea as `novel_agent`'s provider wrapper and `openclaw`'s contract-oriented modules.

## Testing Strategy

Test levels:

1. Schema tests
- validate required fields
- reject malformed outputs

2. Module unit tests
- each module tested with tiny fixtures
- no LLM required in unit tests

3. Pipeline smoke test
- run full V1 pipeline on a tiny synthetic Yelp-like fixture
- assert final artifacts exist

4. Real-data smoke test
- run on one small city subset with `--max-pois 20`
- confirm runtime and output shape

Minimum commands:

```bash
pytest
python3 scripts/city_poi_density.py --top 10
python3 scripts/run_v1_pipeline.py --city "Philadelphia" --state "PA" --query "cheap dinner with good view before 8pm" --max-pois 20
```

## Build Order

1. Add project scaffolding
- `src/planner`
- `tests`
- `pyproject.toml`
- basic dependencies

2. Implement schemas
- all Pydantic models
- schema tests

3. Implement City Subset Builder
- stream raw Yelp files
- write city subset artifacts
- test on tiny fixtures

4. Implement POI Loader
- normalize Yelp business records
- category filtering

5. Implement Comment Loader
- join reviews and tips by `business_id`
- top-N selection

6. Implement deterministic Comment Summarizer
- keyword baseline
- schema output

7. Implement POI Feature Aggregator
- check-in feature extraction
- derived tags

8. Implement Hard Constraint Filter
- rejection reasons
- final filtered artifact

9. Implement V1 Pipeline Runner
- stage-by-stage execution
- trace file

10. Add optional LLM parser/summarizer
- only after deterministic pipeline works

## Engineering Decisions

- Use JSONL artifacts first because they are inspectable and easy to debug.
- Keep SQLite optional until query speed becomes a real bottleneck.
- Do not call LLMs inside data loading or filtering.
- Keep raw Yelp records separate from normalized internal schemas.
- Preserve rejection reasons for XAI and debugging.
- Prefer keeping uncertain POIs with warning tags over filtering them out early.
- Treat `checkin.json` as temporal popularity data, not map data.
- Keep V1 independent from map routing so the project can progress without road-network data.

## V1 Success Criteria

V1 is complete when:
- a city subset can be built from the Yelp dump
- a user query can be parsed into `Intent`
- candidate POIs can be loaded and normalized
- reviews and tips can be attached to candidate POIs
- comments can be summarized into compact signals
- check-ins can be converted into temporal features
- final POI cards can be filtered by hard constraints
- every stage writes an artifact
- every rejected POI has an explanation
- the pipeline runs on at least one dense city, preferably `Philadelphia, PA`
