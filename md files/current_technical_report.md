# Current Technical Report

This document describes the current implemented system state in the codebase.

It focuses on:
- data structures
- the output form of the intent parser
- the current keyword / vocabulary dictionaries
- the inner logic of the POI loader


## 0. Source Of Truth

The canonical vocabularies now live in [vocab.py](/home/arnold/code/meituan/src/planner/vocab.py:1).

That file is now the source of truth for:
- allowed `goals`
- allowed `categories`
- allowed `poi_types`
- `GOAL_CATEGORY_HINTS`
- `POI_TYPE_CATEGORY_HINTS`

This means:
- the prompt reads from the shared vocabulary
- the `Intent` schema validates against the same vocabulary
- the `POI Loader` scores against the same vocabulary

So `goals` are no longer just prompt-guided strings. They are now schema-validated.


## 1. Current Pipeline

The current implemented pipeline is:

1. `Intent Parser`
   - input: raw user query
   - output: structured `Intent`
   - implementation: LLM-only

2. `POI Loader`
   - input: `Intent` + Yelp `business.json` subset + optional spatial constraint
   - output: ranked list of `RawPOI`
   - implementation: deterministic code only, no LLM

3. `Comment Loader`
   - input: selected `RawPOI` list + subset `review.json` + subset `tip.json`
   - output: grouped raw UGC bundles per POI
   - implementation: deterministic code only, no LLM

4. `GUI / Cache Layer`
   - stores the latest parsed intent in `cache/intents/`
   - stores the latest loaded POIs in `cache/pois/`
   - stores the latest loaded comments in `cache/comments/`
   - displays all three in `Streamlit`


## 2. Data Structures

The core runtime data structures currently live in [schemas.py](/home/arnold/code/meituan/src/planner/schemas.py:1).

### 2.1 Intent

`Intent` is the structured output of the intent parser.

Important:
- `goals` are now validated against the shared goal vocabulary
- `categories` are now validated against the shared category vocabulary
- `poi_types` are now validated against the shared planner vocabulary

```python
class Intent(BaseModel):
    raw_query: str
    city: Optional[str] = None
    target_area: Optional[str] = None
    goals: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    poi_types: list[str] = Field(default_factory=list)
    budget_level: Literal["low", "medium", "high", "unknown"] = "unknown"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    return_location: Optional[str] = None
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    parse_method: Literal["llm"] = "llm"
    confidence: float
```

Meaning of the main fields:
- `raw_query`: original user text
- `city`: canonical city name used for retrieval
- `target_area`: local area hint if present
- `goals`: semantic goals such as `dinner`, `museum`, `park`, `live_music`
- `categories`: retrieval-oriented Yelp category hints from the Philadelphia subset vocabulary
- `poi_types`: planner-oriented abstract types such as `food_drink`, `museum`, `park_outdoor`
- `budget_level`: normalized budget signal
- `start_time`, `end_time`: parsed time hints
- `return_location`: anchor like hotel or home
- `hard_constraints`: must-satisfy textual constraints
- `soft_preferences`: preference signals for ranking
- `confidence`: parser confidence


### 2.2 RawPOI

`RawPOI` is the normalized POI object produced by the POI loader.

```python
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
```

Meaning of the planner-specific fields:
- `price_tier`: raw Yelp price tier from `RestaurantsPriceRange2`
- `price_level`: derived label: `low`, `medium`, `high`
- `distance_to_anchor_km`: straight-line distance to current anchor
- `estimated_travel_minutes`: heuristic travel time
- `retrieval_score`: total score assigned by POI loader
- `retrieval_reasons`: explanation tags describing why the POI scored as it did


### 2.3 POICommentBundle

The `Comment Loader` output is grouped by POI.

```python
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
    reviews: list[ReviewComment]
    tips: list[TipComment]
```

Meaning:
- `reviews`: selected raw review records for this POI
- `tips`: selected raw tip records for this POI
- `review_count_loaded`: number kept after sort/cap
- `tip_count_loaded`: number kept after sort/cap


