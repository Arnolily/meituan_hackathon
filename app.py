from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st
from pydantic import ValidationError

from planner.config import DEFAULT_CACHE_DIR, load_env_file
from planner.io.intent_cache import load_intent_json, save_cached_intent
from planner.io.comment_cache import save_cached_comments
from planner.io.comment_summary_cache import save_cached_comment_summaries
from planner.io.poi_cache import save_cached_pois
from planner.llm.client import OpenAICompatibleClient
from planner.modules.comment_loader import load_event_comment_groups, load_poi_groups_json
from planner.modules.comment_summarizer import summarize_event_comment_groups
from planner.modules.intent_parser import parse_intent
from planner.modules.poi_loader import load_candidate_poi_groups
from planner.schemas import AnchorPoint, EventCommentGroup, Intent, SpatialConstraint
from scripts.load_comments import resolve_comment_files
from scripts.load_pois import resolve_business_file


st.set_page_config(page_title="Meituan Planner Debug UI", layout="wide")


def read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_intent(cache_dir: Path) -> Intent | None:
    path = cache_dir / "intents" / "latest_intent.json"
    if not path.exists():
        return None
    raw_json = path.read_text(encoding="utf-8")
    try:
        intent = load_intent_json(raw_json)
    except ValidationError:
        return None
    if intent.model_dump_json(indent=2) != raw_json:
        path.write_text(intent.model_dump_json(indent=2), encoding="utf-8")
    return intent


def load_latest_pois(cache_dir: Path) -> list[dict]:
    path = cache_dir / "pois" / "latest_pois.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_comments(cache_dir: Path) -> list[dict]:
    path = cache_dir / "comments" / "latest_comments.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_comment_summaries(cache_dir: Path) -> list[dict]:
    path = cache_dir / "comment_summaries" / "latest_comment_summaries.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_spatial_context(cache_dir: Path) -> dict | None:
    path = cache_dir / "pois" / "latest_spatial_constraint.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_latest_spatial_context(cache_dir: Path, spatial_constraint: SpatialConstraint | None) -> None:
    path = cache_dir / "pois" / "latest_spatial_constraint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = spatial_constraint.model_dump() if spatial_constraint is not None else None
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def intent_summary(intent: Intent) -> dict:
    return {
        "raw_query": intent.raw_query,
        "city": intent.city,
        "overall_goal": intent.overall_goal,
        "end_time": intent.end_time,
        "return_location": intent.return_location,
        "hard_constraints": intent.hard_constraints,
        "soft_preferences": intent.soft_preferences,
        "events": [event.model_dump() for event in intent.events],
        "confidence": intent.confidence,
    }


def flatten_pois(poi_groups: list[dict]) -> list[dict]:
    if poi_groups and "business_id" in poi_groups[0]:
        return poi_groups
    rows: list[dict] = []
    for group in poi_groups:
        event_name = group.get("event_name")
        event_goal = group.get("event_goal")
        for poi in group.get("pois", []):
            row = dict(poi)
            row["event_name"] = event_name
            row["event_goal"] = event_goal
            rows.append(row)
    return rows


def flatten_comment_bundles(comment_groups: list[dict]) -> list[dict]:
    if comment_groups and "business_id" in comment_groups[0]:
        return comment_groups
    rows: list[dict] = []
    for group in comment_groups:
        event_name = group.get("event_name")
        event_goal = group.get("event_goal")
        for bundle in group.get("bundles", []):
            row = dict(bundle)
            row["event_name"] = event_name
            row["event_goal"] = event_goal
            rows.append(row)
    return rows


