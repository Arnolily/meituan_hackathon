import type { Poi, RoutePlan, TravelIntent } from "../types";
import type { RoutePlanningPreferences } from "../types/routePreferences";
import { getPoisForRoute } from "./routeCalculations";

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function averageRating(routePois: Poi[]) {
  if (routePois.length === 0) return 0;
  return routePois.reduce((sum, poi) => sum + poi.rating, 0) / routePois.length;
}

function typeRatio(routePois: Poi[], types: Poi["type"][]) {
  if (routePois.length === 0) return 0;
  const count = routePois.filter((poi) => types.includes(poi.type)).length;
  return count / routePois.length;
}

function formatScoreTag(score: number) {
  if (score >= 88) return "高度匹配";
  if (score >= 78) return "较匹配";
  return "可参考";
}

function buildPreferenceReason(
  preferences: RoutePlanningPreferences,
  intentPreferences: string[],
  route: RoutePlan,
  routePois: Poi[],
  maxWalkMinutes: number
) {
  const reasons: string[] = [];

  if (preferences.transport === "walk" && route.totalDistance <= 1.8) {
    reasons.push("更贴合少走路和步行友好的偏好");
  } else if (preferences.transport === "transit" && route.totalDistance > 1.5) {
    reasons.push("更适合搭配地铁和公共交通衔接");
  }

  if (preferences.foodVsPlay <= 35) {
    const foodCount = routePois.filter((poi) => poi.type === "餐饮").length;
    if (foodCount > 0) reasons.push("餐饮停留占比更高");
  } else if (preferences.foodVsPlay >= 65) {
    const playCount = routePois.filter((poi) => poi.type !== "餐饮").length;
    if (playCount >= 2) reasons.push("更偏向逛玩和体验型停留");
  } else {
    reasons.push("吃和逛的节奏更平衡");
  }

  if (maxWalkMinutes <= preferences.walkMinutes) {
    reasons.push(`单段步行控制在你偏好的 ${preferences.walkMinutes} 分钟内`);
  }

  if (preferences.avoidTransfers && route.poiIds.length <= 4) {
    reasons.push("路线更集中，后续换乘压力更低");
  }

  if (preferences.pace === "relaxed" && route.status === "可执行") {
    reasons.push("整体节奏更轻松");
  } else if (preferences.pace === "tight" && route.totalDuration <= 240) {
    reasons.push("整体更紧凑，适合高效率出行");
  }

  if (intentPreferences.includes("少排队") && route.totalQueueTime <= 15) {
    reasons.push("排队时间更短");
  }

  if (intentPreferences.includes("高评分")) {
    const highRatingCount = routePois.filter((poi) => poi.rating >= 4.6).length;
    if (highRatingCount > 0) reasons.push("高评分地点更多");
  }

  return reasons.slice(0, 3).join("，") || "整体更贴近你的长期偏好和这次的路线目标";
}

export function personalizeRoutes(
  routes: RoutePlan[],
  pois: Poi[],
  preferences: RoutePlanningPreferences,
  intent: TravelIntent | null
) {
  const intentPreferences = intent?.preferences ?? [];
  const annotated = routes.map((route, index) => {
    const routePois = getPoisForRoute(route, pois);
    const maxWalkMinutes = Math.max(0, ...route.stops.map((stop) => stop.walkMinutes));
    const foodRatio = typeRatio(routePois, ["餐饮"]);
    const experienceRatio = typeRatio(routePois, ["公园", "文化", "娱乐"]);
    const mallRatio = typeRatio(routePois, ["商场"]);
    let score = 68;
    const tags = new Set<string>();

    if (preferences.transport === "walk") {
      score += clamp(16 - route.totalDistance * 4, -8, 12);
      tags.add("步行友好");
    } else if (preferences.transport === "transit") {
      score += route.totalDistance > 1.8 ? 5 : 0;
      tags.add("可接驳");
    } else {
      score += route.status === "可执行" ? 6 : 2;
    }

    if (preferences.foodVsPlay <= 35) {
      score += foodRatio * 12;
      tags.add("餐饮优先");
    } else if (preferences.foodVsPlay >= 65) {
      score += experienceRatio * 12;
      tags.add("体验更足");
    } else {
      score += foodRatio > 0 && experienceRatio > 0 ? 8 : 0;
      tags.add("吃逛平衡");
    }

    if (maxWalkMinutes > preferences.walkMinutes) {
      score -= clamp((maxWalkMinutes - preferences.walkMinutes) * 0.8, 0, 12);
    } else {
      score += 7;
      tags.add("步行可控");
    }

    if (preferences.avoidTransfers) {
      score += route.poiIds.length <= 4 ? 4 : -3;
      tags.add("少换乘");
    }

    if (preferences.pace === "relaxed") {
      score += route.status === "可执行" ? 8 : route.status === "略紧张" ? 1 : -8;
      tags.add("节奏轻松");
    } else if (preferences.pace === "tight") {
      score += route.totalDuration <= (intent?.durationHours ?? 4) * 60 ? 6 : -4;
      tags.add("紧凑高效");
    } else {
      score += route.status !== "不可执行" ? 5 : -6;
    }

    if (intentPreferences.includes("少排队")) {
      score += clamp(16 - route.totalQueueTime * 0.55, -10, 10);
      tags.add("少排队");
    }

    if (intentPreferences.includes("少走路")) {
      score += clamp(14 - route.totalDistance * 4.2, -9, 9);
      tags.add("少走路");
    }

    if (intentPreferences.includes("高评分")) {
      score += clamp((averageRating(routePois) - 4.2) * 10, 0, 7);
      tags.add("高评分");
    }

    if (intentPreferences.includes("小众")) {
      const nicheCount = routePois.filter((poi) => poi.tags.includes("小众") || poi.tags.includes("安静")).length;
      score += nicheCount * 3;
      if (nicheCount > 0) tags.add("小众");
    }

    if (intentPreferences.includes("适合拍照")) {
      const photoCount = routePois.filter((poi) => poi.tags.includes("适合拍照") || poi.tags.includes("拍照")).length;
      score += photoCount * 3;
      if (photoCount > 0) tags.add("适合拍照");
    }

    if (intentPreferences.includes("体验轻松")) {
      score += route.status === "可执行" ? 6 : -3;
      tags.add("体验轻松");
    }

    if (mallRatio > 0 && preferences.foodVsPlay >= 55) {
      score += 2;
      tags.add("室内备选");
    }

    const preferenceScore = Math.round(clamp(score, 45, 98));
    return {
      route: {
        ...route,
        preferenceScore,
        preferenceTags: [formatScoreTag(preferenceScore), ...Array.from(tags)].slice(0, 4),
        preferenceReason: buildPreferenceReason(preferences, intentPreferences, route, routePois, maxWalkMinutes),
      },
      index,
    };
  });

  return annotated
    .sort((a, b) => (b.route.preferenceScore ?? 0) - (a.route.preferenceScore ?? 0) || a.index - b.index)
    .map((item) => item.route);
}