### 2.4 SpatialConstraint

The current spatial filter is:

```python
class SpatialConstraint(BaseModel):
    anchor: AnchorPoint
    max_radius_km: Optional[float] = None
    max_travel_min: Optional[float] = None
    mode: Literal["walking", "driving", "transit"] = "walking"
```

This is used by the POI loader after semantic scoring.


## 3. Output Form of the Intent Parser

The intent parser is implemented in:
- [intent_parser.py](/home/arnold/code/meituan/src/planner/modules/intent_parser.py:1)
- [prompts.py](/home/arnold/code/meituan/src/planner/llm/prompts.py:1)

It is currently:
- LLM-only
- OpenAI-compatible API client
- JSON output only
- cached to `cache/intents/`

### 3.1 Output JSON Shape

The prompt requires the model to return a JSON object with:

```json
{
  "city": "Philadelphia",
  "target_area": null,
  "goals": ["dinner", "nightlife"],
  "categories": ["Restaurants", "Bars", "Cocktail Bars"],
  "poi_types": ["food_drink", "nightlife"],
  "budget_level": "high",
  "start_time": null,
  "end_time": "02:00",
  "return_location": "hotel",
  "hard_constraints": ["return_to_hotel"],
  "soft_preferences": ["premium_experience", "high_end_atmosphere"],
  "confidence": 0.92
}
```

After that, `Intent.from_llm_payload(...)` wraps it into the `Intent` object and adds:
- `raw_query`
- `parse_method = "llm"`


### 3.2 Intent Parser Responsibilities

The current parser is expected to do these transformations:
- convert Chinese or aliases into canonical English city names when possible
- convert vague place requests into controlled retrieval categories
- preserve semantic goals separately from retrieval categories
- infer indirect meaning

Examples:
- `fine dining`
  - `categories=["Restaurants"]`
  - `poi_types=["food_drink"]`
  - `budget_level="high"`
  - `soft_preferences=["premium_experience"]`

- `high-end bar`
  - `categories=["Bars", "Cocktail Bars"]`
  - `poi_types=["nightlife"]`
  - `soft_preferences=["premium_experience"]`

- `good restaurant`
  - `categories=["Restaurants"]`
  - `soft_preferences=["high_quality_food"]`


## 4. Current Vocabulary / Keyword Dictionaries

There are two layers of vocabulary:
- prompt-level controlled vocabulary for the intent parser
- code-level hint dictionaries for the POI loader


### 4.1 Allowed `categories` in the Intent Parser Prompt

The category vocabulary is now the full raw Yelp category surface found in the Philadelphia subset.

It lives in [vocab.py](/home/arnold/code/meituan/src/planner/vocab.py:1) as `ALLOWED_CATEGORIES`.

Important examples now covered explicitly:
- `Museums`
- `Art Museums`
- `Parks`
- `Landmarks & Historical Buildings`
- `Visitor Centers`
- `Tours`
- `Historical Tours`
- `Walking Tours`
- `Music Venues`
- `Performing Arts`
- `Festivals`
- `Sports Clubs`
- `Hotels`
- `Casinos`

These are still retrieval hints, not final route labels.


### 4.2 Allowed `poi_types` in the Intent Parser Prompt

Current planner-facing vocabulary in the prompt and schema:

- `food_drink`
- `nightlife`
- `shopping`
- `sightseeing`
- `museum`
- `park_outdoor`
- `culture`
- `performance`
- `tour`
- `sports`
- `family_activity`
- `entertainment`
- `event`
- `lodging`
- `transport`
- `service`
- `wellness`
- `activity`


### 4.3 Allowed `goals`

Current goal vocabulary in the prompt and schema:

- `breakfast`
- `coffee`
- `lunch`
- `dinner`
- `dessert`
- `drinks`
- `nightlife`
- `live_music`
- `dancing`
- `shopping`
- `sightseeing`
- `museum`
- `park`
- `historical_site`
- `art_gallery`
- `performance`
- `tour`
- `sports`
- `festival`
- `family_activity`
- `games`
- `hotel_stay`
- `casino`

