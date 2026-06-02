from __future__ import annotations

import argparse
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from planner.config import DEFAULT_CACHE_DIR, DEFAULT_INTERIM_DIR, PROJECT_ROOT, load_env_file
from planner.io.comment_cache import load_cached_comments, save_cached_comments
from planner.io.comment_summary_cache import save_cached_comment_summaries
from planner.io.intent_cache import save_cached_intent
from planner.io.poi_cache import save_cached_pois
from planner.io.poi_aggregation_cache import save_cached_aggregated_pois
from planner.io.route_cache import save_cached_routes
from planner.llm.client import OpenAICompatibleClient
from planner.modules.comment_loader import load_event_comment_groups
from planner.modules.comment_summarizer import summarize_event_comment_groups
from planner.modules.intent_parser import parse_intent
from planner.modules.intent_clarifier import (
    DO_NOT_CARE,
    apply_clarification_answers,
    build_clarification_plan,
    build_poi_refinement_plan,
)
from planner.modules.ors_client import OpenRouteServiceDirectionClient
from planner.modules.poi_aggregator import aggregate_event_poi_groups
from planner.modules.poi_loader import load_candidate_poi_groups
from planner.modules.route_finder import find_route_candidates
from planner.schemas import (
    AnchorPoint,
    EventCommentGroup,
    EventCommentSummaryGroup,
    EventIntent,
    Intent,
    POICommentSummary,
    RouteLeg,
    RouteStop,
    RouteTravelMode,
    SpatialConstraint,
)
from planner.utils.geo import haversine_distance_km
from scripts.load_pois import resolve_business_file


PHILADELPHIA_ANCHOR = AnchorPoint(name="Philadelphia, PA, USA", latitude=39.953764, longitude=-75.1555)
MODE_SPEED_KPH: dict[RouteTravelMode, float] = {"walking": 4.8, "cycling": 15.0, "driving": 28.0}
FRONTEND_POI_TYPES = ("餐饮", "娱乐", "商场", "公园", "文化")
BROAD_CATEGORY_HINTS = {"Restaurants", "Food", "Museums", "Arts & Entertainment"}


class ClarificationNeeded(Exception):
    def __init__(self, *, intent: Intent, questions: list[dict[str, Any]]) -> None:
        self.intent = intent
        self.questions = questions
        super().__init__("Clarification required")


class ApproximateDirectionClient:
    def route(self, *, stops: list[RouteStop], mode: RouteTravelMode) -> list[RouteLeg]:
        speed_kph = MODE_SPEED_KPH.get(mode, MODE_SPEED_KPH["walking"])
        legs: list[RouteLeg] = []
        for origin, destination in zip(stops, stops[1:]):
            distance_meters = haversine_distance_km(origin, destination) * 1220.0
            duration_seconds = (distance_meters / 1000.0) / speed_kph * 3600.0
            legs.append(
                RouteLeg(
                    origin_name=origin.name,
                    destination_name=destination.name,
                    mode=mode,
                    distance_meters=round(distance_meters, 2),
                    duration_seconds=round(duration_seconds, 2),
                    polyline=[[origin.latitude, origin.longitude], [destination.latitude, destination.longitude]],
                    provider="approximate",
                    provider_status="ok",
                    provider_info="Estimated from straight-line distance.",
                    raw_path_count=1,
                )
            )
        return legs


def _env_value(env_settings: dict[str, str], key: str) -> str | None:
    return os.environ.get(key) or env_settings.get(key)


def _parse_env_file(path: Any) -> dict[str, str]:
    if not path.exists():
        return {}
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip().strip('"').strip("'")
    return parsed


def _load_api_env() -> dict[str, str]:
    settings = load_env_file()
    for env_file in (PROJECT_ROOT / "meituan_map" / ".env.local", PROJECT_ROOT / "meituan_map" / ".env"):
        for key, value in _parse_env_file(env_file).items():
            settings.setdefault(key, value)
    return settings


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _budget_level(value: str | None) -> str:
    if value in {"low", "medium", "high"}:
        return value
    return "medium"


def _frontend_types(payload: dict[str, Any]) -> list[str]:
    travel_intent = payload.get("travelIntent") or {}
    poi_types = travel_intent.get("poiTypes")
    if isinstance(poi_types, list):
        selected = [item for item in poi_types if item in FRONTEND_POI_TYPES]
        if selected:
            return selected
    return ["餐饮", "公园", "文化"]


def _fallback_intent(query: str, payload: dict[str, Any]) -> Intent:
    travel_intent = payload.get("travelIntent") or {}
    text = query.lower()
    selected_types = _frontend_types(payload)
    events: list[EventIntent] = []

    def add_event(name: str, goal: str, categories: list[str], poi_types: list[str]) -> None:
        events.append(
            EventIntent(
                name=name,
                goal=goal,
                categories=categories,
                poi_types=poi_types,
                budget_level="unknown",
                soft_preferences=list(travel_intent.get("preferences") or []),
            )
        )

    if "餐饮" in selected_types or any(token in text for token in ["eat", "food", "lunch", "dinner", "coffee", "吃", "饭", "咖啡"]):
        if "coffee" in text or "咖啡" in text:
            add_event("Coffee", "coffee", ["Coffee & Tea"], ["food_drink"])
        elif "dinner" in text or "晚饭" in text or "晚餐" in text:
            add_event("Dinner", "dinner", ["Restaurants"], ["food_drink"])
        else:
            add_event("Meal", "lunch", ["Restaurants", "Food"], ["food_drink"])
    if "公园" in selected_types or any(token in text for token in ["park", "公园"]):
        add_event("Park", "park", ["Parks"], ["park_outdoor"])
    if "文化" in selected_types or any(token in text for token in ["museum", "culture", "art", "博物馆", "文化", "艺术"]):
        if "art" in text or "艺术" in text:
            add_event("Art", "art_gallery", ["Art Galleries", "Art Museums"], ["culture"])
        else:
            add_event("Museum", "museum", ["Museums", "Art Museums"], ["museum"])
    if "商场" in selected_types or any(token in text for token in ["shop", "mall", "shopping", "购物", "商场"]):
        add_event("Shopping", "shopping", ["Shopping Centers"], ["shopping"])
    if "娱乐" in selected_types or any(token in text for token in ["game", "fun", "entertainment", "玩", "娱乐"]):
        add_event("Activity", "games", ["Arts & Entertainment", "Arcades"], ["entertainment"])
    if not events:
        add_event("Meal", "lunch", ["Restaurants", "Food"], ["food_drink"])
        add_event("Museum", "museum", ["Museums", "Art Museums"], ["museum"])

    return Intent(
        raw_query=query,
        city="Philadelphia",
        overall_goal=query or "Philadelphia route planning",
        events=events[:4],
        confidence=0.5,
    )


