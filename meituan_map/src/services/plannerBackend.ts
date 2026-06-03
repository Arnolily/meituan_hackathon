import type { Poi, RoutePlan, TravelIntent } from "../types";
import { getSelectedCommentModelChoiceId, getSelectedModelChoiceId, type ModelChoiceId } from "./mimo";

const DEFAULT_PLANNER_ENDPOINT = "/api/planner/routes";
const DEFAULT_PLANNER_CLARIFICATION_ENDPOINT = "/api/planner/clarifications";

export interface PlannerBackendResult {
  pois: Poi[];
  routes: RoutePlan[];
  agentNotices?: string[];
  intent?: BackendIntentSummary;
}

export interface PlannerClarificationQuestion {
  id: string;
  event_index: number;
  field: "budget_level" | "cuisine_category";
  question: string;
  options: string[];
}

export interface BackendIntentEvent {
  name?: string | null;
  goal: string;
  categories?: string[];
  poi_types?: string[];
  budget_level?: string;
  soft_preferences?: string[];
  target_area?: string | null;
}

export interface BackendIntentSummary {
  city?: string | null;
  overall_goal?: string;
  events?: BackendIntentEvent[];
}

export interface PlannerClarification {
  needsClarification: boolean;
  intent: BackendIntentSummary;
  questions: PlannerClarificationQuestion[];
}

export class PlannerClarificationError extends Error {
  clarification: PlannerClarification;

  constructor(clarification: PlannerClarification) {
    super("还需要补充偏好");
    this.name = "PlannerClarificationError";
    this.clarification = clarification;
  }
}

export function isPlannerClarificationError(error: unknown): error is PlannerClarificationError {
  return error instanceof PlannerClarificationError;
}

function getPlannerEndpoint() {
  return import.meta.env.VITE_PLANNER_API_PATH ?? DEFAULT_PLANNER_ENDPOINT;
}

function getPlannerClarificationEndpoint() {
  return import.meta.env.VITE_PLANNER_CLARIFICATION_API_PATH ?? DEFAULT_PLANNER_CLARIFICATION_ENDPOINT;
}

export async function requestPlannerClarification(travelIntent: TravelIntent, anchor?: { lat: number; lng: number; name?: string }) {
  const response = await fetch(getPlannerClarificationEndpoint(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: travelIntent.rawText,
      travelIntent,
      anchor,
      mode: "walking",
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.error ?? `暂时无法确认预算：${response.status}`);
  }

  return (await response.json()) as PlannerClarification;
}

export async function parsePlannerIntent(
  travelIntent: TravelIntent,
  anchor?: { lat: number; lng: number; name?: string },
  modelChoice?: ModelChoiceId
) {
  const response = await fetch(getPlannerClarificationEndpoint(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: travelIntent.rawText,
      travelIntent,
      anchor,
      mode: "walking",
      modelChoice,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.error ?? `暂时无法理解需求：${response.status}`);
  }

  return (await response.json()) as PlannerClarification;
}

export async function generateRoutesWithBackend(
  travelIntent: TravelIntent,
  anchor?: { lat: number; lng: number; name?: string },
  clarification?: { answers: Record<string, string>; intent: unknown }
) {
  const response = await fetch(getPlannerEndpoint(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: travelIntent.rawText,
      travelIntent,
      anchor,
      mode: "walking",
      clarificationAnswers: clarification?.answers,
      backendIntent: clarification?.intent,
      modelChoice: getSelectedModelChoiceId(),
      commentModelChoice: getSelectedCommentModelChoiceId(),
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    if (response.status === 409 && payload?.needsClarification && Array.isArray(payload.questions)) {
      throw new PlannerClarificationError(payload as PlannerClarification);
    }
    throw new Error(payload?.error ?? `路线生成暂时失败：${response.status}`);
  }

  const payload = (await response.json()) as PlannerBackendResult;
  if (!payload.pois?.length || !payload.routes?.length) {
    throw new Error("暂时没有找到合适路线");
  }
  return payload;
}
