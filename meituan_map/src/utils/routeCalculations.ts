import type { Poi, RoutePlan, RouteStatus } from "../types";

const WALKING_SPEED_KM_PER_HOUR = 4.8;
const ROUTE_DISTANCE_FACTOR = 1.22;
const MIN_SEGMENT_WALK_MINUTES = 4;

function toRadians(value: number) {
  return (value * Math.PI) / 180;
}

export function distanceKm(a: Poi, b: Poi) {
  const earthKm = 6371;
  const dLat = toRadians(b.lat - a.lat);
  const dLng = toRadians(b.lng - a.lng);
  const lat1 = toRadians(a.lat);
  const lat2 = toRadians(b.lat);
  const h =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  return 2 * earthKm * Math.asin(Math.sqrt(h));
}

export function walkingDistanceKm(a: Poi, b: Poi) {
  return distanceKm(a, b) * ROUTE_DISTANCE_FACTOR;
}

export function walkingMinutesBetween(a: Poi, b: Poi) {
  const minutes = (walkingDistanceKm(a, b) / WALKING_SPEED_KM_PER_HOUR) * 60;
  return Math.max(MIN_SEGMENT_WALK_MINUTES, Math.round(minutes));
}

export function minutesToClock(start: string, offsetMinutes: number) {
  const [hour, minute] = start.split(":").map(Number);
  const date = new Date(2026, 0, 1, hour, minute + offsetMinutes);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function getPoisForRoute(route: RoutePlan, pois: Poi[]) {
  const poiMap = new Map(pois.map((poi) => [poi.id, poi]));
  return route.poiIds.map((id) => poiMap.get(id)).filter((poi): poi is Poi => Boolean(poi));
}

export function calculateRouteStatus(totalDuration: number, targetHours: number): RouteStatus {
  const targetMinutes = targetHours * 60;
  if (totalDuration <= targetMinutes) return "可执行";
  if (totalDuration <= targetMinutes + 30) return "略紧张";
  return "不可执行";
}

export function recalculateRoute(route: RoutePlan, pois: Poi[], targetHours: number): RoutePlan {
  const routePois = getPoisForRoute(route, pois);
  const segmentWalkMinutes = routePois.map((poi, index) => {
    const previous = routePois[index - 1];
    return previous ? walkingMinutesBetween(previous, poi) : 0;
  });
  const travelMinutes = segmentWalkMinutes.reduce((sum, minutes) => sum + minutes, 0);
  const totalDuration = routePois.reduce((sum, poi) => sum + poi.stayTime, 0) + travelMinutes;
  const totalQueueTime = routePois.reduce((sum, poi) => sum + poi.queueTime, 0);
  const paidPois = routePois.filter((poi) => poi.avgPrice > 0);
  const avgCost = paidPois.length
    ? Math.round(paidPois.reduce((sum, poi) => sum + poi.avgPrice, 0) / paidPois.length)
    : 0;
  const measuredDistance = routePois.reduce((sum, poi, index) => {
    const next = routePois[index + 1];
    return next ? sum + walkingDistanceKm(poi, next) : sum;
  }, 0);
  const totalDistance = Math.round(Math.max(1.2, measuredDistance) * 10) / 10;

  let cursor = 0;
  const stops = routePois.map((poi, index) => {
    cursor += segmentWalkMinutes[index] ?? 0;
    const arriveTime = minutesToClock(route.timelineStart, cursor);
    cursor += poi.stayTime;
    return {
      poiId: poi.id,
      arriveTime,
      leaveTime: minutesToClock(route.timelineStart, cursor),
      walkMinutes: segmentWalkMinutes[index] ?? 0,
    };
  });

  return {
    ...route,
    label: route.name,
    tag:
      route.strategy === "efficiency"
        ? "少绕路"
        : route.strategy === "lowQueue"
          ? "低排队"
          : "体验优先",
    stops,
    totalMinutes: totalDuration,
    totalDuration,
    totalDistance,
    totalQueueTime,
    avgCost,
    status: calculateRouteStatus(totalDuration, targetHours),
    polyline: routePois.map((poi) => [poi.lng, poi.lat]),
  };
}

export function recalculateRoutes(routes: RoutePlan[], pois: Poi[], targetHours: number) {
  return routes.map((route) => recalculateRoute(route, pois, targetHours));
}
