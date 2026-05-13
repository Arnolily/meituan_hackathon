## Architecture

## Current V1 Plan

The current dataset-backed `v1` should focus on building a strong POI understanding pipeline before real map routing.

Reason:
- the Yelp dump already gives us `POI + UGC + user profile proxy + check-in history`
- the missing piece is road/transit map data
- therefore `v1` should optimize data integration, summarization, and filtering first

Current `v1` scope:
1. build a clean one-city subset from Yelp
2. parse user intent into structured constraints
3. retrieve candidate POIs
4. load and summarize UGC
5. aggregate POI, UGC, and check-in signals into one POI card
6. filter POIs by hard constraints

This means the first six modules are a valid `v1`, but they should be treated as a `data-centric planning foundation`, not yet a full route planner.

## Dataset Notes

The Yelp dataset currently gives us:
- `business.json` -> POI backbone
- `review.json` -> long-form UGC
- `tip.json` -> short actionable UGC
- `user.json` -> user profile proxy
- `checkin.json` -> temporal popularity signal

Important note on `checkin.json`:
- it is not map geometry
- it does not give travel paths
- it is useful for features such as `night_active`, `weekend_busy`, `peak_hour`, `high_traffic`

Therefore, `checkin.json` should be merged into the POI feature layer in `v1`.

## Preprocessing Step

Before the runtime pipeline, add one offline dataset-prep step:

### 0. City Subset Builder
Build a dense one-city subset from Yelp for experimentation.

Why:
- the full Yelp dump is too broad
- route planning should first be tested in one city
- dense cities make the planning problem more meaningful

Current recommendation:
- prefer `Philadelphia, PA` as the first city
- `New Orleans, LA` is also a strong candidate

Output:
- one filtered city-level dataset
- joined by `business_id` and `user_id`
- ready for runtime modules

### 1. Intent Parser
Convert the user's natural language into structured intent.

Example input:
- 想要去海河玩，预算有限，想看风景加上吃晚饭，在晚上八点之前回到xx酒店

Example output:
```json
{
  "target_area": "海河",
  "goals": ["观景", "晚饭"],
  "budget_level": "limited",
  "return_location": "xx酒店",
  "return_deadline": "20:00"
}
```

Hard constraints:
- target area = 海河
- must include dinner
- must return to xx酒店 before 20:00

Soft constraints:
- low cost
- good scenery

### 2. POI Loader
Filter candidate POIs from the POI database using the parsed intent.

Each POI should be normalized into structured fields.

Example:
```json
{
  "name": "天津之眼",
  "type": "观光",
  "price_rmb": 70,
  "opening_hours": "10:00-22:00",
  "position": "lat/lng",
  "average_duration_h": 0.5
}
```

Notes:
- `price_rmb` is the primary price field
- optional derived field: `price_level = cheap | medium | expensive`

### 3. Comment Loader
Load raw user comments for each candidate POI.

Example:
```json
{
  "poi": "天津之眼",
  "comments": [
    "人太多",
    "晴天风景好",
    "卫生很差"
  ]
}
```

### 4. Comment Summarizer
Convert raw comments into concise tags or signals for downstream planning.

Example:
```json
{
  "poi": "天津之眼",
  "tags": ["crowded", "good_view_sunny", "poor_hygiene"]
}
```

### 5. POI Feature Aggregator
Merge POI structured data, summarized comment signals, and check-in signals into one POI card.

Example:
```json
{
  "name": "天津之眼",
  "type": "观光",
  "price_rmb": 70,
  "opening_hours": "10:00-22:00",
  "position": "lat/lng",
  "average_duration_h": 0.5,
  "tags": ["crowded", "good_view_sunny", "poor_hygiene"],
  "checkin_features": {
    "checkin_count": 1200,
    "night_active": true,
    "weekend_busy": true
  }
}
```

Notes:
- this is the main unified POI card for downstream filtering and later routing
- `checkin.json` should be converted into compact temporal features here
- `tip.json` can be treated as a lightweight comment source and merged with review signals

### 6. Hard Constraint Filter
Remove POIs that violate hard constraints.

Examples:
- outside the target area
- closed during the requested time
- impossible to fit into the schedule

Note:
- hard constraints should filter directly
- soft constraints should mostly affect scoring, not direct removal

In `v1`, this is the last online module before true route generation is introduced later.

### 7. Travel Time / Feasibility Estimator
Estimate travel time, total duration, and return feasibility.

Main checks:
- hotel -> POI travel time
- POI -> restaurant travel time
- restaurant -> hotel travel time
- whether the route can return before 20:00

This module is necessary for real route planning.

Status:
- postpone to `v2` if no map or routing graph is available
- a weak fallback is straight-line or heuristic travel time, but that should be labeled as approximate

### 8. Route Generator
Generate multiple feasible route candidates from the remaining POIs.

Example routes:
- 酒店 -> 海河观景点 -> 晚饭 -> 酒店
- 酒店 -> 天津之眼 -> 晚饭 -> 酒店

### 9. Route Scorer
Score each route using weighted factors.

Possible factors:
- scenery quality
- budget fit
- travel efficiency
- return-time safety margin
- comment-based quality signals

### 10. Route Explainer and Replanner
Explain why a route is recommended and revise it after user feedback.

Examples:
- why this route is cheap
- why this route has better scenery
- regenerate a route with less walking
- regenerate a route with better dinner options

## Pipeline

Offline dataset prep
-> City Subset Builder

User Query
-> Intent Parser
-> POI Loader
-> Comment Loader
-> Comment Summarizer
-> POI Feature Aggregator
-> Hard Constraint Filter
-> Travel Time / Feasibility Estimator
-> Route Generator
-> Route Scorer
-> Route Explainer and Replanner

## V1 / V2 Boundary

### V1
- City Subset Builder
- Intent Parser
- POI Loader
- Comment Loader
- Comment Summarizer
- POI Feature Aggregator
- Hard Constraint Filter

Goal:
- produce high-quality candidate POI cards for one city
- support retrieval, summarization, and constraint-aware filtering

### V2
- Travel Time / Feasibility Estimator
- Route Generator
- Route Scorer
- Route Explainer and Replanner

Goal:
- produce real multi-stop itineraries
- reason over time, order, return feasibility, and tradeoffs

## Design Notes

- Keep each module narrow and testable.
- Use deterministic logic for filtering, travel-time estimation, and scoring.
- Use the LLM mainly for intent parsing, comment summarization, explanation, and replanning dialogue.
- Do not merge retrieval, summarization, and route planning into one LLM step.
- For the Yelp-based prototype, use one dense city first instead of the full dump.
- Treat `checkin.json` as a popularity and temporal-demand signal, not as map data.