def flatten_comment_summaries(summary_groups: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for group in summary_groups:
        event_name = group.get("event_name")
        event_goal = group.get("event_goal")
        for summary in group.get("summaries", []):
            row = dict(summary)
            row["event_name"] = event_name
            row["event_goal"] = event_goal
            rows.append(row)
    return rows


def build_poi_table(pois: list[dict]) -> pd.DataFrame:
    rows = []
    for poi in pois:
        rows.append(
            {
                "event": poi.get("event_name") or poi.get("event_goal"),
                "name": poi.get("name"),
                "score": poi.get("retrieval_score"),
                "city": poi.get("city"),
                "categories": ", ".join(poi.get("categories", [])[:4]),
                "stars": poi.get("stars"),
                "review_count": poi.get("review_count"),
                "price_level": poi.get("price_level"),
                "distance_km": poi.get("distance_to_anchor_km"),
                "travel_min": poi.get("estimated_travel_minutes"),
            }
        )
    return pd.DataFrame(rows)


def build_comment_table(comment_bundles: list[dict]) -> pd.DataFrame:
    rows = []
    for bundle in comment_bundles:
        rows.append(
            {
                "event": bundle.get("event_name") or bundle.get("event_goal"),
                "name": bundle.get("name"),
                "city": bundle.get("city"),
                "reviews_loaded": bundle.get("review_count_loaded", 0),
                "tips_loaded": bundle.get("tip_count_loaded", 0),
            }
        )
    return pd.DataFrame(rows)


def build_comment_summary_table(summaries: list[dict]) -> pd.DataFrame:
    rows = []
    for summary in summaries:
        rows.append(
            {
                "event": summary.get("event_name") or summary.get("event_goal"),
                "name": summary.get("name"),
                "inference_sec": summary.get("inference_seconds"),
                "keywords": ", ".join(summary.get("keywords", [])[:6]),
                "pros": len(summary.get("pros", [])),
                "cons": len(summary.get("cons", [])),
                "risks": len(summary.get("notable_risks", [])),
                "confidence": summary.get("confidence"),
            }
        )
    return pd.DataFrame(rows)


def build_map_dataframe(pois: list[dict], anchor: dict | None) -> pd.DataFrame:
    rows = []
    for poi in pois:
        rows.append(
            {
                "lat": poi["latitude"],
                "lon": poi["longitude"],
                "label": poi["name"],
                "kind": "poi",
            }
        )
    if anchor is not None:
        rows.append(
            {
                "lat": anchor["latitude"],
                "lon": anchor["longitude"],
                "label": anchor.get("name", "anchor"),
                "kind": "anchor",
            }
        )
    return pd.DataFrame(rows)


def build_map_chart(pois: list[dict], anchor: dict | None) -> pdk.Deck:
    poi_rows = [
        {
            "lat": poi["latitude"],
            "lon": poi["longitude"],
            "label": poi["name"],
        }
        for poi in pois
    ]
    poi_df = pd.DataFrame(poi_rows)

    layers: list[pdk.Layer] = [
        pdk.Layer(
            "ScatterplotLayer",
            data=poi_df,
            get_position="[lon, lat]",
            get_fill_color=[220, 53, 69, 180],
            get_radius=80,
            pickable=True,
        )
    ]

    view_lat = float(poi_df["lat"].mean())
    view_lon = float(poi_df["lon"].mean())

    if anchor is not None:
        anchor_df = pd.DataFrame(
            [
                {
                    "lat": anchor["latitude"],
                    "lon": anchor["longitude"],
                    "label": anchor.get("name", "Current Location"),
                }
            ]
        )
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=anchor_df,
                get_position="[lon, lat]",
                get_fill_color=[0, 123, 255, 220],
                get_line_color=[255, 255, 255, 255],
                line_width_min_pixels=2,
                stroked=True,
                get_radius=150,
                pickable=True,
            )
        )
        layers.append(
            pdk.Layer(
                "TextLayer",
                data=anchor_df,
                get_position="[lon, lat]",
                get_text="label",
                get_color=[0, 123, 255, 255],
                get_size=14,
                get_alignment_baseline="'top'",
                get_pixel_offset=[0, 18],
            )
        )
        view_lat = float(anchor_df["lat"].mean())
        view_lon = float(anchor_df["lon"].mean())

    tooltip = {
        "html": "<b>{label}</b>",
        "style": {"backgroundColor": "rgba(30, 30, 30, 0.9)", "color": "white"},
    }

    return pdk.Deck(
        map_provider=None,
        map_style=None,
        initial_view_state=pdk.ViewState(latitude=view_lat, longitude=view_lon, zoom=13, pitch=0),
        layers=layers,
        tooltip=tooltip,
    )


