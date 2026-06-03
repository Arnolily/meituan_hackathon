import { MAP_CENTER } from "../data/constants";

const STORAGE_KEY = "meituan_map_last_center";

export type MapLngLat = [number, number];

function isValidCenter(c: unknown): c is MapLngLat {
  if (!Array.isArray(c) || c.length !== 2) return false;
  const [lng, lat] = c;
  return (
    typeof lng === "number" &&
    typeof lat === "number" &&
    Number.isFinite(lng) &&
    Number.isFinite(lat) &&
    lng >= -180 &&
    lng <= 180 &&
    lat >= -90 &&
    lat <= 90
  );
}

/** 上次浏览/定位成功的地图中心，无记录时用默认城市 */
export function loadLastMapCenter(): MapLngLat | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    return isValidCenter(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveLastMapCenter(center: MapLngLat) {
  if (typeof localStorage === "undefined" || !isValidCenter(center)) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(center));
  } catch {
    /* quota / private mode */
  }
}

/** 首屏默认使用产品默认城市；只有用户主动使用当前位置时才允许读取上次中心。 */
export function getBootstrapMapCenter(options: { useSavedCenter?: boolean } = {}): MapLngLat {
  return options.useSavedCenter ? loadLastMapCenter() ?? MAP_CENTER : MAP_CENTER;
}
