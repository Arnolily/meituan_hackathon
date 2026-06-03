import type { RouteHistoryItem, RoutePlan, TravelIntent } from "../types";

const ROUTE_HISTORY_STORAGE_KEY = "meituan_map_route_history";
const MAX_HISTORY_ITEMS = 8;

function cloneRoute(route: RoutePlan): RoutePlan {
  return {
    ...route,
    poiIds: [...route.poiIds],
    stops: route.stops.map((stop) => ({ ...stop })),
    polyline: route.polyline.map((point) => [...point] as [number, number]),
    preferenceTags: route.preferenceTags ? [...route.preferenceTags] : undefined,
    preferenceReason: route.preferenceReason,
  };
}

export function loadRouteHistory(): RouteHistoryItem[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(ROUTE_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const items = JSON.parse(raw) as RouteHistoryItem[];
    return Array.isArray(items) ? items.slice(0, MAX_HISTORY_ITEMS) : [];
  } catch {
    return [];
  }
}

export function saveRouteHistory(items: RouteHistoryItem[]) {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(ROUTE_HISTORY_STORAGE_KEY, JSON.stringify(items.slice(0, MAX_HISTORY_ITEMS)));
  } catch {
    /* ignore private mode/quota */
  }
}

export function createRouteHistoryItem(route: RoutePlan, intent: TravelIntent | null): RouteHistoryItem {
  return {
    id: `history-${Date.now()}-${route.id}`,
    createdAt: new Date().toISOString(),
    route: cloneRoute(route),
    intent: intent ? { ...intent, preferences: [...intent.preferences], poiTypes: [...intent.poiTypes] } : null,
  };
}

export function prependRouteHistory(item: RouteHistoryItem, currentItems: RouteHistoryItem[]) {
  const deduped = currentItems.filter((existing) => existing.route.id !== item.route.id || existing.route.name !== item.route.name);
  return [item, ...deduped].slice(0, MAX_HISTORY_ITEMS);
}
