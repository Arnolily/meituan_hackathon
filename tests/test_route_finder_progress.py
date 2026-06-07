from planner.modules.route_finder import find_route_candidates
from planner.schemas import AggregatedPOI, EventAggregatedPOIGroup, Intent


class DirectionClient:
    def route(self, *, stops, mode):
        return []


def test_route_candidates_report_completion_progress() -> None:
    groups = [
        EventAggregatedPOIGroup(
            event_index=1,
            event_name="coffee",
            event_goal="coffee",
            pois=[
                AggregatedPOI(
                    business_id=f"poi-{index}",
                    name=f"POI {index}",
                    city="Philadelphia",
                    state="PA",
                    latitude=39.9 + index * 0.01,
                    longitude=-75.1,
                    stars=4.5,
                    review_count=100,
                    is_open=True,
                    aggregate_score=5 - index,
                )
                for index in range(3)
            ],
        )
    ]
    completed = []

    routes = find_route_candidates(
        intent=Intent(raw_query="coffee", events=[{"goal": "coffee"}]),
        aggregated_groups=groups,
        direction_client=DirectionClient(),
        max_candidates=3,
        progress_callback=lambda done, total: completed.append((done, total)),
    )

    assert len(routes) == 3
    assert completed == [(1, 3), (2, 3), (3, 3)]
