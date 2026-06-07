import { create } from "zustand";
import { MOCK_POIS } from "../data/mockPois";
import { MOCK_ROUTES } from "../data/mockRoutes";
import { DEFAULT_MANUAL_START } from "../data/constants";
import type {
  AppView,
  GenerationStage,
  Poi,
  RouteAdjustmentAction,
  RouteHistoryItem,
  RoutePlan,
  TravelIntent,
} from "../types";
import {
  DEFAULT_ROUTE_PREFERENCES,
  loadRoutePreferences,
  saveRoutePreferences,
  type RoutePlanningPreferences,
} from "../types/routePreferences";
import { getPoisForRoute, recalculateRoute, recalculateRoutes, walkingDistanceKm } from "../utils/routeCalculations";
import { createRouteHistoryItem, loadRouteHistory, prependRouteHistory, saveRouteHistory } from "../utils/routeHistory";
import { personalizeRoutes } from "../utils/routePersonalization";
import {
  isPlannerClarificationError,
  type BackendIntentSummary,
  type PlannerBackendResult,
  type PlannerClarification,
  type PlannerStreamEvent,
  streamRoutesWithBackend,
} from "../services/plannerBackend";

export type AccountSection = "login" | "profile" | "preferences" | "history";
export type AccountView = "menu" | "detail";
export type GenerationPanelMode = "open" | "docked" | "closed";

export interface AccountUser {
  name: string;
  email: string;
  phone?: string;
}

const ACCOUNT_USER_STORAGE_KEY = "meituan_map_account_user";

function loadAccountUser(): AccountUser | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(ACCOUNT_USER_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AccountUser) : null;
  } catch {
    return null;
  }
}

function saveAccountUser(user: AccountUser | null) {
  if (typeof localStorage === "undefined") return;
  try {
    if (user) localStorage.setItem(ACCOUNT_USER_STORAGE_KEY, JSON.stringify(user));
    else localStorage.removeItem(ACCOUNT_USER_STORAGE_KEY);
  } catch {
    /* ignore quota/private mode */
  }
}

interface AppState {
  currentView: AppView;
  mapInstance: unknown | null;
  mapReady: boolean;
  mapError: string | null;
  userMapCenter: [number, number] | null;
  travelIntent: TravelIntent | null;
  generationStage: GenerationStage;
  generationProgressText: string;
  generationEvents: PlannerStreamEvent[];
  generationProgress: number;
  generationPanelMode: GenerationPanelMode;
  isBackgroundEnriching: boolean;
  activeRequestId: string | null;
  pois: Poi[];
  routes: RoutePlan[];
  activeRouteId: string | null;
  adoptedRouteId: string | null;
  visiblePoiIds: string[];
  selectedPoiId: string | null;
  detailPoi: Poi | null;
  showTimeline: boolean;
  agentNotices: string[];
  executionRouteId: string | null;
  currentStepIndex: number;
  executionArrived: boolean;
  toast: string | null;
  themeToastAt: number;
  shareOpen: boolean;
  accountSidebarOpen: boolean;
  accountView: AccountView;
  accountSection: AccountSection;
  accountUser: AccountUser | null;
  routePreferences: RoutePlanningPreferences;
  routeHistory: RouteHistoryItem[];
  backendIntent: BackendIntentSummary | null;
  backendClarification: PlannerClarification | null;
  backendClarificationContext: { answers: Record<string, string>; intent: unknown } | null;
  setCurrentView: (view: AppView) => void;
  setMapInstance: (m: unknown) => void;
  setMapReady: (v: boolean) => void;
  setMapError: (e: string | null) => void;
  setUserMapCenter: (c: [number, number] | null) => void;
  setTravelIntent: (intent: TravelIntent) => void;
  updateTravelIntent: (patch: Partial<TravelIntent>) => void;
  confirmTravelIntent: () => void;
  setGenerationStage: (stage: GenerationStage) => void;
  setGenerationPanelMode: (mode: GenerationPanelMode) => void;
  cancelGeneration: () => void;
  runDemoGeneration: () => Promise<void>;
  submitBackendClarification: (answers: Record<string, string>) => Promise<void>;
  clearBackendClarification: () => void;
  setBackendClarification: (clarification: PlannerClarification | null) => void;
  setBackendIntent: (intent: BackendIntentSummary | null) => void;
  setPois: (pois: Poi[]) => void;
  setRoutes: (routes: RoutePlan[]) => void;
  setActiveRoute: (id: string | null) => void;
  setSelectedPoi: (id: string | null) => void;
  reorderRoutePois: (routeId: string, sourceIndex: number, destinationIndex: number) => void;
  removePoiFromRoute: (routeId: string, poiId: string) => void;
  replacePoiInRoute: (routeId: string, oldPoiId: string, newPoiId: string) => void;
  updatePoiStayTime: (poiId: string, stayTime: number) => void;
  updateRouteDurationTarget: (durationHours: number) => void;
  applyRouteInstruction: (routeId: string, action: RouteAdjustmentAction, note?: string) => void;
  saveRouteToHistory: (routeId?: string) => void;
  reuseRouteHistory: (historyId: string) => void;
  clearRouteHistory: () => void;
  addAgentNotice: (text: string) => void;
  clearAgentNotices: () => void;
  startExecution: (routeId: string) => void;
  advanceExecutionStep: () => void;
  skipExecutionStep: () => void;
  replaceNextExecutionPoi: (newPoiId: string) => void;
  markExecutionArrived: () => void;
  endExecution: () => void;
  setAdoptedRoute: (id: string | null) => void;
  setVisiblePois: (ids: string[]) => void;
  setDetailPoi: (p: Poi | null) => void;
  setSelectedPoiId: (id: string | null) => void;
  setShowTimeline: (v: boolean) => void;
  showToast: (msg: string) => void;
  clearToast: () => void;
  setShareOpen: (v: boolean) => void;
  setAccountSidebarOpen: (v: boolean) => void;
  toggleAccountSidebar: () => void;
  setAccountSection: (s: AccountSection) => void;
  openAccountDetail: (s: AccountSection) => void;
  backToAccountMenu: () => void;
  loginAccount: (user: AccountUser) => void;
  logoutAccount: () => void;
  setRoutePreferences: (patch: Partial<RoutePlanningPreferences>) => void;
  resetRoutePreferences: () => void;
}

