export type AppView = "intent" | "map" | "execution";

export type PoiType = "餐饮" | "娱乐" | "商场" | "公园" | "文化";
export type PoiCategory = "food" | "mall" | "restroom" | "study" | "entertainment" | "life";
export type StartMode = "now" | "planned";
export type StartPointMode = "currentLocation" | "manual";
export type BudgetLevel = "low" | "medium" | "high";
export type Pace = "relaxed" | "balanced" | "compact";
export type GenerationStage =
  | "idle"
  | "intent_parsing"
  | "poi_filtering"
  | "route_comparing"
  | "route_generating"
  | "route_ready";
export type RouteStrategy = "efficiency" | "experience" | "lowQueue";
export type RouteStatus = "可执行" | "略紧张" | "不可执行";
export type RouteAdjustmentAction =
  | "lowQueue"
  | "lessWalk"
  | "moreFood"
  | "moreCulture"
  | "moreMall"
  | "relaxed"
  | "compact"
  | "unknown";

export interface TravelIntent {
  rawText: string;
  startMode: StartMode;
  startPointMode: StartPointMode;
  manualStartName?: string;
  durationHours: number;
  budgetLevel: BudgetLevel;
  pace: Pace;
  preferences: string[];
  poiTypes: PoiType[];
  confirmed: boolean;
}

export interface RouteStop {
  poiId: string;
  arriveTime: string;
  walkMinutes: number;
  leaveTime?: string;
}

export interface Poi {
  id: string;
  name: string;
  type: PoiType;
  category: PoiCategory;
  lng: number;
  lat: number;
  rating: number;
  avgPrice: number;
  queueTime: number;
  stayTime: number;
  recommendedStayTime: number;
  tags: string[];
  commentParsed?: boolean;
  reviewSummary: string[];
  riskNotes: string[];
  recommendReason: string;
  alternatives: string[];
  price?: number;
  distance?: number;
}

export interface RoutePlan {
  id: string;
  name: string;
  strategy: RouteStrategy;
  poiIds: string[];
  totalDuration: number;
  totalDistance: number;
  totalQueueTime: number;
  avgCost: number;
  reason: string;
  status: RouteStatus;
  timelineStart: string;
  label: string;
  tag: string;
  stops: RouteStop[];
  totalMinutes: number;
  polyline: [number, number][];
  geometrySource?: "openrouteservice" | "google_directions" | "unavailable";
  preferenceScore?: number;
  preferenceTags?: string[];
  preferenceReason?: string;
}

export interface RouteHistoryItem {
  id: string;
  createdAt: string;
  route: RoutePlan;
  intent: TravelIntent | null;
}
