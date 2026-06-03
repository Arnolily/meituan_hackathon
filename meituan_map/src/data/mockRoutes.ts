import type { RoutePlan } from "../types";
import { recalculateRoutes } from "../utils/routeCalculations";
import { MOCK_POIS } from "./mockPois";

const routeTemplates: RoutePlan[] = [
  {
    id: "route-efficiency",
    name: "效率优先路线",
    strategy: "efficiency",
    poiIds: ["poi-food-2", "poi-park-2", "poi-culture-2"],
    totalDuration: 185,
    totalDistance: 2.1,
    totalQueueTime: 13,
    avgCost: 75,
    reason: "这条路线距离最短，地点之间衔接紧凑，适合希望少走路、快速完成主要体验的用户。",
    status: "可执行",
    timelineStart: "14:00",
    label: "效率优先路线",
    tag: "少绕路",
    stops: [],
    totalMinutes: 185,
    polyline: [],
  },
  {
    id: "route-experience",
    name: "体验优先路线",
    strategy: "experience",
    poiIds: ["poi-food-1", "poi-park-3", "poi-culture-1", "poi-culture-3"],
    totalDuration: 255,
    totalDistance: 3.4,
    totalQueueTime: 25,
    avgCost: 121,
    reason: "这条路线覆盖餐饮、散步和文化空间，内容更丰富，适合希望慢慢体验城市街区的用户。",
    status: "略紧张",
    timelineStart: "14:00",
    label: "体验优先路线",
    tag: "体验优先",
    stops: [],
    totalMinutes: 255,
    polyline: [],
  },
  {
    id: "route-low-queue",
    name: "低排队路线",
    strategy: "lowQueue",
    poiIds: ["poi-food-4", "poi-park-2", "poi-culture-3", "poi-mall-2"],
    totalDuration: 175,
    totalDistance: 2.8,
    totalQueueTime: 12,
    avgCost: 92,
    reason: "这条路线优先选择排队较少、停留灵活的地点，适合不想等待、希望行程更稳的用户。",
    status: "可执行",
    timelineStart: "14:00",
    label: "低排队路线",
    tag: "低排队",
    stops: [],
    totalMinutes: 175,
    polyline: [],
  },
];

export const MOCK_ROUTES: RoutePlan[] = recalculateRoutes(routeTemplates, MOCK_POIS, 4);
export const mockRoutes = MOCK_ROUTES;