const DEMO_INTENT: TravelIntent = {
  rawText: "我今天下午想在费城玩 4 个小时，想吃点东西、逛公园、看点有意思的文化空间，不想排队太久，预算中等。",
  startMode: "now",
  startPointMode: "manual",
  manualStartName: DEFAULT_MANUAL_START,
  durationHours: 4,
  budgetLevel: "medium",
  pace: "relaxed",
  preferences: ["少排队", "少走路", "体验轻松"],
  poiTypes: ["餐饮", "公园", "文化"],
  confirmed: false,
};

const GENERATION_TEXT: Record<GenerationStage, string> = {
  idle: "准备生成路线",
  intent_parsing: "正在理解你的出行需求",
  poi_filtering: "正在筛选附近适合的地点",
  route_comparing: "正在比较不同路线组合",
  route_generating: "正在生成 3 条可执行路线",
  route_ready: "路线已生成",
};

let activeGenerationController: AbortController | null = null;
const clonePois = () => MOCK_POIS.map((poi) => ({ ...poi, tags: [...poi.tags], alternatives: [...poi.alternatives] }));
const cloneRoutePlan = (route: RoutePlan): RoutePlan => ({
  ...route,
  poiIds: [...route.poiIds],
  stops: route.stops.map((stop) => ({ ...stop })),
  polyline: route.polyline.map((point) => [...point] as [number, number]),
  preferenceTags: route.preferenceTags ? [...route.preferenceTags] : undefined,
  preferenceReason: route.preferenceReason,
});
const cloneRoutes = (
  targetHours: number,
  routePreferences: RoutePlanningPreferences,
  intent: TravelIntent | null,
  pois = clonePois()
) => personalizeRoutes(recalculateRoutes(MOCK_ROUTES.map(cloneRoutePlan), pois, targetHours), pois, routePreferences, intent);

function targetHoursFrom(intent: TravelIntent | null) {
  return intent?.durationHours ?? 4;
}

function isPlannerBackendResult(data: PlannerStreamEvent["data"]): data is PlannerBackendResult {
  return Boolean(data && "routes" in data && "pois" in data);
}

function stageFromStreamEvent(event: PlannerStreamEvent, current: GenerationStage): GenerationStage {
  if (event.type === "partial_result") return "route_comparing";
  if (event.type === "result") return "route_generating";
  if (event.type !== "stage") return current;
  if (event.stage === "fast_planning") return "poi_filtering";
  if (event.stage === "enriching") return "route_comparing";
  return current;
}

function refreshRoutes(
  routes: RoutePlan[],
  pois: Poi[],
  targetHours: number,
  routePreferences: RoutePlanningPreferences,
  intent: TravelIntent | null
) {
  return personalizeRoutes(recalculateRoutes(routes.map(cloneRoutePlan), pois, targetHours), pois, routePreferences, intent);
}

function applyBackendAnswersToIntent(
  clarification: PlannerClarification,
  answers: Record<string, string>
): BackendIntentSummary {
  const events = clarification.intent.events?.map((event) => ({
    ...event,
    categories: event.categories ? [...event.categories] : undefined,
    poi_types: event.poi_types ? [...event.poi_types] : undefined,
    soft_preferences: event.soft_preferences ? [...event.soft_preferences] : undefined,
  }));
  if (!events) return clarification.intent;

  for (const question of clarification.questions) {
    const answer = answers[question.id];
    if (!answer || answer === "do_not_care") continue;
    const event = events[question.event_index - 1];
    if (!event) continue;
    if (question.field === "budget_level") {
      event.budget_level = answer;
    }
    if (question.field === "cuisine_category") {
      const categories = event.categories ?? [];
      event.categories = categories.includes(answer) ? categories : [...categories, answer];
    }
  }

  return { ...clarification.intent, events };
}