def _intent_from_payload(payload: dict[str, Any], query: str, env_settings: dict[str, str]) -> Intent:
    raw_intent = payload.get("backendIntent")
    if isinstance(raw_intent, dict):
        return Intent.model_validate(raw_intent)
    return _apply_direct_intent_overrides(query, _parse_or_fallback_intent(query, payload, env_settings))


def _question_payloads(plan: Any) -> list[dict[str, Any]]:
    return [question.model_dump() for question in plan.questions]


def _answered(question_ids: set[str], answers: dict[str, str]) -> set[str]:
    return {question_id for question_id in question_ids if answers.get(question_id)}


def _extra_category_refinement_questions(
    intent: Intent,
    poi_groups: list[Any],
    *,
    skip_event_indices: set[int] | None = None,
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    skipped = skip_event_indices or set()
    event_by_index = {index: event for index, event in enumerate(intent.events, start=1)}
    for group in poi_groups:
        if group.event_index in skipped:
            continue
        event = event_by_index.get(group.event_index)
        if event is None:
            continue
        if event.categories and not any(category in BROAD_CATEGORY_HINTS for category in event.categories):
            continue
        available: list[str] = []
        for poi in group.pois:
            for category in poi.categories:
                if category in BROAD_CATEGORY_HINTS or category in available:
                    continue
                available.append(category)
        if len(available) < 2:
            continue
        event_label = event.name or event.goal or f"event {group.event_index}"
        questions.append(
            {
                "id": f"event_{group.event_index}_category_refinement",
                "event_index": group.event_index,
                "field": "cuisine_category",
                "question": f"What kind of POI for {event_label}?",
                "options": available[:8] + [DO_NOT_CARE],
            }
        )
    return questions


def _apply_extra_category_answers(intent: Intent, questions: list[dict[str, Any]], answers: dict[str, str]) -> Intent:
    if not questions:
        return intent
    events = [event.model_dump() for event in intent.events]
    question_by_id = {question["id"]: question for question in questions}
    for question_id, answer in answers.items():
        question = question_by_id.get(question_id)
        if question is None or answer == DO_NOT_CARE or answer not in question["options"]:
            continue
        event_payload = events[question["event_index"] - 1]
        categories = [category for category in event_payload.get("categories", []) if category not in BROAD_CATEGORY_HINTS]
        if answer not in categories:
            categories.append(answer)
        event_payload["categories"] = categories
    return Intent.model_validate({**intent.model_dump(), "events": events})


def _raise_if_clarification_needed(
    *,
    intent: Intent,
    questions: list[dict[str, Any]],
    answers: dict[str, str],
) -> None:
    pending = [question for question in questions if not answers.get(question["id"])]
    if pending:
        raise ClarificationNeeded(intent=intent, questions=pending)


def _budget_override_from_text(query: str) -> str | None:
    patterns = [
        ("low", r"低预算|预算.{0,12}(低|少|便宜|省钱)|(?:低|少|便宜|省钱).{0,8}预算|改成低|change to low|low budget"),
        ("medium", r"中等预算|预算.{0,12}(中|适中|普通)|(?:中等|适中|普通).{0,8}预算|改成中|change to medium|medium budget"),
        ("high", r"高预算|预算.{0,12}(高|贵|品质)|(?:高|贵|品质).{0,8}预算|改成高|change to high|high budget"),
    ]
    matches: list[tuple[int, str]] = []
    for budget, pattern in patterns:
        for match in re.finditer(pattern, query, flags=re.IGNORECASE):
            matches.append((match.start(), budget))
    if not matches:
        return None
    return max(matches, key=lambda item: item[0])[1]


def _apply_direct_intent_overrides(query: str, intent: Intent) -> Intent:
    budget = _budget_override_from_text(query)
    if not budget:
        return intent
    events = [event.model_copy(update={"budget_level": budget}) for event in intent.events]
    return intent.model_copy(update={"events": events})


def _llm_config(payload: dict[str, Any], env_settings: dict[str, str]) -> tuple[str | None, str | None, str | None]:
    model_choice = payload.get("modelChoice")
    return _llm_config_for_choice(model_choice, env_settings)


def _comment_llm_config(payload: dict[str, Any], env_settings: dict[str, str]) -> tuple[str | None, str | None, str | None]:
    model_choice = payload.get("commentModelChoice") or payload.get("modelChoice")
    return _llm_config_for_choice(model_choice, env_settings)


def _llm_config_for_choice(model_choice: Any, env_settings: dict[str, str]) -> tuple[str | None, str | None, str | None]:
    if model_choice == "deepseek":
        api_key = _env_value(env_settings, "DEEPSEEK_API_KEY") or _env_value(env_settings, "VITE_DEEPSEEK_API_KEY")
        base_url = _env_value(env_settings, "DEEPSEEK_BASE_URL") or _env_value(env_settings, "VITE_DEEPSEEK_BASE_URL")
        model = _env_value(env_settings, "DEEPSEEK_MODEL") or _env_value(env_settings, "VITE_DEEPSEEK_MODEL")
    elif model_choice == "mimo":
        api_key = _env_value(env_settings, "MIMO_API_KEY") or _env_value(env_settings, "VITE_MIMO_API_KEY")
        base_url = _env_value(env_settings, "MIMO_BASE_URL") or _env_value(env_settings, "VITE_MIMO_BASE_URL")
        model = _env_value(env_settings, "MIMO_MODEL") or _env_value(env_settings, "VITE_MIMO_MODEL")
    else:
        api_key = (
            _env_value(env_settings, "OPENAI_API_KEY")
            or _env_value(env_settings, "DEEPSEEK_API_KEY")
            or _env_value(env_settings, "VITE_DEEPSEEK_API_KEY")
            or _env_value(env_settings, "MIMO_API_KEY")
            or _env_value(env_settings, "VITE_MIMO_API_KEY")
        )
        base_url = (
            _env_value(env_settings, "OPENAI_BASE_URL")
            or _env_value(env_settings, "DEEPSEEK_BASE_URL")
            or _env_value(env_settings, "VITE_DEEPSEEK_BASE_URL")
            or _env_value(env_settings, "MIMO_BASE_URL")
            or _env_value(env_settings, "VITE_MIMO_BASE_URL")
        )
        model = (
            _env_value(env_settings, "OPENAI_MODEL")
            or _env_value(env_settings, "DEEPSEEK_MODEL")
            or _env_value(env_settings, "VITE_DEEPSEEK_MODEL")
            or _env_value(env_settings, "MIMO_MODEL")
            or _env_value(env_settings, "VITE_MIMO_MODEL")
        )
    return api_key, base_url, model


def _parse_or_fallback_intent(query: str, payload: dict[str, Any], env_settings: dict[str, str]) -> Intent:
    api_key, base_url, model = _llm_config(payload, env_settings)
    if api_key and model:
        try:
            client = OpenAICompatibleClient(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout=float(_env_value(env_settings, "OPENAI_TIMEOUT_SEC") or "60"),
            )
            return parse_intent(query, default_city="Philadelphia", llm_client=client)
        except Exception:
            pass
    return _fallback_intent(query, payload)


def _anchor_from_payload(payload: dict[str, Any]) -> AnchorPoint:
    anchor = payload.get("anchor") or {}
    latitude = anchor.get("lat") or anchor.get("latitude")
    longitude = anchor.get("lng") or anchor.get("longitude")
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return AnchorPoint(name=anchor.get("name") or "Current Location", latitude=float(latitude), longitude=float(longitude))

    travel_intent = payload.get("travelIntent") or {}
    return PHILADELPHIA_ANCHOR.model_copy(update={"name": travel_intent.get("manualStartName") or PHILADELPHIA_ANCHOR.name})


def _direction_client(env_settings: dict[str, str]):
    ors_key = _env_value(env_settings, "OPENROUTESERVICE_API_KEY") or _env_value(env_settings, "ORS_API_KEY")
    if ors_key:
        return OpenRouteServiceDirectionClient(api_key=ors_key, timeout=float(_env_value(env_settings, "ORS_TIMEOUT_SEC") or "20"))
    return ApproximateDirectionClient()


def _poi_type(categories: list[str], event_goal: str | None) -> str:
    joined = " ".join(categories).lower()
    goal = (event_goal or "").lower()
    if any(token in joined for token in ["restaurant", "food", "coffee", "bar", "bakery", "cafe"]) or goal in {"lunch", "dinner", "coffee"}:
        return "餐饮"
    if any(token in joined for token in ["park", "active life"]) or goal == "park":
        return "公园"
    if any(token in joined for token in ["museum", "gallery", "arts", "historical"]) or goal in {"museum", "art_gallery", "historical_site"}:
        return "文化"
    if any(token in joined for token in ["shopping", "mall", "store"]) or goal == "shopping":
        return "商场"
    return "娱乐"


def _poi_category(poi_type: str) -> str:
    return {"餐饮": "food", "公园": "life", "文化": "study", "商场": "mall", "娱乐": "entertainment"}.get(poi_type, "life")


def _natural_goal(value: str | None) -> str:
    labels = {
        "breakfast": "早餐",
        "coffee": "咖啡",
        "lunch": "午餐",
        "dinner": "晚餐",
        "dessert": "甜品",
        "drinks": "饮品",
        "nightlife": "夜生活",
        "shopping": "购物",
        "sightseeing": "观光",
        "museum": "博物馆",
        "park": "公园",
        "historical_site": "历史地点",
        "art_gallery": "艺术空间",
        "performance": "演出",
        "tour": "游览",
        "family_activity": "亲子活动",
        "games": "娱乐活动",
    }
    return labels.get(value or "", (value or "这一段行程").replace("_", " "))


def _natural_category(value: str) -> str:
    labels = {
        "Chinese": "中餐",
        "Japanese": "日料",
        "Italian": "意餐",
        "Mexican": "墨西哥菜",
        "American (New)": "新式美餐",
        "American (Traditional)": "传统美餐",
        "Seafood": "海鲜",
        "Thai": "泰餐",
        "Indian": "印度菜",
        "Korean": "韩餐",
        "Vietnamese": "越南菜",
        "Restaurants": "餐厅",
        "Food": "餐饮",
        "Breakfast & Brunch": "早午餐",
        "Coffee & Tea": "咖啡或茶饮",
        "Cafes": "咖啡馆",
        "Museums": "博物馆",
        "Art Museums": "艺术博物馆",
        "Art Galleries": "画廊或艺术空间",
        "Parks": "公园",
        "Shopping Centers": "购物中心",
        "Arts & Entertainment": "文化娱乐空间",
        "Active Life": "户外活动",
        "Arcades": "游戏厅",
        "Bars": "酒吧",
        "Beer Gardens": "啤酒花园",
        "Beer Bar": "啤酒吧",
        "Cocktail Bars": "鸡尾酒吧",
        "Vegetarian": "素食",
        "Vegan": "纯素",
        "Tacos": "塔可",
        "Bakeries": "烘焙店",
        "Desserts": "甜品",
        "Juice Bars & Smoothies": "果汁和冰沙",
        "Ice Cream & Frozen Yogurt": "冰淇淋和冻酸奶",
    }
    return labels.get(value, value.replace(" & ", "和").replace("_", " "))


def _event_display_name(event_name: str | None, event_goal: str | None) -> str:
    if not event_name:
        return _natural_goal(event_goal)
    normalized = event_name.strip().lower().replace(" ", "_")
    natural = _natural_goal(normalized)
    if natural != normalized.replace("_", " "):
        return natural
    return event_name


def _price(poi: dict[str, Any]) -> int:
    tier = poi.get("price_tier")
    if isinstance(tier, int):
        return {1: 35, 2: 70, 3: 120, 4: 180}.get(tier, 60)
    return 0


def _load_cached_comment_summaries(
    poi_groups: list[Any],
    cache_dir: Any = DEFAULT_CACHE_DIR,
    *,
    allow_local_fallback: bool = True,
) -> list[EventCommentSummaryGroup]:
    latest_path = cache_dir / "comment_summaries" / "latest_comment_summaries.json"
    if not latest_path.exists():
        return []
    try:
        cached_groups = [EventCommentSummaryGroup.model_validate(item) for item in json.loads(latest_path.read_text(encoding="utf-8"))]
    except Exception:
        return []

    business_ids_by_event = {
        group.event_index: {poi.business_id for poi in group.pois}
        for group in poi_groups
    }
    filtered_groups: list[EventCommentSummaryGroup] = []
    for group in cached_groups:
        wanted_ids = business_ids_by_event.get(group.event_index)
        if not wanted_ids:
            continue
        summaries = [
            summary
            for summary in group.summaries
            if (
                summary.business_id in wanted_ids
                and _summary_is_display_chinese(summary.model_dump())
                and (allow_local_fallback or not _summary_is_local_fallback(summary.model_dump()))
            )
        ]
        if summaries:
            filtered_groups.append(group.model_copy(update={"summaries": summaries}))
    return filtered_groups


def _select_comment_poi_groups(poi_groups: list[Any], *, max_comment_pois: int) -> list[Any]:
    if max_comment_pois <= 0:
        return []
    selected_by_event = {group.event_index: [] for group in poi_groups}
    selected_count = 0
    offset = 0
    while selected_count < max_comment_pois:
        added_any = False
        for group in poi_groups:
            if selected_count >= max_comment_pois:
                break
            if offset >= len(group.pois):
                continue
            selected_by_event[group.event_index].append(group.pois[offset])
            selected_count += 1
            added_any = True
        if not added_any:
            break
        offset += 1
    return [
        group.model_copy(update={"pois": selected_by_event[group.event_index]})
        for group in poi_groups
        if selected_by_event.get(group.event_index)
    ]


def _desired_summary_ids(poi_groups: list[Any]) -> dict[int, set[str]]:
    return {
        group.event_index: {poi.business_id for poi in group.pois}
        for group in poi_groups
    }


def _summary_coverage(
    summary_groups: list[EventCommentSummaryGroup],
    poi_groups: list[Any],
) -> bool:
    desired = _desired_summary_ids(poi_groups)
    if not desired:
        return False
    summaries_by_event = {
        group.event_index: {summary.business_id for summary in group.summaries}
        for group in summary_groups
    }
    return all(ids.issubset(summaries_by_event.get(event_index, set())) for event_index, ids in desired.items())


RISK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(long wait|waited|waiting|line|queue)\b", re.I), "可能需要排队或等待"),
    (re.compile(r"\b(packed|crowded|busy|reservation|book)\b", re.I), "热门时段建议提前预约或避开高峰"),
    (re.compile(r"\b(slow service|slow|took forever|server|host)\b", re.I), "服务速度可能不稳定"),
    (re.compile(r"\b(rude|attitude|ignored|bad service)\b", re.I), "少数评论对服务态度不满意"),
    (re.compile(r"\b(expensive|overpriced|pricey|cost|not worth)\b", re.I), "价格或性价比需要留意"),
    (re.compile(r"\b(parking|garage|street parking)\b", re.I), "停车可能不太方便"),
    (re.compile(r"\b(noisy|noise|loud)\b", re.I), "环境可能偏吵"),
    (re.compile(r"\b(closed|hours|open late|open)\b", re.I), "营业时间需要出发前再确认"),
)

