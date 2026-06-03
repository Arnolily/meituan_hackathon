import { useEffect, useRef, useState } from "react";
import { DEFAULT_LOCATION_LABEL } from "../data/constants";
import { disposeGoogleMap, loadGoogleMap, locateUserOnMap } from "./loadGoogleMap";
import { useMapLayers } from "./useMapLayers";
import { useAppStore } from "../store/appStore";
import { useGeolocation } from "../hooks/useGeolocation";
import type { Poi, RoutePlan } from "../types";

export function MapContainer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const setMapInstance = useAppStore((s) => s.setMapInstance);
  const setMapReady = useAppStore((s) => s.setMapReady);
  const setMapError = useAppStore((s) => s.setMapError);
  const setUserMapCenter = useAppStore((s) => s.setUserMapCenter);
  const showToast = useAppStore((s) => s.showToast);
  const mapError = useAppStore((s) => s.mapError);
  const travelIntent = useAppStore((s) => s.travelIntent);
  const pois = useAppStore((s) => s.pois);
  const routes = useAppStore((s) => s.routes);
  const activeRouteId = useAppStore((s) => s.activeRouteId);
  const shouldUseCurrentLocation = travelIntent?.startPointMode === "currentLocation";
  const { setLocationMarker } = useMapLayers();
  const [retryNonce, setRetryNonce] = useState(0);
  const [mapVisualReady, setMapVisualReady] = useState(false);
  const [mapLoadSlow, setMapLoadSlow] = useState(false);
  const renderableChecksRef = useRef(0);
  const activeLoadIdRef = useRef(0);

  useGeolocation(setLocationMarker);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let cancelled = false;
    const loadId = activeLoadIdRef.current + 1;
    activeLoadIdRef.current = loadId;
    const abortController = new AbortController();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let map: any = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let tilesListener: any = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let idleListener: any = null;
    let renderCheckTimer: ReturnType<typeof setInterval> | null = null;
    const startedAt = window.performance.now();
    const slowTimer = window.setTimeout(() => {
      if (!cancelled) setMapLoadSlow(true);
    }, 2600);

    renderableChecksRef.current = 0;
    setMapReady(false);
    setMapError(null);
    setMapVisualReady(false);
    setMapLoadSlow(false);

    loadGoogleMap(el, { signal: abortController.signal })
      .then(async ({ map: googleMap, initialCenter }) => {
        if (cancelled || activeLoadIdRef.current !== loadId) {
          window.google?.maps?.event?.clearInstanceListeners(googleMap);
          return;
        }

        map = googleMap;
        setMapInstance(googleMap);
        setUserMapCenter(initialCenter);
        setMapReady(true);
        setMapError(null);

        const revealMapWhenRenderable = () => {
          if (cancelled) return;
          const minimumFallbackTimePassed = window.performance.now() - startedAt > 1200;
          const renderable = minimumFallbackTimePassed && hasRenderableGoogleMap(el);
          renderableChecksRef.current = renderable ? renderableChecksRef.current + 1 : 0;

          if (renderableChecksRef.current < 2) {
            setMapLoadSlow(true);
            return;
          }

          window.clearTimeout(slowTimer);
          if (renderCheckTimer) window.clearInterval(renderCheckTimer);
          setMapVisualReady(true);
          setMapLoadSlow(false);
        };

        tilesListener = googleMap.addListener("tilesloaded", revealMapWhenRenderable);
        idleListener = googleMap.addListener("idle", revealMapWhenRenderable);
        renderCheckTimer = window.setInterval(revealMapWhenRenderable, 500);
        window.setTimeout(revealMapWhenRenderable, 120);
        window.setTimeout(revealMapWhenRenderable, 800);

        googleMap.addListener("click", () => {
          useAppStore.getState().setDetailPoi(null);
        });

        if (!shouldUseCurrentLocation) return;

        const gpsCenter = await locateUserOnMap(googleMap);
        if (cancelled) return;

        if (gpsCenter) {
          setUserMapCenter(gpsCenter);
        } else {
          showToast(`定位未开启，已保留 ${DEFAULT_LOCATION_LABEL} 默认位置`);
        }
      })
      .catch((err: Error) => {
        window.clearTimeout(slowTimer);
        setMapVisualReady(false);
        setMapLoadSlow(false);
        if (!cancelled && err.name !== "AbortError") setMapError(err.message || "Google 地图服务暂不可用，请刷新重试");
      });

    const onResize = () => window.google?.maps?.event?.trigger(map, "resize");
    window.addEventListener("resize", onResize);

    return () => {
      cancelled = true;
      abortController.abort();
      window.clearTimeout(slowTimer);
      if (renderCheckTimer) window.clearInterval(renderCheckTimer);
      window.removeEventListener("resize", onResize);
      tilesListener?.remove?.();
      idleListener?.remove?.();
      if (map && activeLoadIdRef.current === loadId) {
        disposeGoogleMap(map, el);
        map = null;
      }
    };
  }, [setMapInstance, setMapReady, setMapError, setUserMapCenter, showToast, shouldUseCurrentLocation, retryNonce]);

  const handleRetry = () => {
    setMapError(null);
    setMapVisualReady(false);
    setMapLoadSlow(false);
    setRetryNonce((value) => value + 1);
  };

  return (
    <>
      <div id="map-root" ref={containerRef} />
      {!mapVisualReady ? <CachedMapFallback slow={mapLoadSlow} pois={pois} routes={routes} activeRouteId={activeRouteId} /> : null}
      {mapError ? (
        <div className="map-error">
          <div className="map-error__card">
            <h2>实时地图未连接</h2>
            <p className="map-error__msg">{mapError}</p>
            <ul className="map-error__tips">
              <li>当前已切换到缓存演示地图，演示流程可以继续。</li>
              <li>稍后可重试连接实时地图。</li>
            </ul>
            <div className="map-error__actions">
              <button className="btn-primary" type="button" onClick={handleRetry}>
                重试实时地图
              </button>
            </div>
            <p className="map-error__hint">如果持续失败，请检查本地地图服务配置和网络访问。</p>
          </div>
        </div>
      ) : null}
    </>
  );
}

