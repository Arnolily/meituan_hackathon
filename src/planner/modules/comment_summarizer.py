from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from time import perf_counter
from typing import Any, Callable, Optional, Protocol

from planner.llm.prompts import (
    COMMENT_BATCH_SUMMARIZER_SYSTEM_PROMPT,
    COMMENT_SUMMARIZER_SYSTEM_PROMPT,
    build_comment_batch_summarizer_user_prompt,
    build_comment_summarizer_user_prompt,
)
from planner.schemas import EventCommentGroup, EventCommentSummaryGroup, Intent, POICommentBundle, POICommentSummary


class JSONLLMClient(Protocol):
    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> dict[str, Any]:
        ...


GOAL_KEYWORDS: dict[str, list[str]] = {
    "breakfast": ["breakfast", "brunch", "coffee", "早饭", "早餐", "早午餐"],
    "lunch": ["lunch", "food", "restaurant", "meal", "taco", "sandwich", "午餐", "吃饭", "餐厅"],
    "dinner": ["dinner", "food", "restaurant", "meal", "reservation", "service", "晚餐", "吃饭", "餐厅"],
    "coffee": ["coffee", "cafe", "latte", "espresso", "pastry", "咖啡", "咖啡馆"],
    "dessert": ["dessert", "ice cream", "bakery", "cake", "甜品", "冰淇淋", "烘焙"],
    "drinks": ["drink", "bar", "cocktail", "beer", "wine", "酒吧", "饮品"],
    "nightlife": ["bar", "cocktail", "music", "night", "夜生活", "酒吧"],
    "shopping": ["shopping", "store", "mall", "boutique", "购物", "商场"],
    "sightseeing": ["sightseeing", "view", "historic", "walk", "观光", "景点"],
    "museum": ["museum", "exhibit", "collection", "gallery", "art", "博物馆", "展览", "艺术"],
    "park": ["park", "outdoor", "green", "walk", "garden", "trail", "公园", "户外", "散步"],
    "historical_site": ["historic", "history", "landmark", "tour", "历史", "地标"],
    "art_gallery": ["art", "gallery", "exhibit", "艺术", "画廊", "展览"],
    "performance": ["performance", "show", "theater", "music", "演出", "剧场"],
    "games": ["game", "arcade", "fun", "activity", "游戏", "娱乐"],
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Chinese": ["chinese", "noodle", "dumpling", "中餐", "面", "饺子"],
    "Japanese": ["japanese", "sushi", "ramen", "日料", "寿司", "拉面"],
    "Italian": ["italian", "pasta", "pizza", "意餐", "披萨"],
    "Mexican": ["mexican", "taco", "burrito", "墨西哥", "塔可"],
    "Seafood": ["seafood", "fish", "oyster", "海鲜"],
    "Restaurants": ["restaurant", "food", "meal", "service", "餐厅", "吃饭"],
    "Food": ["food", "meal", "snack", "吃饭", "餐饮"],
    "Breakfast & Brunch": ["breakfast", "brunch", "pancake", "早午餐"],
    "Coffee & Tea": ["coffee", "tea", "latte", "咖啡", "茶"],
    "Cafes": ["cafe", "coffee", "pastry", "咖啡馆"],
    "Museums": ["museum", "exhibit", "collection", "博物馆"],
    "Art Museums": ["art", "museum", "painting", "艺术博物馆"],
    "Art Galleries": ["gallery", "art", "exhibit", "画廊"],
    "Parks": ["park", "green", "outdoor", "公园"],
    "Active Life": ["outdoor", "activity", "walk", "户外"],
    "Shopping Centers": ["shopping", "mall", "store", "购物中心"],
    "Arts & Entertainment": ["art", "entertainment", "show", "文化娱乐"],
    "Bars": ["bar", "beer", "cocktail", "酒吧"],
}