function sortByNearestNeighbor(route: RoutePlan, pois: Poi[]) {
  const routePois = getPoisForRoute(route, pois);
  if (routePois.length <= 2) return [...route.poiIds];

  const ordered = [routePois[0]];
  const remaining = routePois.slice(1);
  while (remaining.length > 0) {
    const last = ordered[ordered.length - 1];
    let bestIndex = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    remaining.forEach((poi, index) => {
      const distance = walkingDistanceKm(last, poi);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    });
    ordered.push(remaining.splice(bestIndex, 1)[0]);
  }

  return ordered.map((poi) => poi.id);
}

function candidateForRoute(route: RoutePlan, pois: Poi[], types: Poi["type"][], preferLowQueue = false) {
  const currentIds = new Set(route.poiIds);
  return pois
    .filter((poi) => types.includes(poi.type) && !currentIds.has(poi.id))
    .sort((a, b) => {
      if (preferLowQueue && a.queueTime !== b.queueTime) return a.queueTime - b.queueTime;
      return b.rating - a.rating || a.queueTime - b.queueTime;
    })[0];
}

function replaceWeakestByType(route: RoutePlan, pois: Poi[], types: Poi["type"][], preferLowQueue = false) {
  const routePois = getPoisForRoute(route, pois);
  const candidate = candidateForRoute(route, pois, types, preferLowQueue);
  if (!candidate) return route;

  const replaceTarget =
    routePois.find((poi) => !types.includes(poi.type)) ??
    [...routePois].sort((a, b) => (preferLowQueue ? b.queueTime - a.queueTime : a.rating - b.rating))[0];

  return replaceTarget
    ? { ...route, poiIds: route.poiIds.map((id) => (id === replaceTarget.id ? candidate.id : id)) }
    : route;
}

