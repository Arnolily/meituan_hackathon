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
from planner.io.poi_cache import save_cached_pois
from planner.llm.client import OpenAICompatibleClient
from planner.modules.comment_loader import load_comment_bundles, load_pois_json
from planner.modules.intent_parser import parse_intent
from planner.modules.poi_loader import load_candidate_pois
from planner.schemas import AnchorPoint, Intent, SpatialConstraint
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
        "target_area": intent.target_area,
        "goals": intent.goals,
        "categories": intent.categories,
        "poi_types": intent.poi_types,
        "budget_level": intent.budget_level,
        "end_time": intent.end_time,
        "return_location": intent.return_location,
        "hard_constraints": intent.hard_constraints,
        "soft_preferences": intent.soft_preferences,
        "confidence": intent.confidence,
    }


def build_poi_table(pois: list[dict]) -> pd.DataFrame:
    rows = []
    for poi in pois:
        rows.append(
            {
                "name": poi.get("name"),
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
                "name": bundle.get("name"),
                "city": bundle.get("city"),
                "reviews_loaded": bundle.get("review_count_loaded", 0),
                "tips_loaded": bundle.get("tip_count_loaded", 0),
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
    latest_pois = load_latest_pois(cache_dir)
    latest_comments = load_latest_comments(cache_dir)

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

        intent_clicked = st.button("Parse Intent", use_container_width=True)
        poi_clicked = st.button("Load POIs", use_container_width=True)
        comments_clicked = st.button("Load Comments", use_container_width=True)

    if intent_clicked:
        api_key = env_settings.get("OPENAI_API_KEY")
        base_url = env_settings.get("OPENAI_BASE_URL")
        model = env_settings.get("OPENAI_MODEL")
        if not api_key or not model:
            st.error("Missing OPENAI_API_KEY or OPENAI_MODEL in .env.local.")
        else:
            llm_client = OpenAICompatibleClient(api_key=api_key, base_url=base_url, model=model)
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
            pois = load_candidate_pois(
                latest_intent,
                business_file=business_file,
                max_pois=int(max_pois),
                spatial_constraint=spatial_constraint,
            )
            save_latest_spatial_context(cache_dir, spatial_constraint)
            save_cached_pois(
                pois,
                cache_dir=cache_dir,
                intent=latest_intent,
                business_file=business_file,
                max_pois=int(max_pois),
            )
            latest_pois = [poi.model_dump() for poi in pois]
            st.success(f"Loaded and cached {len(latest_pois)} POIs.")

    if comments_clicked:
        if not latest_pois:
            latest_pois = load_latest_pois(cache_dir)
        if not latest_pois:
            st.error("No cached POIs found. Load POIs first.")
        else:
            pois = load_pois_json(latest_pois)
            review_file, tip_file = resolve_comment_files(pois, None, None)
            bundles = load_comment_bundles(
                pois,
                review_file=review_file,
                tip_file=tip_file,
                max_reviews_per_poi=int(max_reviews_per_poi),
                max_tips_per_poi=int(max_tips_per_poi),
            )
            save_cached_comments(
                bundles,
                cache_dir=cache_dir,
                pois=pois,
                review_file=review_file,
                tip_file=tip_file,
                max_reviews_per_poi=int(max_reviews_per_poi),
                max_tips_per_poi=int(max_tips_per_poi),
            )
            latest_comments = [bundle.model_dump() for bundle in bundles]
            st.success(f"Loaded and cached comments for {len(latest_comments)} POIs.")

    left, right = st.columns([1, 2])

    with left:
        st.subheader("Latest Intent")
        if latest_intent is None:
            st.info("No cached intent yet.")
        else:
            st.json(intent_summary(latest_intent))

    with right:
        st.subheader("Latest POIs")
        if not latest_pois:
            st.info("No cached POIs yet.")
        else:
            poi_df = build_poi_table(latest_pois)
            st.dataframe(poi_df, use_container_width=True, hide_index=True)

    st.subheader("Latest Comments")
    if latest_comments:
        comment_df = build_comment_table(latest_comments)
        st.dataframe(comment_df, use_container_width=True, hide_index=True)
    else:
        st.info("No cached comments yet.")

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
        labels = [poi["name"] for poi in latest_pois]
        selected_name = st.selectbox("Select POI", labels)
        selected = next(poi for poi in latest_pois if poi["name"] == selected_name)
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
