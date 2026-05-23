# Current Technical Report

## Pipeline

Implemented runtime flow:

1. `Intent Parser`: LLM parses user query into structured `Intent`.
2. `POI Loader`: deterministic retrieval from Yelp business subset.
3. `Comment Loader`: deterministic review/tip loading for selected POIs.
4. `Comment Summarizer`: LLM summarizes POI UGC into compact signals.
5. `POI Aggregator`: deterministic merge of POI data + comment summary.
6. `Streamlit UI`: runs each step and caches latest artifacts.

Latest cache files:
- `cache/intents/latest_intent.json`
- `cache/pois/latest_pois.json`
- `cache/comments/latest_comments.json`
- `cache/comment_summaries/latest_comment_summaries.json`
- `cache/aggregated_pois/latest_aggregated_pois.json`

## Main Data Objects

`Intent`
- event-based query structure
- fields include `city`, `overall_goal`, `start_time`, `end_time`, `return_location`, constraints, preferences, and `events`
- each event has `goal`, `target_area`, `categories`, `poi_types`, `budget_level`, constraints, and preferences

`RawPOI`
- normalized Yelp business record
- includes location, category, rating, review count, price, hours, attributes, spatial annotations, and retrieval scoring trace

`POICommentSummary`
- LLM-generated summary of reviews/tips
- includes `summary`, `keywords`, `pros`, `cons`, `notable_risks`, `evidence`, and `confidence`

`AggregatedPOI`
- final POI card for downstream planning
- merges `RawPOI` with matched `POICommentSummary`
- adds `comment_summary_available`, comment signal fields, `aggregate_score`, and `aggregate_breakdown`

## POI Retrieval Score

`retrieval_score` is deterministic and produced by `poi_loader.py`.

Hard gates:
- city mismatch -> reject
- if event categories exist and none match -> reject
- non-positive scores are not rejected after these gates

Score criteria:
- category match: `+10 + 2 * category_hits`
- `poi_type` match: `+2` per matching type
- goal-category hint match: `+1.5`
- target area in POI name/address: `+3`
- budget fit:
  - low budget: tier 1 `+100`, tier 2 `-30`, tier 3/4 `-100`
  - medium budget: tier 2 `+100`, tier 1/3 `+20`, tier 4 `-60`
  - high budget: tier 3/4 `+100`, tier 2 `-30`, tier 1 `-80`
  - known budget + unknown POI price: `-20`
- soft preferences:
  - `premium_experience`: premium price `+3`, premium ambience `+1.5`, reservations `+0.75`
  - `high_quality_food`: restaurant category `+1`, stars >= 4.3 `+1.5`
  - `high_end_atmosphere`: upscale ambience `+1.5`, bar/cocktail category `+0.75`
  - `budget_sensitive`: cheap `+2`, expensive `-2`
  - `good_view`: outdoor seating `+0.5`
- hard-constraint heuristics:
  - `must_include_dinner` + restaurant: `+2`
  - minor/non-alcoholic hints: kid-friendly `+1`, cafe/coffee category `+1`
- quality prior: `stars * 0.4 + min(review_count, 1000) / 1000`

Distance is not a retrieval-score reward. It is used only for optional spatial filtering and final sorting.

Final POI sort:
1. higher `retrieval_score`
2. distance known before unknown
3. smaller anchor distance
4. higher `review_count`
5. higher `stars`
6. name

## Aggregated Score

`aggregate_score` is deterministic and produced by `poi_aggregator.py`.

It does not call an LLM. It only combines existing POI retrieval data and comment-summary signals.

Formula:

```text
aggregate_score =
  retrieval_score
  + quality_signal
  + summary_component
```

Components:
- `retrieval_score`: original POI loader score
- `quality_signal`: `min(max(stars, 0), 5) * 0.25 + min(max(review_count, 0), 1000) / 1000`
- if summary exists:
  - `comment_confidence`: summary confidence, `0.0` to `1.0`
  - `positive_comment_signal`: `min(len(pros), 4) * 0.25 + min(len(keywords), 6) * 0.05`
  - `negative_comment_signal`: `min(len(cons), 4) * -0.2 + min(len(risks), 4) * -0.35`
  - `summary_component`: sum of the three fields above
- if summary is missing:
  - `summary_component`: `missing_comment_summary_penalty = -0.5`

Final aggregated POI sort:
1. higher `aggregate_score`
2. higher `retrieval_score`
3. higher `review_count`
4. name

## Current Limits

Not implemented yet:
- opening-hours validation against `start_time` / `end_time`
- hard constraint filtering as a separate module
- route sequencing
- map API travel time
- return-location feasibility
- route-level scoring and explanation