PRO_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(sushi|sashimi|roll|omakase)\b", re.I), "寿司、刺身或 omakase 口碑不错"),
    (re.compile(r"\b(noodle|ramen|pho|pasta|dumpling|dim sum|hot pot)\b", re.I), "面食、点心或热锅类菜品评价不错"),
    (re.compile(r"\b(lunch special|happy hour|brunch|breakfast)\b", re.I), "午餐套餐、早午餐或 happy hour 反馈不错"),
    (re.compile(r"\b(cocktail|beer|wine|drink|bar)\b", re.I), "酒水或吧台体验不错"),
    (re.compile(r"\b(dessert|pastry|bakery|ice cream|cake)\b", re.I), "甜品、烘焙或冰淇淋反馈不错"),
    (re.compile(r"\b(food|dish|menu|delicious|tasty|flavor|fresh|portion)\b", re.I), "菜品味道评价较好"),
    (re.compile(r"\b(attentive|friendly|helpful|kind|great service|server|staff)\b", re.I), "服务细致或态度友好"),
    (re.compile(r"\b(atmosphere|vibe|ambiance|decor|interior|space|cozy|quiet)\b", re.I), "环境氛围较好"),
    (re.compile(r"\b(location|view|walk|convenient|near|market)\b", re.I), "位置和周边便利性较好"),
    (re.compile(r"\b(exhibit|museum|gallery|historic|history|art|collection)\b", re.I), "展览、历史或艺术内容评价不错"),
)