export const useAppStore = create<AppState>((set, get) => ({
  currentView: "intent",
  mapInstance: null,
  mapReady: false,
  mapError: null,
  userMapCenter: null,
  travelIntent: null,
  generationStage: "idle",
  generationProgressText: GENERATION_TEXT.idle,
  generationEvents: [],
  generationProgress: 0,
  generationPanelMode: "closed",
  isBackgroundEnriching: false,
  activeRequestId: null,
  pois: [],
  routes: [],
  activeRouteId: null,
  adoptedRouteId: null,
  visiblePoiIds: [],
  selectedPoiId: null,
  detailPoi: null,
  showTimeline: false,
  agentNotices: [],
  executionRouteId: null,
  currentStepIndex: 0,
  executionArrived: false,
  toast: null,
  themeToastAt: 0,
  shareOpen: false,
  accountSidebarOpen: false,
  accountView: "menu",
  accountSection: "login",
  accountUser: typeof window !== "undefined" ? loadAccountUser() : null,
  routePreferences: typeof window !== "undefined" ? loadRoutePreferences() : { ...DEFAULT_ROUTE_PREFERENCES },
  routeHistory: typeof window !== "undefined" ? loadRouteHistory() : [],
  backendIntent: null,
  backendClarification: null,
  backendClarificationContext: null,
  setCurrentView: (view) => set({ currentView: view }),
  setMapInstance: (m) => set({ mapInstance: m }),
  setMapReady: (v) => set({ mapReady: v }),
  setMapError: (e) => set({ mapError: e }),
  setUserMapCenter: (c) => set({ userMapCenter: c }),
  setTravelIntent: (intent) => set({ travelIntent: intent }),
  updateTravelIntent: (patch) =>
    set((s) => ({ travelIntent: { ...(s.travelIntent ?? DEMO_INTENT), ...patch } })),
  confirmTravelIntent: () =>
    set((s) => (s.travelIntent ? { travelIntent: { ...s.travelIntent, confirmed: true } } : s)),
  setGenerationStage: (stage) => set({ generationStage: stage, generationProgressText: GENERATION_TEXT[stage] }),
  setGenerationPanelMode: (mode) => set({ generationPanelMode: mode }),
  cancelGeneration: () => {
    activeGenerationController?.abort();
    activeGenerationController = null;
    set({
      generationStage: "idle",
      generationProgressText: "已停止生成",
      generationPanelMode: get().generationEvents.length ? "docked" : "closed",
      isBackgroundEnriching: false,
      activeRequestId: null,
    });
  },
  runDemoGeneration: async () => {
    activeGenerationController?.abort();
    activeGenerationController = new AbortController();
    const controller = activeGenerationController;
    set({
      pois: [],
      routes: [],
      activeRouteId: null,
      selectedPoiId: null,
      detailPoi: null,
      visiblePoiIds: [],
      generationEvents: [],
      generationProgress: 0,
      generationPanelMode: "open",
      isBackgroundEnriching: false,
      activeRequestId: null,
    });

    const state = get();
    const travelIntent = state.travelIntent;
    if (!travelIntent) return;
    const backendContext = state.backendClarificationContext ?? (state.backendIntent ? { answers: {}, intent: state.backendIntent } : undefined);

    try {
      get().setGenerationStage("intent_parsing");
      const anchor =
        state.userMapCenter && travelIntent.startPointMode === "currentLocation"
          ? { lng: state.userMapCenter[0], lat: state.userMapCenter[1], name: "当前位置" }
          : undefined;
      await streamRoutesWithBackend(
        travelIntent,
        anchor,
        backendContext,
        (event) => {
          if (controller.signal.aborted) return;
          set((current) => ({
            generationEvents: [...current.generationEvents, event].slice(-120),
            generationProgress: event.progress,
            generationProgressText: event.message,
            generationStage: stageFromStreamEvent(event, current.generationStage),
            activeRequestId: event.requestId,
            isBackgroundEnriching:
              event.type === "stage" && event.stage === "enriching"
                ? true
                : event.type === "complete"
                  ? false
                  : current.isBackgroundEnriching,
          }));

          if (event.type === "clarification" && event.data && "questions" in event.data) {
            set({
              backendClarification: event.data,
              backendClarificationContext: {
                answers: { ...(backendContext?.answers ?? {}) },
                intent: event.data.intent,
              },
              backendIntent: event.data.intent,
              generationStage: "idle",
              isBackgroundEnriching: false,
            });
            return;
          }

          if ((event.type === "partial_result" || event.type === "result") && isPlannerBackendResult(event.data)) {
            const latest = get();
            const routes = personalizeRoutes(event.data.routes, event.data.pois, latest.routePreferences, travelIntent);
            const recommendedRoute = routes[0];
            const activeRouteId = routes.some((route) => route.id === latest.activeRouteId)
              ? latest.activeRouteId
              : recommendedRoute?.id ?? null;
            const adoptedRouteId = routes.some((route) => route.id === latest.adoptedRouteId)
              ? latest.adoptedRouteId
              : recommendedRoute?.id ?? null;
            set({
              pois: event.data.pois,
              visiblePoiIds: event.data.pois.map((poi) => poi.id),
              routes,
              activeRouteId,
              adoptedRouteId,
              generationStage: event.type === "partial_result" ? "route_comparing" : "route_generating",
              generationPanelMode: event.type === "partial_result" ? "docked" : latest.generationPanelMode,
              showTimeline: true,
              backendClarification: null,
              backendClarificationContext: null,
              backendIntent: event.data.intent ?? latest.backendIntent,
              agentNotices: [...(event.data.agentNotices ?? []), ...latest.agentNotices].slice(0, 6),
            });
          }

          if (event.type === "warning") {
            set((current) => ({ agentNotices: [event.message, ...current.agentNotices].slice(0, 6) }));
          }

          if (event.type === "error") {
            set((current) => ({
              generationStage: "idle",
              isBackgroundEnriching: false,
              agentNotices: [event.message, ...current.agentNotices].slice(0, 6),
            }));
          }

          if (event.type === "complete" && !get().backendClarification && get().generationStage !== "idle") {
            set({
              generationStage: "route_ready",
              generationProgress: 100,
              generationProgressText: event.message,
              generationPanelMode: "docked",
              isBackgroundEnriching: false,
              activeRequestId: null,
            });
          }
        },
        controller.signal
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (isPlannerClarificationError(error)) {
        set({
          backendClarification: error.clarification,
          backendClarificationContext: {
            answers: { ...(backendContext?.answers ?? {}) },
            intent: error.clarification.intent,
          },
          backendIntent: error.clarification.intent,
          generationStage: "idle",
          generationProgressText: "需要补充几个偏好",
          agentNotices: ["还需要补充每一段行程的预算或地点类型，回答后会继续生成路线。", ...get().agentNotices].slice(0, 4),
        });
        return;
      }
      const pois = clonePois();
      const routes = cloneRoutes(targetHoursFrom(travelIntent), state.routePreferences, travelIntent, pois);
      const recommendedRoute = routes[0];
      set({
        pois,
        routes,
        visiblePoiIds: pois.map((poi) => poi.id),
        activeRouteId: recommendedRoute?.id ?? "route-experience",
        adoptedRouteId: recommendedRoute?.id ?? "route-experience",
        generationStage: "route_ready",
        generationProgressText: GENERATION_TEXT.route_ready,
        generationPanelMode: "docked",
        agentNotices: [
          `暂时无法生成真实路线，已先展示演示路线。${error instanceof Error ? error.message : ""}`,
          recommendedRoute
            ? `当前展示“${recommendedRoute.name}”，匹配度 ${recommendedRoute.preferenceScore ?? 80} 分。${recommendedRoute.preferenceReason ?? ""}`
            : "已展示前端演示路线。",
        ],
        showTimeline: true,
        backendClarification: null,
      });
    } finally {
      if (activeGenerationController === controller) activeGenerationController = null;
    }
  },
  submitBackendClarification: async (answers) => {
    const state = get();
    const travelIntent = state.travelIntent;
    const clarification = state.backendClarification;
    if (!travelIntent || !clarification) return;
    const answeredIntent = applyBackendAnswersToIntent(clarification, answers);
    if (!travelIntent.confirmed) {
      set({
        backendClarification: null,
        backendClarificationContext: {
          answers: { ...(state.backendClarificationContext?.answers ?? {}), ...answers },
          intent: answeredIntent,
        },
        backendIntent: answeredIntent,
        generationStage: "idle",
        generationProgressText: GENERATION_TEXT.idle,
        agentNotices: ["预算偏好已补充，可以继续确认这次计划。", ...state.agentNotices].slice(0, 4),
      });
      return;
    }

    activeGenerationController?.abort();
    activeGenerationController = new AbortController();
    const controller = activeGenerationController;
    const mergedAnswers = { ...(state.backendClarificationContext?.answers ?? {}), ...answers };
    set({
      backendClarification: null,
      generationStage: "poi_filtering",
      generationProgressText: "正在按补充偏好筛选地点",
      generationEvents: [],
      generationProgress: 0,
      generationPanelMode: "open",
      isBackgroundEnriching: false,
    });

    try {
      const anchor =
        state.userMapCenter && travelIntent.startPointMode === "currentLocation"
          ? { lng: state.userMapCenter[0], lat: state.userMapCenter[1], name: "当前位置" }
          : undefined;
      await streamRoutesWithBackend(
        travelIntent,
        anchor,
        {
          answers: mergedAnswers,
          intent: answeredIntent,
        },
        (event) => {
          if (controller.signal.aborted) return;
          set((current) => ({
            generationEvents: [...current.generationEvents, event].slice(-120),
            generationProgress: event.progress,
            generationProgressText: event.message,
            generationStage: stageFromStreamEvent(event, current.generationStage),
            activeRequestId: event.requestId,
            isBackgroundEnriching:
              event.type === "stage" && event.stage === "enriching"
                ? true
                : event.type === "complete"
                  ? false
                  : current.isBackgroundEnriching,
          }));

          if ((event.type === "partial_result" || event.type === "result") && isPlannerBackendResult(event.data)) {
            const latest = get();
            const routes = personalizeRoutes(event.data.routes, event.data.pois, latest.routePreferences, travelIntent);
            const recommendedRoute = routes[0];
            set({
              pois: event.data.pois,
              visiblePoiIds: event.data.pois.map((poi) => poi.id),
              routes,
              activeRouteId: recommendedRoute?.id ?? null,
              adoptedRouteId: recommendedRoute?.id ?? null,
              generationStage: event.type === "partial_result" ? "route_comparing" : "route_generating",
              generationPanelMode: event.type === "partial_result" ? "docked" : latest.generationPanelMode,
              backendClarificationContext: null,
              backendIntent: event.data.intent ?? answeredIntent,
              agentNotices: [...(event.data.agentNotices ?? []), ...latest.agentNotices].slice(0, 6),
              showTimeline: true,
            });
          }

          if (event.type === "clarification" && event.data && "questions" in event.data) {
            set({
              backendClarification: event.data,
              backendClarificationContext: {
                answers: mergedAnswers,
                intent: event.data.intent,
              },
              backendIntent: event.data.intent,
              generationStage: "idle",
              generationProgressText: "需要补充几个偏好",
              isBackgroundEnriching: false,
              activeRequestId: null,
            });
            return;
          }

          if (event.type === "warning") {
            set((current) => ({ agentNotices: [event.message, ...current.agentNotices].slice(0, 6) }));
          }

          if (event.type === "error") {
            set((current) => ({
              generationStage: "idle",
              isBackgroundEnriching: false,
              activeRequestId: null,
              agentNotices: [event.message, ...current.agentNotices].slice(0, 6),
            }));
          }

          if (event.type === "complete" && !get().backendClarification && get().generationStage !== "idle") {
            set({
              generationStage: "route_ready",
              generationProgress: 100,
              generationProgressText: event.message,
              generationPanelMode: "docked",
              isBackgroundEnriching: false,
              activeRequestId: null,
            });
          }
        },
        controller.signal
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (isPlannerClarificationError(error)) {
        set({
          backendClarification: error.clarification,
          backendClarificationContext: {
            answers: mergedAnswers,
            intent: error.clarification.intent,
          },
          backendIntent: error.clarification.intent,
          generationStage: "idle",
          generationProgressText: "需要补充几个偏好",
        });
        return;
      }
      set({
        backendClarification: null,
        generationStage: "idle",
        generationProgressText: GENERATION_TEXT.idle,
        agentNotices: [
          `路线生成失败。${error instanceof Error ? error.message : ""}`,
          ...state.agentNotices,
        ].slice(0, 4),
      });
    } finally {
      if (activeGenerationController === controller) activeGenerationController = null;
    }
  },
  clearBackendClarification: () =>
    set({ backendClarification: null, backendClarificationContext: null, generationStage: "idle", generationProgressText: GENERATION_TEXT.idle }),
  setBackendClarification: (clarification) =>
    set({
      backendClarification: clarification,
      backendClarificationContext: clarification ? get().backendClarificationContext : null,
      backendIntent: clarification?.intent ?? get().backendIntent,
    }),
  setBackendIntent: (intent) => set({ backendIntent: intent, backendClarificationContext: null }),
  setPois: (pois) => set({ pois }),
  setRoutes: (routes) => set({ routes }),
  setActiveRoute: (id) => set({ activeRouteId: id, adoptedRouteId: id, showTimeline: !!id }),
  setSelectedPoi: (id) => {
    const poi = get().pois.find((item) => item.id === id) ?? null;
    set({
      selectedPoiId: id,
      detailPoi: poi,
      shareOpen: id ? false : get().shareOpen,
      accountSidebarOpen: id ? false : get().accountSidebarOpen,
    });
  },
  reorderRoutePois: (routeId, sourceIndex, destinationIndex) =>
    set((s) => {
      const updatedRoutes = s.routes.map((route) => {
        if (route.id !== routeId) return route;
        const poiIds = [...route.poiIds];
        const [moved] = poiIds.splice(sourceIndex, 1);
        if (!moved) return route;
        poiIds.splice(destinationIndex, 0, moved);
        return { ...route, poiIds };
      });
      return {
        routes: refreshRoutes(updatedRoutes, s.pois, targetHoursFrom(s.travelIntent), s.routePreferences, s.travelIntent),
        agentNotices: [
          "路线顺序已更新。新的顺序会改变步行距离和到达时间，我已同步更新时间轴和路线状态。",
          ...s.agentNotices,
        ].slice(0, 4),
      };
    }),
  removePoiFromRoute: (routeId, poiId) =>
    set((s) => {
      const updatedRoutes = s.routes.map((route) => {
        if (route.id !== routeId) return route;
        return { ...route, poiIds: route.poiIds.filter((id) => id !== poiId) };
      });
      const routes = refreshRoutes(updatedRoutes, s.pois, targetHoursFrom(s.travelIntent), s.routePreferences, s.travelIntent);
      const route = routes.find((item) => item.id === routeId);
      const shortage = route && route.poiIds.length < 3 ? "当前路线少于 3 个地点，建议从备选点中补充一个地点，保证路线完整。" : "";
      return {
        routes,
        selectedPoiId: s.selectedPoiId === poiId ? null : s.selectedPoiId,
        detailPoi: s.detailPoi?.id === poiId ? null : s.detailPoi,
        agentNotices: [
          shortage || "已删除该地点，路线已重新计算。",
          ...s.agentNotices,
        ].slice(0, 4),
      };
    }),
  replacePoiInRoute: (routeId, oldPoiId, newPoiId) =>
    set((s) => {
      const updatedRoutes = s.routes.map((route) => {
        if (route.id !== routeId) return route;
        const poiIds = route.poiIds.map((id) => (id === oldPoiId ? newPoiId : id));
        return { ...route, poiIds };
      });
      return {
        routes: refreshRoutes(updatedRoutes, s.pois, targetHoursFrom(s.travelIntent), s.routePreferences, s.travelIntent),
        selectedPoiId: newPoiId,
        detailPoi: s.pois.find((poi) => poi.id === newPoiId) ?? null,
        agentNotices: ["已替换为新的地点。这个选择会减少排队时间，并保持路线整体顺路。", ...s.agentNotices].slice(0, 4),
      };
    }),
  updatePoiStayTime: (poiId, stayTime) =>
    set((s) => {
      const pois = s.pois.map((poi) => (poi.id === poiId ? { ...poi, stayTime } : poi));
      return {
        pois,
        detailPoi: s.detailPoi?.id === poiId ? { ...s.detailPoi, stayTime } : s.detailPoi,
        routes: refreshRoutes(s.routes, pois, targetHoursFrom(s.travelIntent), s.routePreferences, s.travelIntent),
      };
    }),
  updateRouteDurationTarget: (durationHours) =>
    set((s) => {
      const travelIntent = { ...(s.travelIntent ?? DEMO_INTENT), durationHours };
      return { travelIntent, routes: refreshRoutes(s.routes, s.pois, durationHours, s.routePreferences, travelIntent) };
    }),
  applyRouteInstruction: (routeId, action, note) =>
    set((s) => {
      const currentRoute = s.routes.find((route) => route.id === routeId);
      if (!currentRoute) return s;

      let pois = s.pois;
      let travelIntent = s.travelIntent;
      let activeRouteId = s.activeRouteId;
      let updatedRoutes = s.routes;
      let notice = note || "路线已按你的要求微调。";

      if (action === "lowQueue") {
        const routePois = getPoisForRoute(currentRoute, pois);
        const highQueuePoi = [...routePois].sort((a, b) => b.queueTime - a.queueTime)[0];
        const candidate = highQueuePoi
          ? pois
              .filter((poi) => poi.type === highQueuePoi.type && !currentRoute.poiIds.includes(poi.id) && poi.queueTime < highQueuePoi.queueTime)
              .sort((a, b) => a.queueTime - b.queueTime || b.rating - a.rating)[0]
          : null;

        if (highQueuePoi && candidate) {
          updatedRoutes = s.routes.map((route) =>
            route.id === routeId
              ? { ...route, poiIds: route.poiIds.map((id) => (id === highQueuePoi.id ? candidate.id : id)) }
              : route
          );
          notice = `已把“${highQueuePoi.name}”替换为等待更少的“${candidate.name}”。`;
        } else {
          const lowQueueRoute = s.routes.find((route) => route.strategy === "lowQueue");
          activeRouteId = lowQueueRoute?.id ?? activeRouteId;
          notice = "当前路线暂无更低排队的同类替换，已优先切到低排队方案。";
        }
      }

      if (action === "lessWalk") {
        updatedRoutes = s.routes.map((route) =>
          route.id === routeId ? { ...route, poiIds: sortByNearestNeighbor(route, pois) } : route
        );
        notice = "已重新排序当前地点，优先压缩站点之间的步行距离。";
      }

      if (action === "moreFood") {
        updatedRoutes = s.routes.map((route) => (route.id === routeId ? replaceWeakestByType(route, pois, ["餐饮"]) : route));
        notice = "已把路线调整得更偏逛吃，优先补入餐饮地点。";
      }

      if (action === "moreCulture") {
        updatedRoutes = s.routes.map((route) => (route.id === routeId ? replaceWeakestByType(route, pois, ["文化"]) : route));
        notice = "已提高文化空间占比，让路线更像城市文化漫步。";
      }

      if (action === "moreMall") {
        updatedRoutes = s.routes.map((route) =>
          route.id === routeId ? replaceWeakestByType(route, pois, ["商场"], true) : route
        );
        notice = "已加入更稳定的室内商场备选，适合天气或体力变化时使用。";
      }

      if (action === "relaxed") {
        const durationHours = Math.min(8, targetHoursFrom(travelIntent) + 1);
        travelIntent = { ...(travelIntent ?? DEMO_INTENT), durationHours, pace: "relaxed" };
        notice = `已把目标时长放宽到 ${durationHours} 小时，并按轻松节奏重新评估路线。`;
      }

      if (action === "compact") {
        const routePoiIds = new Set(currentRoute.poiIds);
        pois = pois.map((poi) => (routePoiIds.has(poi.id) ? { ...poi, stayTime: Math.max(30, poi.stayTime - 10) } : poi));
        travelIntent = { ...(travelIntent ?? DEMO_INTENT), pace: "compact" };
        notice = "已压缩当前路线停留时间，让行程更紧凑。";
      }

      if (action === "unknown") {
        return {
          agentNotices: [
            note || "我还没理解这次调整。你可以试试“少走路一点”“换成少排队”或“加一个商场”。",
            ...s.agentNotices,
          ].slice(0, 4),
        };
      }

      return {
        pois,
        travelIntent,
        activeRouteId,
        adoptedRouteId: activeRouteId,
        routes: refreshRoutes(updatedRoutes, pois, targetHoursFrom(travelIntent), s.routePreferences, travelIntent),
        agentNotices: [notice, ...s.agentNotices].slice(0, 4),
      };
    }),
  saveRouteToHistory: (routeId) => {
    const state = get();
    const route = state.routes.find((item) => item.id === (routeId ?? state.activeRouteId));
    if (!route) {
      state.showToast("当前没有可保存的路线");
      return;
    }
    const item = createRouteHistoryItem(route, state.travelIntent);
    const routeHistory = prependRouteHistory(item, state.routeHistory);
    saveRouteHistory(routeHistory);
    set({ routeHistory });
    state.showToast("已保存到历史路线");
  },
  reuseRouteHistory: (historyId) => {
    const state = get();
    const item = state.routeHistory.find((history) => history.id === historyId);
    if (!item) {
      state.showToast("没有找到这条历史路线");
      return;
    }

    const pois = clonePois();
    const travelIntent = item.intent ?? state.travelIntent ?? { ...DEMO_INTENT, confirmed: true };
    const restoredRoute = recalculateRoute(cloneRoutePlan(item.route), pois, targetHoursFrom(travelIntent));
    const defaultRoutes = cloneRoutes(targetHoursFrom(travelIntent), state.routePreferences, travelIntent, pois).filter(
      (route) => route.id !== restoredRoute.id
    );
    const routes = personalizeRoutes([restoredRoute, ...defaultRoutes], pois, state.routePreferences, travelIntent);

    set({
      currentView: "map",
      pois,
      routes,
      travelIntent,
      activeRouteId: restoredRoute.id,
      adoptedRouteId: restoredRoute.id,
      visiblePoiIds: pois.map((poi) => poi.id),
      generationStage: "route_ready",
      generationProgressText: GENERATION_TEXT.route_ready,
      showTimeline: true,
      accountSidebarOpen: false,
      accountView: "menu",
      agentNotices: [`已复用历史路线“${restoredRoute.name}”，你可以继续编辑或直接进入执行模式。`, ...state.agentNotices].slice(0, 4),
    });
    state.showToast("已复用历史路线");
  },
  clearRouteHistory: () => {
    saveRouteHistory([]);
    set({ routeHistory: [] });
    get().showToast("已清空历史路线");
  },
  addAgentNotice: (text) => set((s) => ({ agentNotices: [text, ...s.agentNotices].slice(0, 4) })),
  clearAgentNotices: () => set({ agentNotices: [] }),
  startExecution: (routeId) => set({ executionRouteId: routeId, currentStepIndex: 0, executionArrived: false, currentView: "execution" }),
  markExecutionArrived: () => set({ executionArrived: true }),
  advanceExecutionStep: () =>
    set((s) => {
      const route = s.routes.find((item) => item.id === s.executionRouteId);
      const nextIndex = Math.min(s.currentStepIndex + 1, Math.max(0, (route?.poiIds.length ?? 1) - 1));
      return { currentStepIndex: nextIndex, executionArrived: false };
    }),
  skipExecutionStep: () =>
    set((s) => {
      const route = s.routes.find((item) => item.id === s.executionRouteId);
      const nextIndex = Math.min(s.currentStepIndex + 1, Math.max(0, (route?.poiIds.length ?? 1) - 1));
      return { currentStepIndex: nextIndex, executionArrived: false };
    }),
  replaceNextExecutionPoi: (newPoiId) => {
    const st = get();
    const route = st.routes.find((item) => item.id === st.executionRouteId);
    const oldPoiId = route?.poiIds[st.currentStepIndex + 1];
    if (route && oldPoiId) get().replacePoiInRoute(route.id, oldPoiId, newPoiId);
  },
  endExecution: () => set({ currentView: "map", executionRouteId: null, currentStepIndex: 0, executionArrived: false }),
  setAdoptedRoute: (id) => set({ adoptedRouteId: id }),
  setVisiblePois: (ids) => set({ visiblePoiIds: ids }),
  setDetailPoi: (p) => set({
    detailPoi: p,
    selectedPoiId: p?.id ?? null,
    shareOpen: p ? false : get().shareOpen,
    accountSidebarOpen: p ? false : get().accountSidebarOpen,
  }),
  setSelectedPoiId: (id) => get().setSelectedPoi(id),
  setShowTimeline: (v) => set({ showTimeline: v }),
  showToast: (msg) => {
    set({ toast: msg });
    window.setTimeout(() => {
      if (get().toast === msg) set({ toast: null });
    }, 3000);
  },
  clearToast: () => set({ toast: null }),
  setShareOpen: (v) => set({
    shareOpen: v,
    detailPoi: v ? null : get().detailPoi,
    selectedPoiId: v ? null : get().selectedPoiId,
    accountSidebarOpen: v ? false : get().accountSidebarOpen,
  }),
  setAccountSidebarOpen: (v) => {
    set({
      accountSidebarOpen: v,
      accountView: v ? get().accountView : "menu",
      shareOpen: v ? false : get().shareOpen,
      detailPoi: v ? null : get().detailPoi,
      selectedPoiId: v ? null : get().selectedPoiId,
    });
  },
  toggleAccountSidebar: () => get().setAccountSidebarOpen(!get().accountSidebarOpen),
  setAccountSection: (s) => set({ accountSection: s }),
  openAccountDetail: (s) => set({ accountSection: s, accountView: "detail" }),
  backToAccountMenu: () => set({ accountView: "menu" }),
  loginAccount: (user) => {
    saveAccountUser(user);
    set({ accountUser: user, accountView: "menu" });
    if (!get().accountSidebarOpen) get().setAccountSidebarOpen(true);
  },
  logoutAccount: () => {
    saveAccountUser(null);
    set({ accountUser: null, accountView: "menu" });
  },
  setRoutePreferences: (patch) => {
    const state = get();
    const next = { ...state.routePreferences, ...patch };
    const routes = refreshRoutes(state.routes, state.pois, targetHoursFrom(state.travelIntent), next, state.travelIntent);
    const recommendedRoute = routes[0];
    saveRoutePreferences(next);
    set({
      routePreferences: next,
      routes,
      activeRouteId: state.routes.length > 0 ? recommendedRoute?.id ?? state.activeRouteId : state.activeRouteId,
      adoptedRouteId: state.routes.length > 0 ? recommendedRoute?.id ?? state.adoptedRouteId : state.adoptedRouteId,
      agentNotices:
        state.routes.length > 0 && recommendedRoute
          ? [
              `已按新的个人偏好重排方案，当前更推荐“${recommendedRoute.name}”。${recommendedRoute.preferenceReason ?? ""}`,
              ...state.agentNotices,
            ].slice(0, 4)
          : state.agentNotices,
    });
  },
  resetRoutePreferences: () => {
    const next = { ...DEFAULT_ROUTE_PREFERENCES };
    const state = get();
    saveRoutePreferences(next);
    set({
      routePreferences: next,
      routes: refreshRoutes(state.routes, state.pois, targetHoursFrom(state.travelIntent), next, state.travelIntent),
    });
    get().showToast("已恢复默认路线偏好");
  },
}));
