/* eslint-disable @typescript-eslint/no-explicit-any */
import { MAP_CENTER, ZOOM_DEFAULT, ZOOM_MAX, ZOOM_MIN } from "../data/constants";
import {
  getBootstrapMapCenter,
  saveLastMapCenter,
  type MapLngLat,
} from "../utils/lastMapCenter";

const GOOGLE_MAPS_DEFAULT_URL = "https://maps.googleapis.com/maps/api/js";
const GOOGLE_MAPS_CALLBACK = "__ib__";
const GOOGLE_MAPS_PLACEHOLDER = "your_google_maps_api_key_here";
const GOOGLE_MAPS_LIBRARY_TIMEOUT = 12_000;

type GoogleMap = any;
type GoogleMapsApi = any;
type GoogleMapsLibrary = any;

const libraryPromises = new globalThis.Map<string, Promise<GoogleMapsLibrary>>();

interface LoadGoogleMapOptions {
  useSavedCenter?: boolean;
  signal?: AbortSignal;
}

function getGoogleMapsKey() {
  return import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
}

function getGoogleMapId() {
  const mapId = import.meta.env.VITE_GOOGLE_MAP_ID;
  return mapId && mapId !== "your_google_maps_map_id_here" ? mapId : undefined;
}

export function hasGoogleMapsKey() {
  const key = getGoogleMapsKey();
  return Boolean(key && key !== GOOGLE_MAPS_PLACEHOLDER);
}

export function parseGoogleMapsError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  if (message.includes("Google Maps auth failed")) {
    return "地图服务认证失败，请检查本地地图配置是否完整。";
  }
  if (message.includes("ApiNotActivatedMapError")) {
    return "地图服务还没有启用，请先打开对应的地图服务。";
  }
  if (message.includes("InvalidKeyMapError")) {
    return "地图服务配置无效，请检查本地地图密钥。";
  }
  if (message.includes("RefererNotAllowedMapError")) {
    return "当前本地地址还没有被地图服务允许访问。";
  }
  if (message.includes("BillingNotEnabledMapError")) {
    return "地图服务账号还不能使用实时地图。";
  }
  if (message.includes("timed out") || message.includes("failed to load")) {
    return "实时地图加载失败，请检查网络后重试。";
  }
  return message || "实时地图服务暂不可用，请稍后重试。";
}

export function toGoogleLatLng(center: MapLngLat) {
  return { lng: center[0], lat: center[1] };
}

export function fromGoogleLatLng(latLng: { lng: () => number; lat: () => number }): MapLngLat {
  return [latLng.lng(), latLng.lat()];
}

export async function loadGoogleMapsApi(): Promise<GoogleMapsApi> {
  if (window.google?.maps?.importLibrary) return window.google.maps;

  const key = getGoogleMapsKey();
  if (!key || key === GOOGLE_MAPS_PLACEHOLDER) {
    throw new Error("还没有配置实时地图");
  }

  if (window.__googleMapsApiPromise) return window.__googleMapsApiPromise;

  window.__googleMapsApiPromise = Promise.resolve().then(() => {
    const root = (window.google = window.google ?? {});
    const maps = (root.maps = root.maps ?? {});
    if (maps.importLibrary) return maps;

    const requestedLibraries = new Set<string>();
    const params = new URLSearchParams();
    let bootstrapPromise: Promise<void> | undefined;

    const loadScript = () => {
      if (bootstrapPromise) return bootstrapPromise;

      bootstrapPromise = new Promise<void>((resolve, reject) => {
        const script = document.createElement("script");
        params.set("libraries", [...requestedLibraries].join(","));
        params.set("key", key);
        params.set("v", "weekly");
        params.set("loading", "async");
        params.set("auth_referrer_policy", "origin");
        params.set("callback", `google.maps.${GOOGLE_MAPS_CALLBACK}`);
        script.src = `${GOOGLE_MAPS_DEFAULT_URL}?${params.toString()}`;
        script.async = true;
        script.defer = true;
        script.onerror = () => {
          window.__googleMapsApiPromise = undefined;
          reject(new Error("实时地图脚本加载失败"));
        };
        maps[GOOGLE_MAPS_CALLBACK] = resolve;
        document.head.appendChild(script);
      });

      return bootstrapPromise;
    };

    maps.importLibrary = (name: string, ...rest: unknown[]) => {
      requestedLibraries.add(name);
      return loadScript().then(() => maps.importLibrary(name, ...rest));
    };

    return maps;
  });

  return window.__googleMapsApiPromise;
}

