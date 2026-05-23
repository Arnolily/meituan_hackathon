from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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
                "reviews": _pack_reviews(bundle, max_reviews=max_reviews, max_chars_per_item=max_chars_per_item),
                "tips": _pack_tips(bundle, max_tips=max_tips, max_chars_per_item=max_chars_per_item),
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
) -> POICommentSummary:
    event = intent.events[event_index - 1]
    packed_reviews = _pack_reviews(bundle, max_reviews=max_reviews, max_chars_per_item=max_chars_per_item)
    packed_tips = _pack_tips(bundle, max_tips=max_tips, max_chars_per_item=max_chars_per_item)
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