def main() -> None:
    cache_dir = DEFAULT_CACHE_DIR
    env_settings = load_env_file()
    latest_spatial_context = load_latest_spatial_context(cache_dir)

    st.title("Meituan Planner Debug UI")

    latest_intent = load_latest_intent(cache_dir)
    latest_poi_groups = load_latest_pois(cache_dir)
    latest_pois = flatten_pois(latest_poi_groups)
    latest_comment_groups = load_latest_comments(cache_dir)
    latest_comments = flatten_comment_bundles(latest_comment_groups)
    latest_summary_groups = load_latest_comment_summaries(cache_dir)
    latest_summaries = flatten_comment_summaries(latest_summary_groups)

    with st.sidebar:
        st.header("Run Pipeline")
        query = st.text_area(
            "Query",
            value=(latest_intent.raw_query if latest_intent is not None else "cheap dinner with good view before 8pm"),
            height=120,
        )
        default_city = st.text_input("Default city", value=(latest_intent.city or "") if latest_intent else "")
        refresh_intent_cache = st.checkbox("Refresh intent cache", value=False)
        st.divider()
        max_pois = st.number_input("Max POIs", min_value=1, max_value=500, value=50, step=1)
        saved_anchor = (latest_spatial_context or {}).get("anchor") or {}
        anchor_lat = st.text_input("Anchor latitude", value=str(saved_anchor.get("latitude", "")) if saved_anchor else "")
        anchor_lng = st.text_input("Anchor longitude", value=str(saved_anchor.get("longitude", "")) if saved_anchor else "")
        anchor_name = st.text_input("Anchor name", value=saved_anchor.get("name", "Current Location") if saved_anchor else "Current Location")
        max_radius_km = st.text_input(
            "Max radius km",
            value="" if latest_spatial_context is None or latest_spatial_context.get("max_radius_km") is None else str(latest_spatial_context["max_radius_km"]),
        )
        max_travel_min = st.text_input(
            "Max travel min",
            value="" if latest_spatial_context is None or latest_spatial_context.get("max_travel_min") is None else str(latest_spatial_context["max_travel_min"]),
        )
        mode_options = ["walking", "driving", "transit"]
        saved_mode = (latest_spatial_context or {}).get("mode", "walking")
        mode = st.selectbox("Mode", mode_options, index=mode_options.index(saved_mode) if saved_mode in mode_options else 0)
        st.divider()
        max_reviews_per_poi = st.number_input("Max reviews / POI", min_value=1, max_value=100, value=20, step=1)
        max_tips_per_poi = st.number_input("Max tips / POI", min_value=1, max_value=100, value=10, step=1)
        max_summaries_per_event = st.number_input("Max summaries / event", min_value=1, max_value=100, value=10, step=1)

        intent_clicked = st.button("Parse Intent", use_container_width=True)
        poi_clicked = st.button("Load POIs", use_container_width=True)
        comments_clicked = st.button("Load Comments", use_container_width=True)
        summarize_comments_clicked = st.button("Summarize Comments", use_container_width=True)

    if intent_clicked:
        api_key = env_settings.get("OPENAI_API_KEY")
        base_url = env_settings.get("OPENAI_BASE_URL")
        model = env_settings.get("OPENAI_MODEL")
        if not api_key or not model:
            st.error("Missing OPENAI_API_KEY or OPENAI_MODEL in .env.local.")
        else:
            timeout = float(env_settings.get("OPENAI_TIMEOUT_SEC", "60"))
            llm_client = OpenAICompatibleClient(api_key=api_key, base_url=base_url, model=model, timeout=timeout)
            intent = parse_intent(query, default_city=(default_city or None), llm_client=llm_client)
            save_cached_intent(
                intent,
                cache_dir=cache_dir,
                query=query,
                default_city=(default_city or None),
                model=model,
                base_url=base_url,
            )
            latest_intent = intent
            st.success("Intent parsed and cached.")

    if poi_clicked:
        latest_intent = load_latest_intent(cache_dir)
        if latest_intent is None:
            st.error("No cached intent found. Parse intent first.")
        else:
            business_file = resolve_business_file(latest_intent)
            spatial_constraint = build_spatial_constraint(
                anchor_lat=anchor_lat,
                anchor_lng=anchor_lng,
                anchor_name=anchor_name,
                max_radius_km=max_radius_km,
                max_travel_min=max_travel_min,
                mode=mode,
            )
            poi_groups = load_candidate_poi_groups(
                latest_intent,
                business_file=business_file,
                max_pois=int(max_pois),
                spatial_constraint=spatial_constraint,
            )
            save_latest_spatial_context(cache_dir, spatial_constraint)
            save_cached_pois(
                poi_groups,
                cache_dir=cache_dir,
                intent=latest_intent,
                business_file=business_file,
                max_pois=int(max_pois),
            )
            latest_poi_groups = [group.model_dump() for group in poi_groups]
            latest_pois = flatten_pois(latest_poi_groups)
            st.success(f"Loaded and cached {len(latest_pois)} POIs across {len(latest_poi_groups)} events.")

    if comments_clicked:
        if not latest_poi_groups:
            latest_poi_groups = load_latest_pois(cache_dir)
            latest_pois = flatten_pois(latest_poi_groups)
        if not latest_poi_groups:
            st.error("No cached POIs found. Load POIs first.")
        else:
            poi_groups = load_poi_groups_json(latest_poi_groups)
            review_file, tip_file = resolve_comment_files(poi_groups, None, None)
            comment_groups = load_event_comment_groups(
                poi_groups,
                review_file=review_file,
                tip_file=tip_file,
                max_reviews_per_poi=int(max_reviews_per_poi),
                max_tips_per_poi=int(max_tips_per_poi),
            )
            save_cached_comments(
                comment_groups,
                cache_dir=cache_dir,
                poi_groups=poi_groups,
                review_file=review_file,
                tip_file=tip_file,
                max_reviews_per_poi=int(max_reviews_per_poi),
                max_tips_per_poi=int(max_tips_per_poi),
            )
            latest_comment_groups = [group.model_dump() for group in comment_groups]
            latest_comments = flatten_comment_bundles(latest_comment_groups)
            st.success(f"Loaded and cached comments for {len(latest_comments)} POIs across {len(latest_comment_groups)} events.")

    if summarize_comments_clicked:
        api_key = env_settings.get("OPENAI_API_KEY")
        base_url = env_settings.get("OPENAI_BASE_URL")
        model = env_settings.get("OPENAI_MODEL")
        if not api_key or not model:
            st.error("Missing OPENAI_API_KEY or OPENAI_MODEL in .env.local.")
        else:
            timeout = float(env_settings.get("OPENAI_TIMEOUT_SEC", "60"))
            latest_intent = load_latest_intent(cache_dir)
            if latest_intent is None:
                st.error("No cached intent found. Parse intent first.")
            else:
                if not latest_comment_groups:
                    latest_comment_groups = load_latest_comments(cache_dir)
                    latest_comments = flatten_comment_bundles(latest_comment_groups)
                if not latest_comment_groups:
                    st.error("No cached comments found. Load comments first.")
                else:
                    client = OpenAICompatibleClient(api_key=api_key, base_url=base_url, model=model, timeout=timeout)
                    comment_groups = [EventCommentGroup.model_validate(item) for item in latest_comment_groups]
                    planned_count = sum(min(len(group.bundles), int(max_summaries_per_event)) for group in comment_groups)
                    progress_bar = st.progress(0.0, text=f"Summarizing 0/{planned_count} POIs")

                    def on_progress(update: dict) -> None:
                        total = max(int(update["total"]), 1)
                        completed = int(update["completed"])
                        progress_bar.progress(
                            completed / total,
                            text=f'Summarizing {completed}/{total}: {update["event_name"]} -> {update["poi_name"]}',
                        )

                    summary_groups = summarize_event_comment_groups(
                        latest_intent,
                        comment_groups,
                        llm_client=client,
                        max_bundles_per_event=int(max_summaries_per_event),
                        progress_callback=on_progress,
                    )
                    progress_bar.progress(1.0, text=f"Summarized {planned_count}/{planned_count} POIs")
                    save_cached_comment_summaries(
                        summary_groups,
                        cache_dir=cache_dir,
                        intent=latest_intent,
                        comment_groups=comment_groups,
                        model=model,
                        base_url=base_url,
                    )
                    latest_summary_groups = [group.model_dump() for group in summary_groups]
                    latest_summaries = flatten_comment_summaries(latest_summary_groups)
                    st.success(f"Summarized comments for {len(latest_summaries)} POIs across {len(latest_summary_groups)} events.")

    left, right = st.columns([1, 2])

    with left:
        st.subheader("Latest Intent")
        if latest_intent is None:
            st.info("No cached intent yet.")
        else:
            st.json(intent_summary(latest_intent))
            st.caption("Event Breakdown")
            for index, event in enumerate(latest_intent.events, start=1):
                with st.expander(f"Event {index}: {event.name or event.goal}", expanded=(index == 1)):
                    st.json(event.model_dump())

    with right:
        st.subheader("Latest POIs")
        if not latest_pois:
            st.info("No cached POIs yet.")
        else:
            poi_df = build_poi_table(latest_pois)
            poi_df = poi_df.sort_values(by=["event", "score"], ascending=[True, False], kind="stable")
            st.dataframe(poi_df, use_container_width=True, hide_index=True)

    st.subheader("Latest Comments")
    if latest_comments:
        comment_df = build_comment_table(latest_comments)
        st.dataframe(comment_df, use_container_width=True, hide_index=True)
    else:
        st.info("No cached comments yet.")

    st.subheader("Comment Summaries")
    if latest_summaries:
        summary_df = build_comment_summary_table(latest_summaries)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    else:
        st.info("No cached comment summaries yet.")

    st.subheader("Map")
    if latest_pois:
        anchor = None
        if anchor_lat and anchor_lng:
            anchor = {
                "latitude": float(anchor_lat),
                "longitude": float(anchor_lng),
                "name": anchor_name or "Current Location",
            }
        elif latest_spatial_context and latest_spatial_context.get("anchor"):
            anchor = latest_spatial_context["anchor"]
        map_chart = build_map_chart(latest_pois, anchor)
        st.pydeck_chart(map_chart, use_container_width=True)
    else:
        st.info("Run POI loading to render the map.")

    st.subheader("POI Detail")
    if latest_pois:
        labels = [f'{poi.get("event_name") or poi.get("event_goal")} | {poi["name"]} | score={poi.get("retrieval_score", 0)}' for poi in latest_pois]
        selected_label = st.selectbox("Select POI", labels)
        selected_index = labels.index(selected_label)
        selected = latest_pois[selected_index]
        st.metric("Retrieval Score", selected.get("retrieval_score", 0.0))
        breakdown = selected.get("retrieval_breakdown") or {}
        if breakdown:
            breakdown_df = pd.DataFrame(
                [{"component": component, "delta": delta} for component, delta in breakdown.items()]
            ).sort_values(by="delta", ascending=False, kind="stable")
            st.caption("Score Breakdown")
            st.dataframe(breakdown_df, use_container_width=True, hide_index=True)
        trace = selected.get("retrieval_trace") or []
        if trace:
            with st.expander("Detailed Score Trace", expanded=False):
                trace_df = pd.DataFrame(trace)
                st.dataframe(trace_df, use_container_width=True, hide_index=True)
        st.json(selected)
    else:
        st.info("No POI details available yet.")

    st.subheader("Comment Detail")
    if latest_comments:
        comment_labels = [bundle["name"] for bundle in latest_comments]
        selected_comment_name = st.selectbox("Select POI Comments", comment_labels)
        selected_bundle = next(bundle for bundle in latest_comments if bundle["name"] == selected_comment_name)
        st.json(selected_bundle)
    else:
        st.info("No comment details available yet.")

    st.subheader("Comment Summary Detail")
    if latest_summaries:
        summary_labels = [
            f'{summary.get("event_name") or summary.get("event_goal")} | {summary["name"]} | {summary.get("inference_seconds", "?")}s'
            for summary in latest_summaries
        ]
        selected_summary_label = st.selectbox("Select POI Summary", summary_labels)
        selected_summary = latest_summaries[summary_labels.index(selected_summary_label)]
        if selected_summary.get("inference_seconds") is not None:
            st.metric("Inference Time (sec)", selected_summary.get("inference_seconds"))
        st.json(selected_summary)
    else:
        st.info("No comment summary details available yet.")


def build_spatial_constraint(
    *,
    anchor_lat: str,
    anchor_lng: str,
    anchor_name: str,
    max_radius_km: str,
    max_travel_min: str,
    mode: str,
) -> SpatialConstraint | None:
    if not anchor_lat and not anchor_lng:
        return None
    if not anchor_lat or not anchor_lng:
        raise ValueError("Both anchor latitude and longitude are required.")
    return SpatialConstraint(
        anchor=AnchorPoint(name=anchor_name or "anchor", latitude=float(anchor_lat), longitude=float(anchor_lng)),
        max_radius_km=float(max_radius_km) if max_radius_km else None,
        max_travel_min=float(max_travel_min) if max_travel_min else None,
        mode=mode,
    )


if __name__ == "__main__":
    main()
