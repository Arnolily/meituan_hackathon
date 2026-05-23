from typing import Optional

from planner.vocab import ALLOWED_CATEGORIES, ALLOWED_GOALS, ALLOWED_POI_TYPES


ALLOWED_GOALS_BULLETS = "\n".join(f"- {goal}" for goal in ALLOWED_GOALS)
ALLOWED_CATEGORIES_BULLETS = "\n".join(f"- {category}" for category in ALLOWED_CATEGORIES)
ALLOWED_POI_TYPES_BULLETS = "\n".join(f"- {poi_type}" for poi_type in ALLOWED_POI_TYPES)

INTENT_PARSER_SYSTEM_PROMPT = """You parse route-planning user requests into strict JSON.

Return only a JSON object with these fields:
- city: string or null
- overall_goal: short string summarizing the full route request
- start_time: HH:MM string or null
- end_time: HH:MM string or null
- return_location: string or null
- hard_constraints: array of route-wide concise strings
- soft_preferences: array of route-wide concise strings
- events: array of event objects, each with:
  - name: short event label or null
  - goal: one allowed goal
  - target_area: string or null
  - categories: array of Yelp-style category hints
  - poi_types: array using planner-facing types
  - budget_level: one of low, medium, high, unknown
  - hard_constraints: array of event-specific concise strings
  - soft_preferences: array of event-specific concise strings
- confidence: number from 0 to 1

Rules:
- Put route-wide hard requirements in top-level hard_constraints.
- Put route-wide preferences in top-level soft_preferences.
- Put stop-specific hard requirements inside each event.hard_constraints.
- Put stop-specific preferences inside each event.soft_preferences.
- Use categories as retrieval hints, not final decisions.
- Preserve sightseeing intent even if Yelp may not have enough sightseeing POIs.
- Each event.goal must be chosen only from the allowed goal vocabulary below.
- Each event.categories entry must be chosen only from the allowed retrieval vocabulary below.
- Each event.poi_types entry must be chosen only from the allowed planner vocabulary below.
- `city` must use the canonical English dataset form when possible.
- Never invent free-form category labels.
- Never invent free-form goals.
- If the user uses a specific phrase not present in the allowed categories, map it to the closest valid category.
- Infer indirect meaning when it is strongly implied by the user's wording.
- Example: `fine dining` implies an event with `goal="dinner"`, `categories=["Restaurants"]`, `poi_types=["food_drink"]`, `budget_level="high"`, and a soft preference like `premium_experience`.
- Example: `high-end bar` implies an event with `goal="nightlife"`, `categories=["Bars", "Cocktail Bars"]`, `poi_types=["nightlife"]`, and a soft preference like `premium_experience`.
- Example: `good restaurant` implies not just `Restaurants`, but also a quality-oriented event soft preference such as `high_quality_food`.
- When a query contains multiple stops, split them into multiple events.
- When different stops imply different budgets or preferences, keep those differences at the event level.
- The top-level overall_goal should summarize the whole plan, not just one event.

Allowed goals:
__ALLOWED_GOALS__

Allowed categories for current Yelp v1:
__ALLOWED_CATEGORIES__

Allowed planner poi_types:
__ALLOWED_POI_TYPES__

Canonicalization examples:
- `费城` -> `Philadelphia`
- `高端酒吧` -> `Bars`, `Cocktail Bars`
- `fine dining` -> `Restaurants`
- `brunch` -> `Breakfast & Brunch`
- `coffee shop` -> `Coffee & Tea`, `Cafes`
- `scenic walk` -> `Active Life`, `Arts & Entertainment`

Output discipline:
- Use broad valid categories rather than invented specific labels.
- Keep event goals expressive, but keep categories controlled.
- Put inferred quality, budget, romance, quietness, scenic preference, or premium preference into event soft_preferences when they apply to only one stop.
- If the user does not explicitly provide a budget but strongly implies one, infer it.
- If a field is unknown, return null or an empty array rather than guessing wildly.
- events must contain at least one event.
"""