function CachedMapFallback({
  slow,
  pois,
  routes,
  activeRouteId,
}: {
  slow: boolean;
  pois: Poi[];
  routes: RoutePlan[];
  activeRouteId: string | null;
}) {
  const activeRoute = routes.find((route) => route.id === activeRouteId) ?? routes[0];
  const visiblePois = activeRoute
    ? activeRoute.poiIds.map((id) => pois.find((poi) => poi.id === id)).filter((poi): poi is Poi => Boolean(poi))
    : pois.slice(0, 5);
  const routePoints = visiblePois.map((poi) => projectPoi(poi));
  const routePolyline = routePoints.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <div className="map-loading-preview" aria-live="polite">
      <div className="map-loading-preview__grid" />
      <div className="map-loading-preview__river" />
      <div className="map-loading-preview__district map-loading-preview__district--park" />
      <div className="map-loading-preview__district map-loading-preview__district--city" />
      <div className="map-loading-preview__district map-loading-preview__district--museum" />
      <div className="map-loading-preview__district map-loading-preview__district--riverwalk" />
      {routePoints.length > 1 ? (
        <svg className="map-loading-preview__route" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <polyline points={routePolyline} />
        </svg>
      ) : null}
      {visiblePois.length > 0 ? (
        visiblePois.map((poi, index) => {
          const point = projectPoi(poi);
          return (
            <div
              key={poi.id}
              className="map-loading-preview__poi"
              style={{ left: `${point.x}%`, top: `${point.y}%` }}
              title={poi.name}
            >
              <span>{index + 1}</span>
              <strong>{poi.name}</strong>
            </div>
          );
        })
      ) : (
        <div className="map-loading-preview__marker">
          <span />
        </div>
      )}
      <div className="map-loading-preview__card">
        <strong>费城缓存地图</strong>
        <span>{slow ? "实时地图连接较慢，正在使用缓存演示底图" : "正在准备实时地图，先展示缓存地图"}</span>
      </div>
    </div>
  );
}

function projectPoi(poi: Poi) {
  const minLng = -75.186;
  const maxLng = -75.135;
  const minLat = 39.942;
  const maxLat = 39.968;
  const x = 12 + ((poi.lng - minLng) / (maxLng - minLng)) * 76;
  const y = 82 - ((poi.lat - minLat) / (maxLat - minLat)) * 64;
  return {
    x: Math.max(10, Math.min(90, x)),
    y: Math.max(16, Math.min(86, y)),
  };
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
    if (rect.width < 64 || rect.height < 64) return false;
    return /googleapis\.com|gstatic\.com|google\.com/.test(src) && !/transparent|poweredby|google4|logo|watermark/i.test(src);
  });

  return tileImages.length >= 4;
}