Important:
- free-form goals like `fine dining` are not valid goals anymore
- that meaning should instead be represented as:
  - `goals=["dinner"]`
  - `budget_level="high"`
  - `soft_preferences=["premium_experience"]`


### 4.4 Canonicalization Examples in the Prompt

The prompt explicitly teaches examples such as:

- `费城` -> `Philadelphia`
- `高端酒吧` -> `Bars`, `Cocktail Bars`
- `fine dining` -> `Restaurants`
- `brunch` -> `Breakfast & Brunch`
- `coffee shop` -> `Coffee & Tea`, `Cafes`
- `scenic walk` -> `Active Life`, `Arts & Entertainment`


### 4.5 POI Loader `POI_TYPE_CATEGORY_HINTS`

The POI loader now has a broader planner mapping in [vocab.py](/home/arnold/code/meituan/src/planner/vocab.py:1).

Examples:
- `museum` -> `Museums`, `Art Museums`
- `park_outdoor` -> `Parks`, `Beaches`, `Boating`, `Walking Tours`
- `culture` -> `Art Galleries`, `Museums`, `Performing Arts`, `Landmarks & Historical Buildings`
- `performance` -> `Performing Arts`, `Music Venues`, `Comedy Clubs`, `Dinner Theater`
- `tour` -> `Tours`, `Historical Tours`, `Walking Tours`, `Boat Tours`

This dictionary is not shown to the LLM. It is used internally by the POI loader for scoring.


### 4.6 POI Loader `GOAL_CATEGORY_HINTS`

The goal-to-category hint dictionary is also broader now.

Examples:
- `museum` -> `Museums`, `Art Museums`
- `park` -> `Parks`, `Beaches`, `Active Life`
- `historical_site` -> `Landmarks & Historical Buildings`, `Historical Tours`
- `art_gallery` -> `Art Galleries`
- `live_music` -> `Music Venues`, `Jazz & Blues`
- `games` -> `Arcades`, `Escape Games`, `Bowling`, `Mini Golf`, `Tabletop Games`
- `casino` -> `Casinos`


### 4.7 Soft Preference Keywords Currently Recognized by the POI Loader

The current loader has explicit logic for these `soft_preferences`:

- `premium_experience`
- `high_quality_food`
- `high_end_atmosphere`
- `budget_sensitive`
- `good_view`

These are meaningful because the loader has scoring logic for them.


### 4.8 Hard Constraint Keywords Currently Recognized by the POI Loader

The current loader has explicit heuristic logic for these `hard_constraints`:

- `must_include_dinner`
- strings containing `minor present`
- strings containing `non-alcoholic`

Important: this is still only partial support. Most hard constraints are not yet deeply enforced.


## 5. How POI Loader Works Internally

The POI loader is implemented in [poi_loader.py](/home/arnold/code/meituan/src/planner/modules/poi_loader.py:1).

Important:
- it does not use an LLM
- it is fully deterministic code


### 5.1 High-Level Flow

For each record in Yelp `business.json`:

1. normalize the raw Yelp record into `RawPOI`
2. compute semantic score against the `Intent`
3. drop the POI if the score is `<= 0`
4. if spatial constraint exists:
   - compute distance and travel time
   - drop the POI if it violates radius or travel limit
5. keep surviving POIs
6. sort by retrieval priority
7. truncate to `max_pois` if requested


### 5.2 Step 1: Normalize Raw Yelp Record

The loader extracts:
- categories
- attributes
- hours
- price tier

Normalization details:
- `categories` are split from the raw comma-separated string
- `attributes` are recursively coerced from string values into bool/int/dict where possible
- `hours` are preserved as a simple dictionary
- `price_tier` is taken from `attributes["RestaurantsPriceRange2"]`
- `price_level` is derived as:
  - `1` -> `low`
  - `2` -> `medium`
  - `3`, `4` -> `high`


