from planner import api
from planner.llm.client import _collect_stream_content
from planner.modules import poi_loader
from planner.modules import ors_client
from planner.schemas import RouteCandidate, RouteLeg, RouteStop


def test_route_stream_emits_partial_before_enriched_result(monkeypatch) -> None:
    monkeypatch.setattr(api, "generate_fast_route_plan", lambda payload: {"routes": [{"id": "fast"}], "pois": []})
    monkeypatch.setattr(api, "generate_route_plan", lambda payload, **_options: {"routes": [{"id": "final"}], "pois": []})

    events = list(api.generate_route_plan_stream({"query": "coffee"}))

    assert [event["type"] for event in events] == [
        "analysis",
        "stage",
        "partial_result",
        "analysis",
        "stage",
        "result",
        "analysis",
        "complete",
    ]
    assert events[2]["data"]["routes"][0]["id"] == "fast"
    assert events[5]["data"]["routes"][0]["id"] == "final"
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert len({event["requestId"] for event in events}) == 1


def test_route_stream_keeps_fast_result_when_enrichment_fails(monkeypatch) -> None:
    monkeypatch.setattr(api, "generate_fast_route_plan", lambda payload: {"routes": [{"id": "fast"}], "pois": []})

    def fail_enrichment(payload, **_options):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(api, "generate_route_plan", fail_enrichment)

    events = list(api.generate_route_plan_stream({"query": "coffee"}))

    assert [event["type"] for event in events] == [
        "analysis",
        "stage",
        "partial_result",
        "analysis",
        "stage",
        "warning",
        "complete",
    ]
    assert events[5]["recoverable"] is True


def test_fast_route_plan_disables_slow_enrichment(monkeypatch) -> None:
    captured = {}

    def fake_generate(payload, **options):
        captured.update(options)
        return {"routes": [], "pois": []}

    monkeypatch.setattr(api, "_generate_route_plan", fake_generate)

    api.generate_fast_route_plan({"query": "coffee"})

    assert captured["include_comment_summaries"] is False
    assert captured["use_live_directions"] is False
    assert captured["max_candidates"] == 6


def test_approximate_direction_client_does_not_emit_straight_line_geometry() -> None:
    client = api.ApproximateDirectionClient()
    stops = [
        RouteStop(kind="poi", name="A", latitude=39.9, longitude=-75.1),
        RouteStop(kind="poi", name="B", latitude=40.0, longitude=-75.2),
    ]

    legs = client.route(stops=stops, mode="walking")

    assert legs[0].provider == "approximate"
    assert legs[0].polyline == []


def test_frontend_routes_do_not_fallback_to_straight_poi_connections() -> None:
    route = RouteCandidate(
        route_id="route-1",
        mode="walking",
        stops=[
            RouteStop(kind="poi", name="A", latitude=39.9, longitude=-75.1, business_id="a"),
            RouteStop(kind="poi", name="B", latitude=40.0, longitude=-75.2, business_id="b"),
        ],
        legs=[
            RouteLeg(
                origin_name="A",
                destination_name="B",
                mode="walking",
                provider="openrouteservice",
                provider_status="failed",
            )
        ],
    )
    pois = [
        {"id": "a", "lng": -75.1, "lat": 39.9, "queueTime": 0, "avgPrice": 0, "stayTime": 45},
        {"id": "b", "lng": -75.2, "lat": 40.0, "queueTime": 0, "avgPrice": 0, "stayTime": 45},
    ]

    routes = api._frontend_routes([route], pois, duration_hours=4)

    assert routes[0]["polyline"] == []
    assert routes[0]["geometrySource"] == "unavailable"


def test_business_records_are_cached_by_file_version(tmp_path) -> None:
    business_file = tmp_path / "business.json"
    business_file.write_text('{"business_id":"b1","name":"Cafe","city":"Philadelphia","state":"PA","latitude":1,"longitude":2}\n')
    poi_loader._load_business_records.cache_clear()

    first = poi_loader._business_records(business_file)
    second = poi_loader._business_records(business_file)

    assert first is second
    assert poi_loader._load_business_records.cache_info().misses == 1
    assert poi_loader._load_business_records.cache_info().hits == 1


def test_collect_stream_content_joins_model_chunks() -> None:
    class Delta:
        def __init__(self, content):
            self.content = content

    class Choice:
        def __init__(self, content):
            self.delta = Delta(content)

    class Chunk:
        def __init__(self, content):
            self.choices = [Choice(content)]

    assert _collect_stream_content([Chunk('{"ok":'), Chunk("true"), Chunk("}")]) == '{"ok":true}'


def test_ors_routes_all_stops_in_one_request(monkeypatch) -> None:
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return (
                b'{"features":[{"properties":{"segments":['
                b'{"distance":100,"duration":60},{"distance":200,"duration":120}'
                b']},"geometry":{"coordinates":[[-75.1,39.9],[-75.2,40.0],[-75.3,40.1]]}}]}'
            )

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr(ors_client, "urlopen", fake_urlopen)
    client = ors_client.OpenRouteServiceDirectionClient(api_key="test", timeout=8)
    stops = [
        RouteStop(kind="anchor", name="A", latitude=39.9, longitude=-75.1),
        RouteStop(kind="poi", name="B", latitude=40.0, longitude=-75.2),
        RouteStop(kind="poi", name="C", latitude=40.1, longitude=-75.3),
    ]

    legs = client.route(stops=stops, mode="walking")

    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.method == "POST"
    assert b'"coordinates"' in request.data
    assert timeout == 8
    assert [leg.duration_seconds for leg in legs] == [60.0, 120.0]


def test_route_stream_times_out_enrichment_and_keeps_fast_result(monkeypatch) -> None:
    monkeypatch.setattr(api, "generate_fast_route_plan", lambda payload: {"routes": [{"id": "fast"}], "pois": []})
    monkeypatch.setattr(api, "ENRICHMENT_DEADLINE_SECONDS", 0.01)

    def slow_enrichment(payload, **_options):
        import time

        time.sleep(0.05)
        return {"routes": [{"id": "final"}], "pois": []}

    monkeypatch.setattr(api, "generate_route_plan", slow_enrichment)

    events = list(api.generate_route_plan_stream({"query": "coffee"}))

    assert any(event["type"] == "warning" and "快速路线" in event["message"] for event in events)
    assert events[-1]["type"] == "complete"
    assert events[-1]["progress"] == 100
    assert not any(event["progress"] == 90 for event in events)