export async function importGoogleMapsLibrary(name: string): Promise<GoogleMapsLibrary> {
  const maps = await loadGoogleMapsApi();
  if (typeof maps.importLibrary !== "function") {
    throw new Error("实时地图组件不可用");
  }

  const cached = libraryPromises.get(name);
  if (cached) return cached;

  const promise = withTimeout(maps.importLibrary(name), GOOGLE_MAPS_LIBRARY_TIMEOUT, "实时地图组件加载超时");
  libraryPromises.set(name, promise);
  return promise;
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let timeout: ReturnType<typeof setTimeout>;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeout = setTimeout(() => reject(new Error(message)), timeoutMs);
  });

  return Promise.race([promise, timeoutPromise]).finally(() => clearTimeout(timeout));
}

export async function resolveUserMapCenter(): Promise<MapLngLat | null> {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    return null;
  }

  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: MapLngLat | null) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };

    const watchdog = window.setTimeout(() => finish(null), 12_000);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        window.clearTimeout(watchdog);
        finish([pos.coords.longitude, pos.coords.latitude]);
      },
      () => {
        window.clearTimeout(watchdog);
        finish(null);
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 300_000 }
    );
  });
}

function getAddressPart(components: Array<{ long_name: string; types: string[] }>, type: string) {
  return components.find((component) => component.types.includes(type))?.long_name ?? "";
}

export async function resolveApproximateAreaLabel(center: MapLngLat): Promise<string | null> {
  const geocodingLibrary = await importGoogleMapsLibrary("geocoding");
  const Geocoder = geocodingLibrary?.Geocoder ?? window.google?.maps?.Geocoder;
  if (typeof Geocoder !== "function") return null;

  return new Promise((resolve) => {
    const geocoder = new Geocoder();
    geocoder.geocode({ location: toGoogleLatLng(center) }, (results: any[], status: string) => {
      if (status !== "OK" || !results?.[0]?.address_components) {
        resolve(null);
        return;
      }

      const components = results[0].address_components as Array<{ long_name: string; types: string[] }>;
      const city =
        getAddressPart(components, "locality") ||
        getAddressPart(components, "administrative_area_level_2") ||
        getAddressPart(components, "administrative_area_level_1");
      const district =
        getAddressPart(components, "sublocality_level_1") ||
        getAddressPart(components, "administrative_area_level_3");
      resolve(district ? `${city}${district}` : city || null);
    });
  });
}

function scheduleMapResize(map: GoogleMap) {
  const run = () => window.google?.maps?.event?.trigger(map, "resize");
  requestAnimationFrame(run);
  window.setTimeout(run, 80);
  window.setTimeout(run, 350);
}

function bindLastCenterPersistence(map: GoogleMap) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const persist = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      const center = map.getCenter?.();
      if (center) saveLastMapCenter(fromGoogleLatLng(center));
    }, 400);
  };
  map.addListener("idle", persist);
  map.addListener("zoom_changed", persist);
}

export async function loadGoogleMap(container: HTMLDivElement, options: LoadGoogleMapOptions = {}) {
  try {
    const maps = await loadGoogleMapsApi();
    if (options.signal?.aborted) {
      throw new DOMException("实时地图加载已取消", "AbortError");
    }

    const mapsLibrary = await importGoogleMapsLibrary("maps");
    if (options.signal?.aborted) {
      throw new DOMException("实时地图加载已取消", "AbortError");
    }

    const MapConstructor = mapsLibrary?.Map ?? maps.Map;
    if (typeof MapConstructor !== "function") {
      throw new Error("实时地图组件不可用");
    }

    const initialCenter = getBootstrapMapCenter({ useSavedCenter: options.useSavedCenter });
    const mapOptions: Record<string, unknown> = {
      center: toGoogleLatLng(initialCenter),
      zoom: ZOOM_DEFAULT,
      minZoom: ZOOM_MIN,
      maxZoom: ZOOM_MAX,
      disableDefaultUI: true,
      gestureHandling: "greedy",
      clickableIcons: false,
      backgroundColor: "#f5f7fb",
    };
    const mapId = getGoogleMapId();
    if (mapId) mapOptions.mapId = mapId;

    const map = new MapConstructor(container, mapOptions);
    bindLastCenterPersistence(map);
    scheduleMapResize(map);
    saveLastMapCenter(initialCenter);

    return { googleMaps: maps, map, initialCenter };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new Error(parseGoogleMapsError(error), { cause: error });
  }
}

export async function locateUserOnMap(map: GoogleMap): Promise<MapLngLat | null> {
  const center = await resolveUserMapCenter();
  if (!center) return null;

  saveLastMapCenter(center);
  map.setCenter(toGoogleLatLng(center));
  scheduleMapResize(map);
  return center;
}

export function disposeGoogleMap(map: GoogleMap, container: HTMLDivElement | null) {
  window.google?.maps?.event?.clearInstanceListeners(map);
  if (container) container.innerHTML = "";
}

export const DEFAULT_GOOGLE_CENTER = MAP_CENTER;
