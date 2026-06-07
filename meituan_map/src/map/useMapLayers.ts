/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useRef } from "react";
import { toGoogleLatLng } from "./loadGoogleMap";
import { useAppStore } from "../store/appStore";
import type { Poi, RoutePlan } from "../types";

type AnyMap = any;

const TYPE_ICON: Record<string, string> = {
  餐饮: "食",
  娱乐: "玩",
  商场: "购",
  公园: "园",
  文化: "文",
};

function markerHtml(poi: Poi, index: number | null, active: boolean, selected: boolean) {
  const commentClass = poi.commentParsed ? "demo-marker--commented" : "demo-marker--uncommented";
  return `
    <button class="demo-marker ${commentClass} ${active ? "demo-marker--active" : "demo-marker--muted"} ${selected ? "demo-marker--selected" : ""}" type="button">
      <span>${index ?? TYPE_ICON[poi.type]}</span>
      <strong>${poi.name}</strong>
    </button>
  `;
}

function routePois(route: RoutePlan, pois: Poi[]) {
  const poiMap = new Map(pois.map((poi) => [poi.id, poi]));
  return route.poiIds.map((id) => poiMap.get(id)).filter((poi): poi is Poi => Boolean(poi));
}

async function roadPathFromRoute(route: RoutePlan, pois: Poi[], maps: AnyMap): Promise<[number, number][]> {
  if (route.geometrySource === "openrouteservice" && route.polyline.length >= 2) {
    return route.polyline;
  }

  const stops = routePois(route, pois);
  if (stops.length < 2 || typeof maps.DirectionsService !== "function") return [];

  const origin = stops[0];
  const destination = stops[stops.length - 1];
  const waypoints = stops.slice(1, -1).map((poi) => ({
    location: { lat: poi.lat, lng: poi.lng },
    stopover: true,
  }));

  return new Promise((resolve) => {
    const service = new maps.DirectionsService();
    service.route(
      {
        origin: { lat: origin.lat, lng: origin.lng },
        destination: { lat: destination.lat, lng: destination.lng },
        waypoints,
        optimizeWaypoints: false,
        travelMode: maps.TravelMode.WALKING,
      },
      (result: AnyMap, status: string) => {
        if (status !== "OK" || !result?.routes?.[0]?.overview_path) {
          resolve([]);
          return;
        }
        resolve(
          result.routes[0].overview_path.map(
            (point: AnyMap) => [point.lng(), point.lat()] as [number, number]
          )
        );
      }
    );
  });
}

function createHtmlOverlay(
  map: AnyMap,
  position: [number, number],
  html: string,
  options: { zIndex?: number; anchor?: "bottom" | "center"; onClick?: (event: MouseEvent) => void } = {}
) {
  const maps = window.google?.maps;
  if (!maps) return null;

  const overlay = new maps.OverlayView();
  let element: HTMLDivElement | null = null;

  overlay.onAdd = () => {
    element = document.createElement("div");
    element.className = `google-html-marker google-html-marker--${options.anchor ?? "bottom"}`;
    element.style.zIndex = String(options.zIndex ?? 1);
    element.innerHTML = html;
    if (options.onClick) {
      element.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        options.onClick?.(event);
      });
    }
    overlay.getPanes()?.overlayMouseTarget.appendChild(element);
  };

  overlay.draw = () => {
    if (!element) return;
    const projection = overlay.getProjection();
    if (!projection) return;
    const point = projection.fromLatLngToDivPixel(new maps.LatLng(position[1], position[0]));
    if (!point) return;
    element.style.left = `${point.x}px`;
    element.style.top = `${point.y}px`;
  };

  overlay.onRemove = () => {
    element?.remove();
    element = null;
  };

  overlay.setMap(map);
  return overlay;
}