def _local_comment_summary_groups(
    *,
    intent: Intent,
    comment_groups: list[EventCommentGroup],
) -> list[EventCommentSummaryGroup]:
    summary_groups: list[EventCommentSummaryGroup] = []
    for group in comment_groups:
        event = intent.events[group.event_index - 1] if 0 < group.event_index <= len(intent.events) else None
        summaries: list[POICommentSummary] = []
        for bundle in group.bundles:
            loaded_reviews = bundle.review_count_loaded or len(bundle.reviews)
            loaded_tips = bundle.tip_count_loaded or len(bundle.tips)
            if loaded_reviews + loaded_tips == 0:
                continue
            high_reviews = [review for review in bundle.reviews if review.stars >= 4.0]
            low_reviews = [review for review in bundle.reviews if review.stars <= 3.0]
            texts = [review.text for review in bundle.reviews] + [tip.text for tip in bundle.tips]
            pros = _matched_local_labels(texts, PRO_PATTERNS)
            if not pros and high_reviews:
                pros = [f"{len(high_reviews)} 条高分评论提供了正面反馈。"]
            risks = _matched_local_labels(texts, RISK_PATTERNS)
            cons = risks[:2]
            if low_reviews and not cons:
                cons = ["少量低分评论提示体验可能不稳定。"]

            goal = _natural_goal(event.goal if event else group.event_goal)
            sentiment = "整体反馈偏正面" if len(high_reviews) >= max(len(low_reviews), 1) else "评论反馈有分化"
            positive_hint = _strip_sentence_suffix(pros[0]) if pros else "有可参考的用户反馈"
            risk_hint = _strip_sentence_suffix(risks[0]) if risks else "暂时没有明显集中风险"
            risk_clause = risk_hint if risks else "暂时没有明显集中风险"
            summaries.append(
                POICommentSummary(
                    business_id=bundle.business_id,
                    name=bundle.name,
                    city=bundle.city,
                    summary=(
                        f"已读取 {loaded_reviews} 条评论和 {loaded_tips} 条短评。"
                        f"作为{goal}候选点，{sentiment}；主要亮点是{positive_hint}，{risk_clause}。"
                    ),
                    keywords=["评论已读取", "本地摘要"],
                    pros=pros[:3],
                    cons=cons[:2],
                    notable_risks=risks[:3],
                    evidence=[_truncate_comment_text(text) for text in texts[:2] if text.strip()],
                    confidence=0.42,
                    inference_seconds=0.0,
                )
            )
        if summaries:
            summary_groups.append(
                EventCommentSummaryGroup(
                    event_index=group.event_index,
                    event_name=group.event_name,
                    event_goal=group.event_goal,
                    summaries=summaries,
                )
            )
    return summary_groups


