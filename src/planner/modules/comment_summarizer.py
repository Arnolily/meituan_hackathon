from __future__ import annotations

from time import perf_counter
from typing import Any, Callable, Optional, Protocol

from planner.llm.prompts import COMMENT_SUMMARIZER_SYSTEM_PROMPT, build_comment_summarizer_user_prompt
from planner.schemas import EventCommentGroup, EventCommentSummaryGroup, Intent, POICommentBundle, POICommentSummary


class JSONLLMClient(Protocol):
    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> dict[str, Any]:
        ...


def summarize_event_comment_groups(
    intent: Intent,
    comment_groups: list[EventCommentGroup],
    *,
    llm_client: JSONLLMClient,
    max_bundles_per_event: Optional[int] = 10,
    max_reviews: int = 8,
    max_tips: int = 6,
    max_chars_per_item: int = 280,
    progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
) -> list[EventCommentSummaryGroup]:
    event_map = {index: event for index, event in enumerate(intent.events, start=1)}
    total = sum(len(group.bundles[:max_bundles_per_event]) if max_bundles_per_event is not None else len(group.bundles) for group in comment_groups)
    completed = 0
    summary_groups: list[EventCommentSummaryGroup] = []
    for group in comment_groups:
        event = event_map[group.event_index]
        bundles = group.bundles[:max_bundles_per_event] if max_bundles_per_event is not None else group.bundles
        summaries = []
        for bundle in bundles:
            summaries.append(
                summarize_poi_comment_bundle(
                intent,
                event_index=group.event_index,
                bundle=bundle,
                llm_client=llm_client,
                max_reviews=max_reviews,
                max_tips=max_tips,
                max_chars_per_item=max_chars_per_item,
            )
            )
            completed += 1
            if progress_callback is not None:
                progress_callback(
                    {
                        "completed": completed,
                        "total": total,
                        "event_name": group.event_name,
                        "event_goal": group.event_goal,
                        "poi_name": bundle.name,
                    }
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


def summarize_poi_comment_bundle(
    intent: Intent,
    *,
    event_index: int,
    bundle: POICommentBundle,
    llm_client: JSONLLMClient,
    max_reviews: int = 8,
    max_tips: int = 6,
    max_chars_per_item: int = 280,
) -> POICommentSummary:
    event = intent.events[event_index - 1]
    packed_reviews = _pack_reviews(bundle, max_reviews=max_reviews, max_chars_per_item=max_chars_per_item)
    packed_tips = _pack_tips(bundle, max_tips=max_tips, max_chars_per_item=max_chars_per_item)
    started_at = perf_counter()
    payload = llm_client.generate_json(
        system_prompt=COMMENT_SUMMARIZER_SYSTEM_PROMPT,
        user_prompt=build_comment_summarizer_user_prompt(
            overall_intent={
                "raw_query": intent.raw_query,
                "city": intent.city,
                "overall_goal": intent.overall_goal,
                "start_time": intent.start_time,
                "end_time": intent.end_time,
                "return_location": intent.return_location,
                "hard_constraints": intent.hard_constraints,
                "soft_preferences": intent.soft_preferences,
            },
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


def _pack_reviews(bundle: POICommentBundle, *, max_reviews: int, max_chars_per_item: int) -> list[str]:
    packed: list[str] = []
    for review in bundle.reviews[:max_reviews]:
        text = _truncate(review.text, max_chars=max_chars_per_item)
        packed.append(f"stars={review.stars}; useful={review.useful}; date={review.date}; text={text}")
    return packed


def _pack_tips(bundle: POICommentBundle, *, max_tips: int, max_chars_per_item: int) -> list[str]:
    packed: list[str] = []
    for tip in bundle.tips[:max_tips]:
        text = _truncate(tip.text, max_chars=max_chars_per_item)
        packed.append(f"compliments={tip.compliment_count}; date={tip.date}; text={text}")
    return packed


def _truncate(text: str, *, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."