export function useMapLayers() {
  const map = useAppStore((s) => s.mapInstance) as AnyMap | null;
  const generationStage = useAppStore((s) => s.generationStage);
  const pois = useAppStore((s) => s.pois);
  const routes = useAppStore((s) => s.routes);
  const activeRouteId = useAppStore((s) => s.activeRouteId);
  const selectedPoiId = useAppStore((s) => s.selectedPoiId);
  const markersRef = useRef<AnyMap[]>([]);
  const linesRef = useRef<AnyMap[]>([]);
  const locMarkerRef = useRef<AnyMap | null>(null);

  useEffect(() => {
    if (document.getElementById("demo-map-layer-styles")) return;
    const style = document.createElement("style");
    style.id = "demo-map-layer-styles";
    style.textContent = `
      .google-html-marker {
        position: absolute;
        will-change: left, top;
        pointer-events: auto;
      }
      .google-html-marker--bottom {
        transform: translate(-50%, -100%);
      }
      .google-html-marker--center {
        transform: translate(-50%, -50%);
      }
      .demo-marker {
        display: flex;
        align-items: center;
        gap: 6px;
        border: 0;
        border-radius: 999px;
        padding: 6px 10px 6px 6px;
        background: rgba(255,255,255,0.72);
        color: #1d1d1f;
        box-shadow: 0 4px 16px rgba(0,0,0,0.14);
        font: 600 12px -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
        white-space: nowrap;
      }
      .demo-marker span {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        background: #86868b;
        color: #fff;
        font-size: 12px;
      }
      .demo-marker--commented {
        background: rgba(0,113,227,0.2);
        border: 1px solid rgba(0,113,227,0.34);
        color: #0a3d74;
      }
      .demo-marker--commented span {
        background: rgba(0,113,227,0.72);
      }
      .demo-marker--uncommented {
        background: rgba(255,255,255,0.62);
        border: 1px solid rgba(142,142,147,0.34);
        color: #3a3a3c;
      }
      .demo-marker--muted {
        opacity: 0.72;
        transform: scale(0.92);
      }
      .demo-marker--muted span {
        background: #86868b;
      }
      .demo-marker--active {
        opacity: 1;
        transform: scale(1);
        background: #0071e3;
        color: #fff;
        border: 1px solid rgba(255,255,255,0.82);
        box-shadow: 0 8px 24px rgba(0,113,227,0.34);
      }
      .demo-marker--active span {
        background: #fff;
        color: #0071e3;
      }
      .demo-marker--selected {
        opacity: 1;
        transform: scale(1);
        outline: 3px solid rgba(0,113,227,0.3);
      }
      .loc-pulse {
        position: relative;
        width: 22px;
        height: 22px;
      }
      .loc-pulse__dot {
        position: absolute;
        inset: 6px;
        border-radius: 50%;
        background: #0071e3;
        z-index: 1;
        box-shadow: 0 0 0 3px #fff;
      }
      .loc-pulse__ring {
        position: absolute;
        inset: 0;
        border-radius: 50%;
        background: rgba(0,113,227,0.2);
        animation: locPulse 1.6s ease-out infinite;
      }
      @keyframes locPulse {
        from { transform: scale(0.65); opacity: 1; }
        to { transform: scale(1.8); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
  }, []);

  useEffect(() => {
    if (!map || !window.google?.maps) return;
    markersRef.current.forEach((marker) => marker.setMap(null));
    markersRef.current = [];

    const activeRoute = routes.find((route) => route.id === activeRouteId);
    const activeIds = new Set(activeRoute?.poiIds ?? []);
    const shouldShowCandidates =
      generationStage === "poi_filtering" ||
      generationStage === "route_comparing" ||
      generationStage === "route_generating" ||
      generationStage === "route_ready";
    const visiblePois = shouldShowCandidates ? pois : [];

    visiblePois.forEach((poi) => {
      const index = activeRoute?.poiIds.indexOf(poi.id);
      const isActive = activeIds.has(poi.id);
      const marker = createHtmlOverlay(
        map,
        [poi.lng, poi.lat],
        markerHtml(poi, index != null && index >= 0 ? index + 1 : null, isActive, selectedPoiId === poi.id),
        {
          zIndex: isActive ? 30 : 12,
          anchor: "bottom",
          onClick: () => useAppStore.getState().setSelectedPoi(poi.id),
        }
      );
      if (marker) markersRef.current.push(marker);
    });

    return () => {
      markersRef.current.forEach((marker) => marker.setMap(null));
      markersRef.current = [];
    };
  }, [map, generationStage, pois, routes, activeRouteId, selectedPoiId]);

  useEffect(() => {
    const maps = window.google?.maps;
    if (!map || !maps) return;
    linesRef.current.forEach((line) => line.setMap(null));
    linesRef.current = [];
    const shouldShowRoutes =
      generationStage === "poi_filtering" ||
      generationStage === "route_comparing" ||
      generationStage === "route_generating" ||
      generationStage === "route_ready";
    if (!shouldShowRoutes) return;

    const bounds = new maps.LatLngBounds();
    let hasBounds = false;

    const activeRoute = routes.find((route) => route.id === activeRouteId) ?? routes[0];
    const visibleRoutes = generationStage === "route_comparing" ? routes : activeRoute ? [activeRoute] : routes.slice(0, 1);
    let cancelled = false;

    void Promise.all(
      visibleRoutes.map(async (route) => ({
        route,
        path: await roadPathFromRoute(route, pois, maps),
      }))
    ).then((resolvedRoutes) => {
      if (cancelled) return;
      resolvedRoutes.forEach(({ route, path }) => {
        if (path.length < 2) return;
        const active = route.id === activeRouteId;
        const googlePath = path.map(toGoogleLatLng);
        googlePath.forEach((point) => {
          bounds.extend(point);
          hasBounds = true;
        });

        const dashed = generationStage === "route_comparing" || !active;
        const line = new maps.Polyline({
          path: googlePath,
          geodesic: false,
          strokeColor: active ? "#0071e3" : "#8e8e93",
          strokeWeight: active ? 6 : 3,
          strokeOpacity: dashed ? 0 : active ? 0.92 : 0.32,
          zIndex: active ? 18 : 8,
          icons: dashed
            ? [
                {
                  icon: {
                    path: "M 0,-1 0,1",
                    strokeOpacity: active ? 0.82 : 0.34,
                    strokeColor: active ? "#0071e3" : "#8e8e93",
                    scale: active ? 4 : 3,
                  },
                  offset: "0",
                  repeat: "16px",
                },
              ]
            : undefined,
        });
        line.setMap(map);
        linesRef.current.push(line);
      });

      if (generationStage === "route_ready" && hasBounds) {
        window.setTimeout(() => {
          if (!cancelled) map.fitBounds(bounds, { top: 90, right: 460, bottom: 120, left: 360 });
        }, 80);
      }
    });

    return () => {
      cancelled = true;
      linesRef.current.forEach((line) => line.setMap(null));
      linesRef.current = [];
    };
  }, [map, generationStage, routes, pois, activeRouteId]);

  const setLocationMarker = (lng: number, lat: number) => {
    if (!map || !window.google?.maps) return;
    if (locMarkerRef.current) locMarkerRef.current.setMap(null);
    locMarkerRef.current = createHtmlOverlay(
      map,
      [lng, lat],
      `<div class="loc-pulse"><span class="loc-pulse__dot"></span><span class="loc-pulse__ring"></span></div>`,
      { anchor: "center", zIndex: 40 }
    );
  };

  return { setLocationMarker };
}