def _matched_local_labels(texts: list[str], patterns: tuple[tuple[re.Pattern[str], str], ...]) -> list[str]:
    labels: list[str] = []
    for text in texts:
        for pattern, label in patterns:
            if pattern.search(text) and label not in labels:
                labels.append(label)
    return labels


DISPLAY_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("寿司、刺身或 omakase 被正面提到", "寿司、刺身或 omakase 口碑不错"),
    ("面食、点心或热锅类菜品被评论提到", "面食、点心或热锅类菜品评价不错"),
    ("甜品、烘焙或冰淇淋被正面提到", "甜品、烘焙或冰淇淋反馈不错"),
    ("服务细致或态度友好被评论提到", "服务细致或态度友好"),
    ("环境氛围或空间体验有正面反馈", "环境氛围较好"),
    ("位置、景观或周边便利性被提到", "位置和周边便利性较好"),
    ("展览、历史或艺术内容被正面提到", "展览、历史或艺术内容评价不错"),
    ("评论提到可能需要排队或等待", "可能需要排队或等待"),
    ("部分评论提到服务速度或服务体验不稳定", "服务速度或服务体验可能不稳定"),
    ("部分评论认为价格或性价比需要留意", "价格或性价比需要留意"),
    ("需要留意营业时间需要出发前再确认", "需要出发前确认营业时间"),
    ("需要留意价格或性价比需要留意", "价格或性价比需要留意"),
    ("需要留意可能需要排队或等待", "可能需要排队或等待"),
    ("需要留意停车可能不太方便", "停车可能不太方便"),
    ("需要留意环境可能偏吵", "环境可能偏吵"),
)


def _normalize_display_text(text: str) -> str:
    cleaned = text.strip()
    for old, new in DISPLAY_TEXT_REPLACEMENTS:
        cleaned = cleaned.replace(old, new)
    return cleaned


def _strip_sentence_suffix(text: str) -> str:
    return _normalize_display_text(text).rstrip("。；;")


def _clean_sentence_parts(items: list[str], *, limit: int) -> list[str]:
    parts: list[str] = []
    for item in items:
        cleaned = _strip_sentence_suffix(item)
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
        if len(parts) >= limit:
            break
    return parts


def _join_sentence_parts(items: list[str], *, limit: int) -> str:
    parts = _clean_sentence_parts(items, limit=limit)
    return "；".join(parts)


def _truncate_comment_text(text: str, *, max_chars: int = 180) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def _comment_source_label(source: str) -> str:
    if source == "cached":
        return "使用已缓存的评论摘要"
    if source == "generated":
        return "已重新解析用户评论"
    if source.startswith("local_fallback_after_"):
        return "评论模型暂时失败，已用已加载评论生成本地摘要"
    if source == "local_fallback_missing_llm_config":
        return "未配置评论模型，已用已加载评论生成本地摘要"
    if source == "disabled":
        return "评论摘要已关闭"
    if source == "missing_comment_files":
        return "没有找到本地评论文件"
    if source == "missing_llm_config":
        return "没有可用的评论模型配置"
    if source == "no_comment_pois_selected":
        return "没有选中需要读取评论的地点"
    if source.startswith("comment_load_failed:"):
        return "读取评论文件失败"
    if source.startswith("summary_failed:"):
        return "评论模型解析失败"
    return source


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _summary_is_display_chinese(summary: dict[str, Any]) -> bool:
    texts = [summary.get("summary") or ""]
    for key in ("keywords", "pros", "cons", "notable_risks", "evidence"):
        values = summary.get(key) or []
        if isinstance(values, list):
            texts.extend(str(value) for value in values if value)
    meaningful = [text for text in texts if text.strip()]
    return bool(meaningful) and any(_has_cjk(text) for text in meaningful)


def _summary_is_local_fallback(summary: dict[str, Any]) -> bool:
    keywords = summary.get("keywords") or []
    return any(str(keyword) == "本地摘要" for keyword in keywords)


def _resolve_comment_files(poi_groups: list[Any]) -> tuple[Any, Any] | None:
    all_pois = [poi for group in poi_groups for poi in group.pois]
    if not all_pois:
        return None
    city = (all_pois[0].city or "").lower()
    state = (all_pois[0].state or "").lower()
    for metadata_file in sorted(DEFAULT_INTERIM_DIR.glob("*/metadata.json")):
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (metadata.get("city") or "").lower() != city:
            continue
        if state and (metadata.get("state") or "").lower() != state:
            continue
        subset_dir = metadata_file.parent
        review_file = subset_dir / "yelp_academic_dataset_review.json"
        tip_file = subset_dir / "yelp_academic_dataset_tip.json"
        if review_file.exists() and tip_file.exists():
            return review_file, tip_file
    return None


