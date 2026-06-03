/** 出行方式倾向 */
export type TransportPreference = "walk" | "balanced" | "transit";

/** 行程节奏 */
export type TripPace = "relaxed" | "normal" | "tight";

export interface RoutePlanningPreferences {
  /** 更愿步行 / 均衡 / 更愿地铁公交 */
  transport: TransportPreference;
  /** 0 吃为主 … 50 均衡 … 100 玩为主 */
  foodVsPlay: number;
  /** 单段乐意步行时长（分钟） */
  walkMinutes: number;
  /** 尽量减少地铁换乘 */
  avoidTransfers: boolean;
  /** 慢游 / 适中 / 紧凑 */
  pace: TripPace;
}

export const DEFAULT_ROUTE_PREFERENCES: RoutePlanningPreferences = {
  transport: "balanced",
  foodVsPlay: 50,
  walkMinutes: 15,
  avoidTransfers: false,
  pace: "normal",
};

const STORAGE_KEY = "meituan_map_route_prefs";

export function loadRoutePreferences(): RoutePlanningPreferences {
  if (typeof localStorage === "undefined") return { ...DEFAULT_ROUTE_PREFERENCES };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_ROUTE_PREFERENCES };
    return { ...DEFAULT_ROUTE_PREFERENCES, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_ROUTE_PREFERENCES };
  }
}

export function saveRoutePreferences(prefs: RoutePlanningPreferences) {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* quota / private mode */
  }
}

export function describeRoutePreferences(p: RoutePlanningPreferences): string {
  const transport =
    p.transport === "walk" ? "多走路" : p.transport === "transit" ? "偏地铁公交" : "步行与公共交通均衡";
  const focus =
    p.foodVsPlay <= 30 ? "吃饭探店优先" : p.foodVsPlay >= 70 ? "景点游玩优先" : "吃玩兼顾";
  const pace = p.pace === "relaxed" ? "慢游" : p.pace === "tight" ? "紧凑高效" : "节奏适中";
  const transfer = p.avoidTransfers ? "，尽量少换乘" : "";
  return `${transport}，${focus}，单段步行约 ${p.walkMinutes} 分钟，${pace}${transfer}`;
}
