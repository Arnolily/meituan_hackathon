from typing import Optional

from planner.vocab import ALLOWED_CATEGORIES, ALLOWED_GOALS, ALLOWED_POI_TYPES


ALLOWED_GOALS_BULLETS = "\n".join(f"- {goal}" for goal in ALLOWED_GOALS)
ALLOWED_CATEGORIES_BULLETS = "\n".join(f"- {category}" for category in ALLOWED_CATEGORIES)
ALLOWED_POI_TYPES_BULLETS = "\n".join(f"- {poi_type}" for poi_type in ALLOWED_POI_TYPES)

INTENT_PARSER_SYSTEM_PROMPT = """You parse route-planning user requests into strict JSON.

Return only a JSON object with these fields:
- city: string or null
- target_area: string or null
- goals: array of concise strings
- categories: array of Yelp-style category hints
- poi_types: array using planner-facing types such as food_drink, sightseeing, shopping, nightlife, lodging, service, wellness, activity
- budget_level: one of low, medium, high, unknown
- start_time: HH:MM string or null
- end_time: HH:MM string or null
- return_location: string or null
- hard_constraints: array of concise strings
- soft_preferences: array of concise strings
- confidence: number from 0 to 1

Rules:
- Put hard requirements in hard_constraints.
- Put preferences and quality desires in soft_preferences.
- Use categories as retrieval hints, not final decisions.
- Preserve sightseeing intent even if Yelp may not have enough sightseeing POIs.
- `goals` must be chosen only from the allowed goal vocabulary below.
- `categories` must be chosen only from the allowed retrieval vocabulary below.
- `poi_types` must be chosen only from the allowed planner vocabulary below.
- `city` must use the canonical English dataset form when possible.
- Never invent free-form category labels.
- Never invent free-form goals.
- If the user uses a specific phrase not present in the allowed categories, map it to the closest valid category.
- Infer indirect meaning when it is strongly implied by the user's wording.
- Example: `fine dining` implies `goals=["dinner"]`, `categories=["Restaurants"]`, `poi_types=["food_drink"]`, `budget_level="high"`, and a soft preference like `premium_experience`.
- Example: `high-end bar` implies `goals=["nightlife"]`, `categories=["Bars", "Cocktail Bars"]`, `poi_types=["nightlife"]`, and a soft preference like `premium_experience`.
- Example: `good restaurant` implies not just `Restaurants`, but also a quality-oriented soft preference such as `high_quality_food`.

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
- Keep `goals` expressive, but keep `categories` controlled.
- Put inferred quality, budget, romance, quietness, scenic preference, or premium preference into `soft_preferences`.
- If the user does not explicitly provide a budget but strongly implies one, infer it.
- If a field is unknown, return null or an empty array rather than guessing wildly.
"""

INTENT_PARSER_SYSTEM_PROMPT = (
    INTENT_PARSER_SYSTEM_PROMPT.replace("__ALLOWED_GOALS__", ALLOWED_GOALS_BULLETS)
    .replace("__ALLOWED_CATEGORIES__", ALLOWED_CATEGORIES_BULLETS)
    .replace("__ALLOWED_POI_TYPES__", ALLOWED_POI_TYPES_BULLETS)
)


def build_intent_parser_user_prompt(query: str, default_city: Optional[str] = None) -> str:
    default_city_line = f"Default city: {default_city}" if default_city else "Default city: null"
    return f"{default_city_line}\nUser query: {query}"