def _build_comment_summary_groups(
    *,
    intent: Intent,
    poi_groups: list[Any],
    payload: dict[str, Any],
    env_settings: dict[str, str],
) -> tuple[list[EventCommentSummaryGroup], str]:
    max_comment_pois = int(_env_value(env_settings, "COMMENT_MAX_POIS") or "20")
    selected_poi_groups = _select_comment_poi_groups(poi_groups, max_comment_pois=max_comment_pois)
    if not selected_poi_groups:
        return [], "no_comment_pois_selected"

    api_key, base_url, model = _comment_llm_config(payload, env_settings)
    cached_groups = _load_cached_comment_summaries(
        selected_poi_groups,
        allow_local_fallback=not (api_key and model),
    )
    if _summary_coverage(cached_groups, selected_poi_groups):
        return cached_groups, "cached"

    if (_env_value(env_settings, "COMMENT_SUMMARIES_ENABLED") or "true").lower() in {"0", "false", "no"}:
        return cached_groups, "disabled"

    files = _resolve_comment_files(selected_poi_groups)
    if files is None:
        return cached_groups, "missing_comment_files"

    review_file, tip_file = files
    max_reviews = int(_env_value(env_settings, "COMMENT_MAX_REVIEWS_PER_POI") or "20")
    max_tips = int(_env_value(env_settings, "COMMENT_MAX_TIPS_PER_POI") or "10")
    try:
        comment_groups = load_cached_comments(
            cache_dir=DEFAULT_CACHE_DIR,
            poi_groups=selected_poi_groups,
            review_file=review_file,
            tip_file=tip_file,
            max_reviews_per_poi=max_reviews,
            max_tips_per_poi=max_tips,
        )
        if comment_groups is None:
            comment_groups = load_event_comment_groups(
                selected_poi_groups,
                review_file=review_file,
                tip_file=tip_file,
                max_reviews_per_poi=max_reviews,
                max_tips_per_poi=max_tips,
            )
            save_cached_comments(
                comment_groups,
                cache_dir=DEFAULT_CACHE_DIR,
                poi_groups=selected_poi_groups,
                review_file=review_file,
                tip_file=tip_file,
                max_reviews_per_poi=max_reviews,
                max_tips_per_poi=max_tips,
            )
    except Exception as error:
        return cached_groups, f"comment_load_failed:{type(error).__name__}"

    if not api_key or not model:
        fallback_groups = _local_comment_summary_groups(intent=intent, comment_groups=comment_groups)
        if fallback_groups:
            save_cached_comment_summaries(
                fallback_groups,
                cache_dir=DEFAULT_CACHE_DIR,
                intent=intent,
                comment_groups=comment_groups,
                model="local_fallback",
                base_url=None,
            )
            return fallback_groups, "local_fallback_missing_llm_config"
        return cached_groups, "missing_llm_config"

    try:
        client = OpenAICompatibleClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=float(_env_value(env_settings, "COMMENT_SUMMARY_TIMEOUT_SEC") or "25"),
        )
        summary_groups = summarize_event_comment_groups(
            intent,
            comment_groups,
            llm_client=client,
            max_bundles_per_event=None,
            max_reviews=int(_env_value(env_settings, "COMMENT_SUMMARY_MAX_REVIEWS") or "3"),
            max_tips=int(_env_value(env_settings, "COMMENT_SUMMARY_MAX_TIPS") or "2"),
            batch_size=int(_env_value(env_settings, "COMMENT_SUMMARY_BATCH_SIZE") or "10"),
            max_parallel_batches=int(_env_value(env_settings, "COMMENT_SUMMARY_MAX_PARALLEL_BATCHES") or "2"),
            batch_retries=int(_env_value(env_settings, "COMMENT_SUMMARY_BATCH_RETRIES") or "0"),
        )
        save_cached_comment_summaries(
            summary_groups,
            cache_dir=DEFAULT_CACHE_DIR,
            intent=intent,
            comment_groups=comment_groups,
            model=model,
            base_url=base_url,
        )
        return summary_groups, "generated"
    except Exception as error:
        fallback_groups = _local_comment_summary_groups(intent=intent, comment_groups=comment_groups)
        if fallback_groups:
            save_cached_comment_summaries(
                fallback_groups,
                cache_dir=DEFAULT_CACHE_DIR,
                intent=intent,
                comment_groups=comment_groups,
                model="local_fallback",
                base_url=None,
            )
            return fallback_groups, f"local_fallback_after_{type(error).__name__}"
        return cached_groups, f"summary_failed:{type(error).__name__}"


def _review_summary_lines(raw: dict[str, Any], poi_type: str, event_goal: str | None) -> list[str]:
    summary = _normalize_display_text(str(raw.get("comment_summary"))) if raw.get("comment_summary") else None
    pros = [text for text in raw.get("comment_pros") or [] if text]
    categories = [_natural_category(category) for category in (raw.get("categories") or [])[:2]]
    if summary:
        lines = [summary]
        if pros:
            lines.append("亮点：" + _join_sentence_parts(pros, limit=2) + "。")
        return lines[:3]
    context = f"适合作为{_natural_goal(event_goal)}安排"
    if categories:
        context += "，主要匹配" + "、".join(categories)
    context += f"；评分 {raw['stars']:.1f}，累计 {raw['review_count']} 条评价。"
    return [context, "暂时没有可用的评论摘要，下面的判断主要来自类别、评分和评论数量。"]


def _risk_note_lines(raw: dict[str, Any]) -> list[str]:
    risks = [text for text in raw.get("comment_notable_risks") or [] if text]
    cons = [text for text in raw.get("comment_cons") or [] if text]
    notes = _clean_sentence_parts(risks, limit=2)
    for con in cons:
        cleaned = _strip_sentence_suffix(con)
        if cleaned and cleaned not in notes:
            notes.append(cleaned)
        if len(notes) >= 3:
            break
    if notes:
        return notes[:3]
    if not raw.get("comment_summary_available"):
        return ["还没有覆盖到这家店的评论摘要，排队、服务和性价比风险需要到店前再确认。"]
    return ["评论摘要里没有明显风险，但仍建议确认营业时间和现场排队情况。"]