### 5.3 Step 2: Semantic Hard Gate

The first hard checks are:

#### A. City check
If `intent.city` exists and does not equal `poi.city`, the POI is rejected immediately.

Reason tag:
- `city_mismatch`

#### B. Category check
If `intent.categories` exists and none of them match the POI categories, the POI is rejected immediately.

Reason tag:
- `no_category_match`

So current retrieval is still category-centered at the gate level.


### 5.4 Step 3: Retrieval Score Calculation

If the POI survives the hard gate, the loader computes `retrieval_score`.

The score is a manual sum of several components.


#### A. Category match

If category matching succeeds:

- base score: `+10`
- each category hit: `+2`

Reason examples:
- `category=Restaurants`
- `category=Cocktail Bars`
- `category_partial=Bars`


#### B. `poi_types` match

For each `poi_type` that maps to at least one matching POI category:

- `+2` per hit

Reason example:
- `poi_type=nightlife`


#### C. `goals` match

For each goal that maps to matching category hints:

- `+1.5` per hit

Reason example:
- `goal=dinner`


#### D. `target_area` match

If `intent.target_area` appears in:
- POI name, or
- POI address

then:
- `+3`

Reason:
- `target_area_match`


#### E. Budget score

Budget is currently interpreted against `price_tier`.

If `budget_level = low`:
- tier `1`: `+3`
- tier `2`: `+1`
- tier `3/4`: `-3`

If `budget_level = medium`:
- tier `2`: `+3`
- tier `1/3`: `+1`
- tier `4`: `-1.5`

If `budget_level = high`:
- tier `3/4`: `+4`
- tier `2`: `-1.5`
- tier `1`: `-3`

Reason examples:
- `budget_match_low`
- `budget_near_medium`
- `budget_match_high`
- `budget_penalty_not_premium`
- `budget_penalty_low_cost`


#### F. Soft preference score

##### `premium_experience`

Adds:
- `+3` if `price_tier >= 3`
- `+1.5` if ambience includes flags like `classy`, `upscale`, `intimate`, `trendy`
- `+0.75` if `RestaurantsReservations == True`

Reasons:
- `pref_premium_price`
- `pref_premium_ambience`
- `pref_reservations`

##### `high_quality_food`

Adds:
- `+1` if category includes `restaurants`
- `+1.5` if `stars >= 4.3`

Reasons:
- `pref_food_category`
- `pref_high_rating`

##### `high_end_atmosphere`

Adds:
- `+1.5` for upscale / romantic / trendy ambience
- `+0.75` if category includes `bars` or `cocktail bars`

Reasons:
- `pref_atmosphere`
- `pref_bar_atmosphere`

##### `budget_sensitive`

Adds:
- `+2` if cheap
- `-2` if expensive

Reasons:
- `pref_budget_value`
- `pref_budget_penalty`

##### `good_view`

Adds:
- `+0.5` if `OutdoorSeating == True`

Reason:
- `pref_outdoor`


#### G. Hard constraint heuristics

Current support is shallow and keyword-based.

If hard constraints contain `must_include_dinner`:
- `+2` for restaurants

Reason:
- `constraint_dinner`

If hard constraints mention `minor present` or `non-alcoholic`:
- `+1` if `GoodForKids == True`
- `+1` if category includes `coffee & tea` or `cafes`

Reasons:
- `constraint_minor_friendly`
- `constraint_non_alcoholic_option`


#### H. Quality prior

Every POI also gets a small prior score:

- `stars * 0.4`
- `min(review_count, 1000) / 1000`

This biases ranking toward:
- better rated places
- more reviewed places


#### I. Missing price penalty

If `price_level` is unknown:
- `-0.25`

Reason:
- `price_unknown`


### 5.5 Step 4: Spatial Annotation and Filtering

If a `SpatialConstraint` is provided, the loader computes:

