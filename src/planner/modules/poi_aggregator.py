from __future__ import annotations

from planner.schemas import AggregatedPOI, EventAggregatedPOIGroup, EventCommentSummaryGroup, EventPOIGroup, POICommentSummary, RawPOI


def aggregate_event_poi_groups(
    poi_groups: list[EventPOIGroup],
    summary_groups: list[EventCommentSummaryGroup],
) -> list[EventAggregatedPOIGroup]:
    summaries_by_event = {
        group.event_index: {summary.business_id: summary for summary in group.summaries}
        for group in summary_groups
    }

    aggregated_groups: list[EventAggregatedPOIGroup] = []
    for group in poi_groups:
        summary_map = summaries_by_event.get(group.event_index, {})
        aggregated_pois = [_aggregate_poi(poi, summary_map.get(poi.business_id)) for poi in group.pois]
        aggregated_pois.sort(
            key=lambda poi: (
                -poi.aggregate_score,
                -poi.retrieval_score,
                -poi.review_count,
                poi.name,
            )
        )
        aggregated_groups.append(
            EventAggregatedPOIGroup(
                event_index=group.event_index,
                event_name=group.event_name,
                event_goal=group.event_goal,
                pois=aggregated_pois,
            )
        )
    return aggregated_groups


def _aggregate_poi(poi: RawPOI, summary: POICommentSummary | None) -> AggregatedPOI:
    score, breakdown = _score_aggregated_poi(poi, summary)
    summary_available = summary is not None
    return AggregatedPOI(
        **poi.model_dump(),
        comment_summary_available=summary_available,
        comment_summary=summary.summary if summary_available else None,
        comment_keywords=list(summary.keywords) if summary_available else [],
        comment_pros=list(summary.pros) if summary_available else [],
        comment_cons=list(summary.cons) if summary_available else [],
        comment_notable_risks=list(summary.notable_risks) if summary_available else [],
        comment_evidence=list(summary.evidence) if summary_available else [],
        comment_confidence=summary.confidence if summary_available else 0.0,
        aggregate_score=score,
        aggregate_breakdown=breakdown,
    )


def _score_aggregated_poi(poi: RawPOI, summary: POICommentSummary | None) -> tuple[float, dict[str, float]]:
    retrieval = poi.retrieval_score
    quality = min(max(poi.stars, 0.0), 5.0) * 0.25 + min(max(poi.review_count, 0), 1000) / 1000.0
    breakdown = {
        "retrieval_score": retrieval,
        "quality_signal": quality,
    }

    if summary is None:
        breakdown["missing_comment_summary_penalty"] = -0.5
    else:
        confidence = summary.confidence
        positive = min(len(summary.pros), 4) * 0.25 + min(len(summary.keywords), 6) * 0.05
        negative = min(len(summary.cons), 4) * -0.2 + min(len(summary.notable_risks), 4) * -0.35
        breakdown.update(
            {
                "comment_confidence": confidence,
                "positive_comment_signal": positive,
                "negative_comment_signal": negative,
            }
        )

    score = round(sum(breakdown.values()), 3)
    rounded_breakdown = {key: round(value, 3) for key, value in breakdown.items()}
    return score, rounded_breakdown