def summarize_event_comment_groups(
    intent: Intent,
    comment_groups: list[EventCommentGroup],
    *,
    llm_client: JSONLLMClient,
    max_bundles_per_event: Optional[int] = 10,
    max_reviews: int = 8,
    max_tips: int = 6,
    max_chars_per_item: int = 280,
    batch_size: int = 7,
    max_parallel_batches: int = 2,
    batch_retries: int = 3,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
) -> list[EventCommentSummaryGroup]:
    event_map = {index: event for index, event in enumerate(intent.events, start=1)}
    total = sum(len(group.bundles[:max_bundles_per_event]) if max_bundles_per_event is not None else len(group.bundles) for group in comment_groups)
    completed = 0
    summary_groups: list[EventCommentSummaryGroup] = []
    for group in comment_groups:
        if group.event_index not in event_map:
            raise ValueError(f"Unknown event_index in comment group: {group.event_index}")
        bundles = group.bundles[:max_bundles_per_event] if max_bundles_per_event is not None else group.bundles
        batches = _chunked(bundles, batch_size=max(batch_size, 1))
        batch_results: list[Optional[list[POICommentSummary]]] = [None] * len(batches)
        with ThreadPoolExecutor(max_workers=max(max_parallel_batches, 1)) as executor:
            futures = {
                executor.submit(
                    summarize_poi_comment_batch,
                    intent,
                    event_index=group.event_index,
                    bundles=batch,
                    llm_client=llm_client,
                    max_reviews=max_reviews,
                    max_tips=max_tips,
                    max_chars_per_item=max_chars_per_item,
                    batch_retries=batch_retries,
                ): (index, batch)
                for index, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                index, batch = futures[future]
                batch_summaries = future.result()
                batch_results[index] = batch_summaries
                completed += len(batch_summaries)
                if progress_callback is not None:
                    progress_callback(
                        {
                            "completed": completed,
                            "total": total,
                            "event_name": group.event_name,
                            "event_goal": group.event_goal,
                            "poi_name": ", ".join(bundle.name for bundle in batch),
                            "batch_size": len(batch),
                        }
                    )
        summaries = [
            summary
            for batch_summaries in batch_results
            for summary in (batch_summaries if batch_summaries is not None else [])
        ]
        if len(summaries) != len(bundles):
            raise RuntimeError(
                f"Expected {len(bundles)} comment summaries for event {group.event_index}, got {len(summaries)}."
            )
        summary_groups.append(
            EventCommentSummaryGroup(
                event_index=group.event_index,
                event_name=group.event_name,
                event_goal=group.event_goal,
                summaries=summaries,
            )
        )
    return summary_groups


def summarize_poi_comment_batch(
    intent: Intent,
    *,
    event_index: int,
    bundles: list[POICommentBundle],
    llm_client: JSONLLMClient,
    max_reviews: int = 8,
    max_tips: int = 6,
    max_chars_per_item: int = 280,
    batch_retries: int = 3,
) -> list[POICommentSummary]:
    if not bundles:
        return []
    keywords = _keywords_for_event(intent, event_index)
    if len(bundles) == 1:
        return [
            summarize_poi_comment_bundle(
                intent,
                event_index=event_index,
                bundle=bundles[0],
                llm_client=llm_client,
                max_reviews=max_reviews,
                max_tips=max_tips,
                max_chars_per_item=max_chars_per_item,
                keywords=keywords,
            )
        ]

    event = intent.events[event_index - 1]
    bundle_map = {bundle.business_id: bundle for bundle in bundles}
    user_prompt = build_comment_batch_summarizer_user_prompt(
        overall_intent=_overall_intent_payload(intent),
        event_intent=event.model_dump(),
        pois=[
            {
                "business_id": bundle.business_id,
                "name": bundle.name,
                "city": bundle.city,
                "reviews": _pack_reviews(bundle, max_reviews=max_reviews, max_chars_per_item=max_chars_per_item, keywords=keywords),
                "tips": _pack_tips(bundle, max_tips=max_tips, max_chars_per_item=max_chars_per_item, keywords=keywords),
            }
            for bundle in bundles
        ],
    )
    last_error: Optional[Exception] = None
    for attempt in range(max(batch_retries, 0) + 1):
        started_at = perf_counter()
        try:
            payload = llm_client.generate_json(
                system_prompt=COMMENT_BATCH_SUMMARIZER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.0,
            )
            elapsed = perf_counter() - started_at
            return _validate_batch_payload(payload, bundle_map=bundle_map, bundles=bundles, elapsed=elapsed)
        except Exception as error:
            last_error = error
            if attempt >= max(batch_retries, 0):
                break
    raise RuntimeError(f"Failed to summarize POI comment batch after {max(batch_retries, 0) + 1} attempts.") from last_error


def summarize_poi_comment_bundle(
    intent: Intent,
    *,
    event_index: int,
    bundle: POICommentBundle,
    llm_client: JSONLLMClient,
    max_reviews: int = 8,
    max_tips: int = 6,
    max_chars_per_item: int = 280,
    keywords: Optional[list[str]] = None,
) -> POICommentSummary:
    event = intent.events[event_index - 1]
    event_keywords = keywords or _keywords_for_event(intent, event_index)
    packed_reviews = _pack_reviews(bundle, max_reviews=max_reviews, max_chars_per_item=max_chars_per_item, keywords=event_keywords)
    packed_tips = _pack_tips(bundle, max_tips=max_tips, max_chars_per_item=max_chars_per_item, keywords=event_keywords)
    started_at = perf_counter()
    payload = llm_client.generate_json(
        system_prompt=COMMENT_SUMMARIZER_SYSTEM_PROMPT,
        user_prompt=build_comment_summarizer_user_prompt(
            overall_intent=_overall_intent_payload(intent),
            event_intent=event.model_dump(),
            poi={
                "business_id": bundle.business_id,
                "name": bundle.name,
                "city": bundle.city,
            },
            packed_reviews=packed_reviews,
            packed_tips=packed_tips,
        ),
        temperature=0.0,
    )
    elapsed = perf_counter() - started_at
    return POICommentSummary.model_validate(
        {
            "business_id": bundle.business_id,
            "name": bundle.name,
            "city": bundle.city,
            "inference_seconds": round(elapsed, 3),
            **payload,
        }
    )


def _validate_batch_payload(
    payload: dict[str, Any],
    *,
    bundle_map: dict[str, POICommentBundle],
    bundles: list[POICommentBundle],
    elapsed: float,
) -> list[POICommentSummary]:
    raw_summaries = payload.get("summaries")
    if not isinstance(raw_summaries, list):
        raise ValueError("Batch summarizer response must contain a summaries array.")

    valid_summaries: dict[str, POICommentSummary] = {}
    seconds_per_summary = round(elapsed / max(len(raw_summaries), 1), 3)
    for raw_summary in raw_summaries:
        if not isinstance(raw_summary, dict):
            raise ValueError("Each batch summary must be a JSON object.")
        business_id = raw_summary.get("business_id")
        bundle = bundle_map.get(business_id)
        if bundle is None:
            raise ValueError(f"Batch summarizer returned unknown business_id: {business_id}")
        if business_id in valid_summaries:
            raise ValueError(f"Batch summarizer returned duplicate business_id: {business_id}")
        valid_summaries[business_id] = POICommentSummary.model_validate(
            {
                **raw_summary,
                "business_id": bundle.business_id,
                "name": bundle.name,
                "city": bundle.city,
                "inference_seconds": seconds_per_summary,
            }
        )

    missing_ids = [bundle.business_id for bundle in bundles if bundle.business_id not in valid_summaries]
    if missing_ids:
        raise ValueError(f"Batch summarizer omitted business_id values: {missing_ids}")
    return [valid_summaries[bundle.business_id] for bundle in bundles]


def _overall_intent_payload(intent: Intent) -> dict[str, Any]:
    return {
        "raw_query": intent.raw_query,
        "city": intent.city,
        "overall_goal": intent.overall_goal,
        "start_time": intent.start_time,
        "end_time": intent.end_time,
        "return_location": intent.return_location,
        "hard_constraints": intent.hard_constraints,
        "soft_preferences": intent.soft_preferences,
    }


def _chunked(items: list[POICommentBundle], *, batch_size: int) -> list[list[POICommentBundle]]:
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _keywords_for_event(intent: Intent, event_index: int) -> list[str]:
    event = intent.events[event_index - 1]
    tokens: list[str] = []
    for source in [
        intent.raw_query,
        intent.overall_goal,
        event.name or "",
        event.goal,
        " ".join(event.categories),
        " ".join(event.poi_types),
        " ".join(event.hard_constraints),
        " ".join(event.soft_preferences),
    ]:
        tokens.extend(_extract_keywords(source))
    tokens.extend(GOAL_KEYWORDS.get(event.goal, []))
    for category in event.categories:
        tokens.extend(CATEGORY_KEYWORDS.get(category, []))
        tokens.extend(_extract_keywords(category))
    for poi_type in event.poi_types:
        tokens.extend(_extract_keywords(poi_type.replace("_", " ")))
    return _dedupe_keywords(tokens)


def _extract_keywords(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower()
    ascii_tokens = re.findall(r"[a-z0-9][a-z0-9'& -]{1,40}", lowered)
    cjk_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    tokens: list[str] = []
    for token in ascii_tokens:
        cleaned = " ".join(token.replace("&", " ").split())
        if len(cleaned) >= 3:
            tokens.append(cleaned)
            tokens.extend(part for part in cleaned.split() if len(part) >= 3)
    tokens.extend(cjk_tokens)
    return tokens


def _dedupe_keywords(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        cleaned = token.strip().lower()
        if len(cleaned) < 2 or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _score_text_for_keywords(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for keyword in keywords if keyword and keyword in lowered)


def _select_reviews(bundle: POICommentBundle, *, max_reviews: int, keywords: list[str]) -> list[Any]:
    if max_reviews <= 0:
        return []
    scored = [
        (_score_text_for_keywords(review.text, keywords), review.useful, review.date, index, review)
        for index, review in enumerate(bundle.reviews)
    ]
    matched = [item for item in scored if item[0] > 0]
    if matched:
        return [item[-1] for item in sorted(matched, key=lambda item: (-item[0], -item[1], item[3]))[:max_reviews]]
    return bundle.reviews[:max_reviews]


def _select_tips(bundle: POICommentBundle, *, max_tips: int, keywords: list[str]) -> list[Any]:
    if max_tips <= 0:
        return []
    scored = [
        (_score_text_for_keywords(tip.text, keywords), tip.compliment_count, tip.date, index, tip)
        for index, tip in enumerate(bundle.tips)
    ]
    matched = [item for item in scored if item[0] > 0]
    if matched:
        return [item[-1] for item in sorted(matched, key=lambda item: (-item[0], -item[1], item[3]))[:max_tips]]
    return bundle.tips[:max_tips]


def _pack_reviews(bundle: POICommentBundle, *, max_reviews: int, max_chars_per_item: int, keywords: Optional[list[str]] = None) -> list[str]:
    packed: list[str] = []
    for review in _select_reviews(bundle, max_reviews=max_reviews, keywords=keywords or []):
        text = _truncate(review.text, max_chars=max_chars_per_item)
        packed.append(f"stars={review.stars}; useful={review.useful}; date={review.date}; text={text}")
    return packed


def _pack_tips(bundle: POICommentBundle, *, max_tips: int, max_chars_per_item: int, keywords: Optional[list[str]] = None) -> list[str]:
    packed: list[str] = []
    for tip in _select_tips(bundle, max_tips=max_tips, keywords=keywords or []):
        text = _truncate(tip.text, max_chars=max_chars_per_item)
        packed.append(f"compliments={tip.compliment_count}; date={tip.date}; text={text}")
    return packed


def _truncate(text: str, *, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."