- `distance_to_anchor_km`
- `estimated_travel_minutes`

Distance:
- straight-line haversine distance

Travel time:
- heuristic by mode
- current modes:
  - `walking`
  - `driving`
  - `transit`

Then the POI is filtered out if:
- `distance_to_anchor_km > max_radius_km`, or
- `estimated_travel_minutes > max_travel_min`

Important: semantic scoring happens first, then spatial filtering.


### 5.6 Step 5: Final Sorting

POIs are sorted by:

1. higher `retrieval_score`
2. having distance information
3. smaller distance to anchor
4. higher `review_count`
5. higher `stars`
6. name

So the current loader is:
- semantic-first
- then spatially practical
- then popularity/quality aware


## 6. What the Current POI Loader Does Not Yet Do

This matters for interpreting current system limits.

The current loader does not yet enforce:
- opening-hours fit with `start_time` / `end_time`
- return-to-hotel feasibility
- sequencing between multiple POIs
- travel time between POIs
- route-level optimization
- comment or tip understanding

Important example:

If the user says:
- `I want to go to a bar and head back to hotel at 2am`

Current behavior:
- the parser may extract `end_time = "02:00"`
- the loader may rank bars highly
- but the loader does not yet check whether the bar is actually open until `02:00`

So time fields are currently parsed, but not yet enforced in the POI retrieval logic.


## 7. Comment Loader Logic

The `Comment Loader` is implemented in:
- [comment_loader.py](/home/arnold/code/meituan/src/planner/modules/comment_loader.py:1)
- [comment_cache.py](/home/arnold/code/meituan/src/planner/io/comment_cache.py:1)
- [load_comments.py](/home/arnold/code/meituan/scripts/load_comments.py:1)

It does not use an LLM.

### 7.1 Input

It consumes:
- cached POIs, usually from `cache/pois/latest_pois.json`
- subset review file:
  - `yelp_academic_dataset_review.json`
- subset tip file:
  - `yelp_academic_dataset_tip.json`

### 7.2 Core Logic

For the selected POIs:

1. build a `business_id` set
2. stream through the subset `review.json`
3. keep only reviews whose `business_id` is in the selected POIs
4. stream through the subset `tip.json`
5. keep only tips whose `business_id` is in the selected POIs
6. group the results by POI
7. sort and cap per POI

### 7.3 Sorting and Caps

Reviews are sorted by:
- `useful`
- then `date`
- then `review_id`

Tips are sorted by:
- `date`
- then `compliment_count`
- then `user_id`

Current default caps:
- `max_reviews_per_poi = 20`
- `max_tips_per_poi = 10`

### 7.4 Cache Output

Comment artifacts are written to:
- keyed cache file under `cache/comments/`
- `cache/comments/latest_comments.json`

So the pipeline now has:
- `latest_intent.json`
- `latest_pois.json`
- `latest_comments.json`


## 8. GUI Integration

The Streamlit app now exposes three pipeline steps:

1. `Parse Intent`
2. `Load POIs`
3. `Load Comments`

The GUI now shows:
- latest intent summary
- latest POI table
- map with current anchor and POIs
- POI detail panel
- latest comment table
- comment detail panel


## 9. Practical Summary

The current implemented design is:

- `Intent Parser`
  - LLM-based
  - controlled vocabulary output
  - semantic understanding plus some inferred preferences

- `POI Loader`
  - deterministic
  - semantic hard gate on city and categories
  - manual retrieval scoring
  - optional spatial pruning
  - outputs explanation tags via `retrieval_reasons`

- `Comment Loader`
  - deterministic
  - streams subset reviews and tips
  - groups raw UGC by selected POI
  - caches per-POI comment bundles

The system is already good enough for:
- semantic retrieval
- budget-sensitive ranking
- premium vs budget preference handling
- anchor-aware local filtering
- raw UGC loading for selected POIs

The main missing retrieval capability is:
- time / opening-hours awareness

The main missing UGC capability is:
- comment summarization into compact signals