def _recommend_reason(raw: dict[str, Any], event_name: str, event_goal: str | None) -> str:
    pros = [text for text in raw.get("comment_pros") or [] if text]
    summary = _normalize_display_text(str(raw.get("comment_summary"))) if raw.get("comment_summary") else None
    if pros:
        return _join_sentence_parts(pros, limit=3) + "。"
    if summary:
        return _strip_sentence_suffix(summary) + "。"
    event_label = _event_display_name(event_name, event_goal)
    return f"推荐它作为{event_label}，因为它和这一段需求匹配，评分 {raw['stars']:.1f}，累计 {raw['review_count']} 条评价。"


def _frontend_pois(aggregated_groups: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in aggregated_groups:
        for poi in group.pois:
            raw = poi.model_dump()
            if raw["business_id"] in seen:
                continue
            seen.add(raw["business_id"])
            poi_type = _poi_type(raw.get("categories") or [], group.event_goal)
            price = _price(raw)
            keywords = raw.get("comment_keywords") or []
            rows.append(
                {
                    "id": raw["business_id"],
                    "name": raw["name"],
                    "type": poi_type,
                    "category": _poi_category(poi_type),
                    "lng": raw["longitude"],
                    "lat": raw["latitude"],
                    "rating": raw["stars"],
                    "avgPrice": price,
                    "queueTime": min(35, max(4, round((raw.get("review_count") or 0) / 120))),
                    "stayTime": 45,
                    "recommendedStayTime": 45,
                    "tags": (keywords[:3] or [_natural_category(category) for category in (raw.get("categories") or [])[:3]] or [poi_type]),
                    "commentParsed": bool(raw.get("comment_summary_available")),
                    "reviewSummary": _review_summary_lines(raw, poi_type, group.event_goal),
                    "riskNotes": _risk_note_lines(raw),
                    "recommendReason": _recommend_reason(raw, group.event_name, group.event_goal),
                    "alternatives": [],
                    "price": price,
                    "distance": raw.get("distance_to_anchor_km"),
                }
            )

    by_type: dict[str, list[str]] = {}
    for row in rows:
        by_type.setdefault(row["type"], []).append(row["id"])
    for row in rows:
        row["alternatives"] = [item for item in by_type.get(row["type"], []) if item != row["id"]][:4]
    return rows


def _clock(offset_minutes: float) -> str:
    minutes = int(round(offset_minutes))
    hour = 10 + minutes // 60
    minute = minutes % 60
    return f"{hour % 24:02d}:{minute:02d}"


def _frontend_routes(routes: list[Any], pois: list[dict[str, Any]], duration_hours: float) -> list[dict[str, Any]]:
    poi_map = {poi["id"]: poi for poi in pois}
    plans: list[dict[str, Any]] = []
    for index, route in enumerate(routes[:3], start=1):
        raw = route.model_dump()
        poi_ids = [stop["business_id"] for stop in raw["stops"] if stop.get("kind") == "poi" and stop.get("business_id") in poi_map]
        if not poi_ids:
            continue
        travel_minutes = round((raw.get("total_travel_seconds") or 0) / 60)
        dwell_minutes = round(raw.get("total_dwell_minutes") or len(poi_ids) * 45)
        total_minutes = travel_minutes + dwell_minutes
        total_queue = sum(poi_map[poi_id]["queueTime"] for poi_id in poi_ids)
        avg_cost = round(sum(poi_map[poi_id]["avgPrice"] for poi_id in poi_ids) / max(len(poi_ids), 1))
        timeline: list[dict[str, Any]] = []
        cursor = 0.0
        leg_minutes = [0.0] + [round((leg.get("duration_seconds") or 0) / 60) for leg in raw["legs"] if leg.get("destination_name")]
        for stop_index, poi_id in enumerate(poi_ids):
            walk = leg_minutes[min(stop_index + 1, len(leg_minutes) - 1)] if len(leg_minutes) > 1 else 0
            cursor += walk
            arrive = _clock(cursor)
            cursor += poi_map[poi_id]["stayTime"]
            timeline.append({"poiId": poi_id, "arriveTime": arrive, "leaveTime": _clock(cursor), "walkMinutes": round(walk)})
        if total_minutes <= duration_hours * 60:
            status = "可执行"
        elif total_minutes <= duration_hours * 60 + 30:
            status = "略紧张"
        else:
            status = "不可执行"
        strategy = "experience" if index == 1 else "efficiency" if index == 2 else "lowQueue"
        polyline = [point for leg in raw["legs"] for point in leg.get("polyline", [])]
        plans.append(
            {
                "id": raw["route_id"],
                "name": f"推荐路线 {index}",
                "strategy": strategy,
                "poiIds": poi_ids,
                "totalDuration": total_minutes,
                "totalDistance": round((raw.get("total_distance_meters") or 0) / 1000, 1),
                "totalQueueTime": total_queue,
                "avgCost": avg_cost,
                "reason": raw.get("explanation") or "根据你的需求生成。",
                "status": status,
                "timelineStart": "10:00",
                "label": f"推荐路线 {index}",
                "tag": "实时路线" if raw.get("feasible") else "需复核",
                "stops": timeline,
                "totalMinutes": total_minutes,
                "polyline": [[point[1], point[0]] for point in polyline] if polyline else [[poi_map[poi_id]["lng"], poi_map[poi_id]["lat"]] for poi_id in poi_ids],
                "preferenceScore": max(50, min(99, round((raw.get("score") or 0) + 50))),
                "preferenceTags": ["精选地点", "步行路线" if raw.get("mode") == "walking" else "出行路线"],
                "preferenceReason": raw.get("explanation") or "",
            }
        )
    return plans


def generate_route_plan(payload: dict[str, Any]) -> dict[str, Any]:
    env_settings = _load_api_env()
    travel_intent = payload.get("travelIntent") or {}
    query = str(payload.get("query") or travel_intent.get("rawText") or "").strip()
    if not query:
        raise ValueError("query is required")

    duration_hours = float(travel_intent.get("durationHours") or payload.get("durationHours") or 4)
    mode: RouteTravelMode = payload.get("mode") if payload.get("mode") in MODE_SPEED_KPH else "walking"
    anchor = _anchor_from_payload(payload)
    answers = payload.get("clarificationAnswers") if isinstance(payload.get("clarificationAnswers"), dict) else {}
    intent = _intent_from_payload(payload, query, env_settings)
    budget_plan = build_clarification_plan(intent)
    if _answered({question.id for question in budget_plan.questions}, answers):
        intent = apply_clarification_answers(intent, answers, plan=budget_plan)
        budget_plan = build_clarification_plan(intent)
    _raise_if_clarification_needed(intent=intent, questions=_question_payloads(budget_plan), answers=answers)

    business_file = resolve_business_file(intent)
    spatial_constraint = SpatialConstraint(anchor=anchor, max_radius_km=8.0, mode=mode)
    poi_groups = load_candidate_poi_groups(intent, business_file=business_file, max_pois=24, spatial_constraint=spatial_constraint)
    poi_plan = build_poi_refinement_plan(intent, poi_groups)
    if _answered({question.id for question in poi_plan.questions}, answers):
        intent = apply_clarification_answers(intent, answers, plan=poi_plan)
        poi_groups = load_candidate_poi_groups(intent, business_file=business_file, max_pois=24, spatial_constraint=spatial_constraint)
        poi_plan = build_poi_refinement_plan(intent, poi_groups)
    poi_question_event_indices = {question.event_index for question in poi_plan.questions}
    extra_questions = _extra_category_refinement_questions(intent, poi_groups, skip_event_indices=poi_question_event_indices)
    if _answered({question["id"] for question in extra_questions}, answers):
        intent = _apply_extra_category_answers(intent, extra_questions, answers)
        poi_groups = load_candidate_poi_groups(intent, business_file=business_file, max_pois=24, spatial_constraint=spatial_constraint)
        poi_plan = build_poi_refinement_plan(intent, poi_groups)
        poi_question_event_indices = {question.event_index for question in poi_plan.questions}
        extra_questions = _extra_category_refinement_questions(intent, poi_groups, skip_event_indices=poi_question_event_indices)
    _raise_if_clarification_needed(
        intent=intent,
        questions=_question_payloads(poi_plan) + extra_questions,
        answers=answers,
    )

    summary_groups, comment_summary_source = _build_comment_summary_groups(
        intent=intent,
        poi_groups=poi_groups,
        payload=payload,
        env_settings=env_settings,
    )
    aggregated_groups = aggregate_event_poi_groups(poi_groups, summary_groups)
    routes = find_route_candidates(
        intent=intent,
        aggregated_groups=aggregated_groups,
        direction_client=_direction_client(env_settings),
        mode=mode,
        anchor=anchor,
        max_pois_per_event=4,
        max_candidates=12,
        dwell_minutes_per_event=45.0,
        require_return=bool(intent.return_location),
    )

    save_cached_intent(intent, cache_dir=DEFAULT_CACHE_DIR, query=query, default_city="Philadelphia", model="api", base_url=None)
    save_cached_pois(poi_groups, cache_dir=DEFAULT_CACHE_DIR, intent=intent, business_file=business_file, max_pois=24)
    save_cached_aggregated_pois(aggregated_groups, cache_dir=DEFAULT_CACHE_DIR, poi_groups=poi_groups, summary_groups=summary_groups)
    save_cached_routes(
        routes,
        cache_dir=DEFAULT_CACHE_DIR,
        intent=intent,
        aggregated_groups=aggregated_groups,
        mode=mode,
        anchor=anchor,
        max_pois_per_event=4,
        max_candidates=12,
        dwell_minutes_per_event=45.0,
        require_return=bool(intent.return_location),
    )

    frontend_pois = _frontend_pois(aggregated_groups)
    frontend_routes = _frontend_routes(routes, frontend_pois, duration_hours)
    if not frontend_routes:
        raise ValueError("Backend did not find any route candidates for this query.")

    return {
        "intent": intent.model_dump(),
        "anchor": anchor.model_dump(),
        "pois": frontend_pois,
        "routes": frontend_routes,
        "agentNotices": [
            f"已经理解出 {len(intent.events)} 段行程，并挑选了 {len(frontend_pois)} 个候选地点。",
            f"评论摘要：{_comment_source_label(comment_summary_source)}，已覆盖 {sum(len(group.summaries) for group in summary_groups)} 个地点的评论和短评。",
            f"已生成 {len(frontend_routes)} 条路线；路段使用{'实时道路路线' if not isinstance(_direction_client(env_settings), ApproximateDirectionClient) else '距离估算'}。",
        ],
    }


def generate_clarification_plan(payload: dict[str, Any]) -> dict[str, Any]:
    env_settings = _load_api_env()
    travel_intent = payload.get("travelIntent") or {}
    query = str(payload.get("query") or travel_intent.get("rawText") or "").strip()
    if not query:
        raise ValueError("query is required")

    intent = _intent_from_payload(payload, query, env_settings)
    budget_plan = build_clarification_plan(intent)
    questions = _question_payloads(budget_plan)
    return {
        "needsClarification": bool(questions),
        "intent": intent.model_dump(),
        "questions": questions,
    }


class PlannerRequestHandler(BaseHTTPRequestHandler):
    server_version = "MeituanPlannerAPI/0.1"

    def do_OPTIONS(self) -> None:
        _json_response(self, 204, {})

    def do_GET(self) -> None:
        if self.path == "/api/planner/health":
            _json_response(self, 200, {"ok": True})
            return
        _json_response(self, 404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path not in {"/api/planner/routes", "/api/planner/clarifications"}:
            _json_response(self, 404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            result = generate_clarification_plan(payload) if self.path == "/api/planner/clarifications" else generate_route_plan(payload)
        except ClarificationNeeded as exc:
            _json_response(
                self,
                409,
                {
                    "needsClarification": True,
                    "intent": exc.intent.model_dump(),
                    "questions": exc.questions,
                },
            )
            return
        except Exception as exc:
            _json_response(self, 500, {"error": str(exc)})
            return
        _json_response(self, 200, result)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Meituan planner HTTP API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), PlannerRequestHandler)
    print(f"Planner API listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