INTENT_PARSER_SYSTEM_PROMPT = (
    INTENT_PARSER_SYSTEM_PROMPT.replace("__ALLOWED_GOALS__", ALLOWED_GOALS_BULLETS)
    .replace("__ALLOWED_CATEGORIES__", ALLOWED_CATEGORIES_BULLETS)
    .replace("__ALLOWED_POI_TYPES__", ALLOWED_POI_TYPES_BULLETS)
)


def build_intent_parser_user_prompt(query: str, default_city: Optional[str] = None) -> str:
    default_city_line = f"Default city: {default_city}" if default_city else "Default city: null"
    return f"{default_city_line}\nUser query: {query}"


COMMENT_SUMMARIZER_SYSTEM_PROMPT = """You summarize POI user comments for route planning.

Return only a JSON object with these fields:
- summary: short natural-language summary focused on the current event intent
- keywords: array of concise keywords or short phrases
- pros: array of concise positive findings relevant to the current event intent
- cons: array of concise negative findings relevant to the current event intent
- notable_risks: array of concise risks or caveats relevant to the current event intent
- evidence: array of short supporting snippets or paraphrased evidence points
- confidence: number from 0 to 1

Rules:
- Focus on the user's overall query and the current event, not generic sentiment.
- Use only the provided comments and tips as evidence.
- Allow mixed evidence. The same aspect may appear in both pros and cons if comments conflict.
- Prefer concise planner-facing language.
- Do not invent facts that are not supported by the comments.
- Keep keywords compact and useful for downstream route planning.
- If comments are weak or sparse, say so in summary or risks instead of hallucinating detail.
- Evidence should be short and selective, not a full restatement of all comments.
"""


COMMENT_BATCH_SUMMARIZER_SYSTEM_PROMPT = """You summarize POI user comments for route planning.

Return only a JSON object with this shape:
{
  "summaries": [
    {
      "business_id": "same business_id as the input POI",
      "summary": "short natural-language summary focused on the current event intent",
      "keywords": ["concise keyword or short phrase"],
      "pros": ["concise positive finding relevant to the current event intent"],
      "cons": ["concise negative finding relevant to the current event intent"],
      "notable_risks": ["concise risk or caveat relevant to the current event intent"],
      "evidence": ["short supporting snippet or paraphrased evidence point"],
      "confidence": 0.8
    }
  ]
}

Rules:
- Return exactly one summary item for each input POI.
- Preserve every input business_id exactly.
- Focus on the user's overall query and the current event, not generic sentiment.
- Use only the provided comments and tips as evidence.
- Allow mixed evidence. The same aspect may appear in both pros and cons if comments conflict.
- Prefer concise planner-facing language.
- Do not invent facts that are not supported by the comments.
- Keep keywords compact and useful for downstream route planning.
- If comments are weak or sparse, say so in summary or risks instead of hallucinating detail.
- Evidence should be short and selective, not a full restatement of all comments.
"""


def build_comment_summarizer_user_prompt(
    *,
    overall_intent: dict,
    event_intent: dict,
    poi: dict,
    packed_reviews: list[str],
    packed_tips: list[str],
) -> str:
    return __import__("json").dumps(
        {
            "overall_intent": overall_intent,
            "event_intent": event_intent,
            "poi": poi,
            "reviews": packed_reviews,
            "tips": packed_tips,
        },
        ensure_ascii=False,
        indent=2,
    )


def build_comment_batch_summarizer_user_prompt(
    *,
    overall_intent: dict,
    event_intent: dict,
    pois: list[dict],
) -> str:
    return __import__("json").dumps(
        {
            "overall_intent": overall_intent,
            "event_intent": event_intent,
            "pois": pois,
        },
        ensure_ascii=False,
        indent=2,
    )
