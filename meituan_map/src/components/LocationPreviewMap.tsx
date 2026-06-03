import { useEffect, useRef, useState } from "react";
import { DEFAULT_LOCATION_LABEL, MAP_CENTER } from "../data/constants";
import {
  disposeGoogleMap,
  hasGoogleMapsKey,
  importGoogleMapsLibrary,
  loadGoogleMapsApi,
  parseGoogleMapsError,
  resolveApproximateAreaLabel,
  resolveUserMapCenter,
  toGoogleLatLng,
} from "../map/loadGoogleMap";
import { useAppStore } from "../store/appStore";
import type { StartPointMode } from "../types";
import { getBootstrapMapCenter, saveLastMapCenter } from "../utils/lastMapCenter";

interface LocationPreviewMapProps {
  startPointMode: StartPointMode;
  manualStartName: string;
  onApproximateAreaChange?: (area: string | null) => void;
}

export function LocationPreviewMap({
  startPointMode,
  manualStartName,
  onApproximateAreaChange,
}: LocationPreviewMapProps) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const setUserMapCenter = useAppStore((s) => s.setUserMapCenter);
  const showToast = useAppStore((s) => s.showToast);
  const hasMapKey = hasGoogleMapsKey();
  const [status, setStatus] = useState(hasMapKey ? DEFAULT_LOCATION_LABEL : "预览不可用");
  const [error, setError] = useState<string | null>(hasMapKey ? null : "还没有配置实时地图");
  const [mapReady, setMapReady] = useState(false);
  const [mapSlow, setMapSlow] = useState(false);
  const renderableChecksRef = useRef(0);

  useEffect(() => {
    const container = mapRef.current;
    if (!container || !hasMapKey) return;

    let cancelled = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let map: any = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let marker: any = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let tilesListener: any = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let idleListener: any = null;
    let renderCheckTimer: ReturnType<typeof setInterval> | null = null;
    const startedAt = window.performance.now();
    const slowTimer = window.setTimeout(() => {
      if (!cancelled) setMapSlow(true);
    }, 2200);

    const useCurrentLocation = startPointMode === "currentLocation";
    renderableChecksRef.current = 0;
    setMapReady(false);
    setMapSlow(false);
    setError(null);

    const syncApproximateArea = async (center: [number, number]) => {
      const area = await resolveApproximateAreaLabel(center);
      if (!cancelled) {
        onApproximateAreaChange?.(area);
      }
    };

    loadGoogleMapsApi()
      .then(async (maps) => {
        if (cancelled) return;

        const [mapsLibrary, markerLibrary] = await Promise.all([
          importGoogleMapsLibrary("maps"),
          importGoogleMapsLibrary("marker").catch(() => ({})),
        ]);
        if (cancelled) return;

        const MapConstructor = mapsLibrary?.Map ?? maps.Map;
        const MarkerConstructor = markerLibrary?.Marker ?? maps.Marker;
        if (typeof MapConstructor !== "function") {
          throw new Error("实时地图组件不可用");
        }

        const initialCenter = getBootstrapMapCenter();
        setUserMapCenter(initialCenter);
        setStatus(useCurrentLocation ? "定位中" : DEFAULT_LOCATION_LABEL);

        map = new MapConstructor(container, {
          center: toGoogleLatLng(initialCenter),
          zoom: 15.4,
          disableDefaultUI: true,
          gestureHandling: "none",
          clickableIcons: false,
          backgroundColor: "#eef4fb",
        });

        if (typeof MarkerConstructor === "function") {
          marker = new MarkerConstructor({
            position: toGoogleLatLng(initialCenter),
            map,
            icon: maps.SymbolPath?.CIRCLE
              ? {
                  path: maps.SymbolPath.CIRCLE,
                  scale: 10,
                  fillColor: "#0071e3",
                  fillOpacity: 1,
                  strokeColor: "#ffffff",
                  strokeWeight: 4,
                }
              : undefined,
          });
        }

        const revealMapWhenRenderable = () => {
          if (cancelled) return;
          const minimumFallbackTimePassed = window.performance.now() - startedAt > 900;
          const renderable = minimumFallbackTimePassed && hasRenderableGoogleMap(container);
          renderableChecksRef.current = renderable ? renderableChecksRef.current + 1 : 0;

          if (renderableChecksRef.current < 2) {
            setMapSlow(true);
            return;
          }

          window.clearTimeout(slowTimer);
          if (renderCheckTimer) window.clearInterval(renderCheckTimer);
          setMapReady(true);
          setMapSlow(false);
        };

        tilesListener = map.addListener("tilesloaded", revealMapWhenRenderable);
        idleListener = map.addListener("idle", revealMapWhenRenderable);
        renderCheckTimer = window.setInterval(revealMapWhenRenderable, 500);
        window.setTimeout(revealMapWhenRenderable, 120);
        window.setTimeout(revealMapWhenRenderable, 800);

        window.google?.maps?.event?.trigger(map, "resize");
        await syncApproximateArea(initialCenter);

        if (!useCurrentLocation) return;

        const gpsCenter = await resolveUserMapCenter();
        if (cancelled) return;

        if (gpsCenter) {
          marker?.setPosition?.(toGoogleLatLng(gpsCenter));
          map.setCenter(toGoogleLatLng(gpsCenter));
          saveLastMapCenter(gpsCenter);
          setUserMapCenter(gpsCenter);
          setStatus("GPS 已定位");
          await syncApproximateArea(gpsCenter);
        } else {
          marker?.setPosition?.(toGoogleLatLng(MAP_CENTER));
          map.setCenter(toGoogleLatLng(MAP_CENTER));
          setUserMapCenter(MAP_CENTER);
          setStatus(DEFAULT_LOCATION_LABEL);
          onApproximateAreaChange?.(DEFAULT_LOCATION_LABEL);
          showToast(`定位未开启，已保留 ${DEFAULT_LOCATION_LABEL} 默认位置`);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        window.clearTimeout(slowTimer);
        setMapReady(false);
        setMapSlow(false);
        setStatus("预览不可用");
        setError(parseGoogleMapsError(err));
      });

    return () => {
      cancelled = true;
      window.clearTimeout(slowTimer);
      if (renderCheckTimer) window.clearInterval(renderCheckTimer);
      tilesListener?.remove?.();
      idleListener?.remove?.();
      if (marker) {
        marker.setMap?.(null);
        marker = null;
      }
      if (map) {
        disposeGoogleMap(map, container);
        map = null;
      }
    };
  }, [hasMapKey, onApproximateAreaChange, setUserMapCenter, showToast, startPointMode]);

  const modeLabel =
    startPointMode === "manual"
      ? manualStartName.trim()
        ? "手动起点"
        : "等待输入"
      : status;

  return (
    <div className="intent-location-card__map" aria-hidden="true">
      <div ref={mapRef} className="intent-location-card__map-canvas" />
      <div className={`intent-location-card__preview${mapReady ? " is-hidden" : ""}`}>
        <div className="intent-location-card__preview-grid" />
        <div className="intent-location-card__preview-road intent-location-card__preview-road--blue" />
        <div className="intent-location-card__preview-road intent-location-card__preview-road--gold" />
        <div className="intent-location-card__preview-marker">
          <span />
        </div>
        <small>{mapSlow ? "正在连接实时地图" : "费城位置预览"}</small>
      </div>
      {error ? (
        <div className="intent-location-card__map-fallback">
          <strong>地图预览暂不可用</strong>
          <span>{error}</span>
        </div>
      ) : null}
      <span className="intent-location-card__map-status">{modeLabel}</span>
    </div>
  );
}

function hasRenderableGoogleMap(container: HTMLDivElement) {
  const rect = container.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return false;

  const googleMapRoot = container.querySelector(".gm-style");
  if (!googleMapRoot) return false;

  const tileImages = Array.from(googleMapRoot.querySelectorAll<HTMLImageElement>("img[src]")).filter((image) => {
    const src = image.currentSrc || image.src;
    if (!src) return false;
    const rect = image.getBoundingClientRect();
    if (rect.width < 32 || rect.height < 32) return false;
    return /googleapis\.com|gstatic\.com|google\.com/.test(src) && !/transparent|poweredby|google4|logo|watermark/i.test(src);
  });

  return tileImages.length >= 2;
}
