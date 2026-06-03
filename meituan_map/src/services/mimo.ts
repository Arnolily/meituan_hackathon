import type {
  BudgetLevel,
  Pace,
  Poi,
  PoiType,
  RouteAdjustmentAction,
  RoutePlan,
  StartMode,
  StartPointMode,
  TravelIntent,
} from "../types";

const DEFAULT_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1";
const DEFAULT_PROXY_PATH = "/api/mimo";
const DEFAULT_MODEL = "mimo-v2.5-pro";
const DEFAULT_DEEPSEEK_BASE_URL = "https://api.siliconflow.cn/v1";
const DEFAULT_DEEPSEEK_PROXY_PATH = "/api/deepseek";
const DEFAULT_DEEPSEEK_MODEL = "deepseek-ai/DeepSeek-V4-Flash";
const MODEL_CHOICE_STORAGE_KEY = "meituan_map_model_choice";
const COMMENT_MODEL_CHOICE_STORAGE_KEY = "meituan_map_comment_model_choice";
export type ModelChoiceId = "mimo" | "deepseek";
const ALLOWED_START_MODES: StartMode[] = ["now", "planned"];
const ALLOWED_START_POINT_MODES: StartPointMode[] = ["currentLocation", "manual"];
const ALLOWED_BUDGETS: BudgetLevel[] = ["low", "medium", "high"];
const ALLOWED_PACES: Pace[] = ["relaxed", "balanced", "compact"];
const ALLOWED_POI_TYPES: PoiType[] = ["餐饮", "娱乐", "商场", "公园", "文化"];
const ALLOWED_PREFERENCES = ["少排队", "少走路", "高评分", "小众", "适合拍照", "体验轻松"];
const ALLOWED_ROUTE_ADJUSTMENTS: RouteAdjustmentAction[] = [
  "lowQueue",
  "lessWalk",
  "moreFood",
  "moreCulture",
  "moreMall",
  "relaxed",
  "compact",
  "unknown",
];

interface MimoChoice {
  message?: {
    content?: string | Array<{ type?: string; text?: string }>;
    reasoning_content?: string | Array<{ type?: string; text?: string }>;
  };
  finish_reason?: string;
}

interface MimoResponse {
  choices?: MimoChoice[];
}

interface ModelIntentPatch {
  startMode?: string;
  startPointMode?: string;
  manualStartName?: string;
  durationHours?: number;
  budgetLevel?: string;
  pace?: string;
  preferences?: string[];
  poiTypes?: string[];
}

interface RouteAdjustmentPatch {
  action?: string;
  note?: string;
}

type MimoResponseFormat = "json_object" | "text";

interface MimoRequestOptions {
  maxTokens?: number;
  responseFormat?: MimoResponseFormat;
}

export interface ModelChoice {
  id: ModelChoiceId;
  label: string;
  model: string;
}

export function getAvailableModelChoices(): ModelChoice[] {
  return [
    {
      id: "mimo",
      label: "MiMo",
      model: import.meta.env.VITE_MIMO_MODEL ?? DEFAULT_MODEL,
    },
    {
      id: "deepseek",
      label: "DeepSeek",
      model: import.meta.env.VITE_DEEPSEEK_MODEL ?? DEFAULT_DEEPSEEK_MODEL,
    },
  ];
}

function normalizeTextContent(content: string | Array<{ type?: string; text?: string }> | undefined) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((item) => item.text ?? "").join("");
}

function extractAssistantText(choice: MimoChoice | undefined) {
  const content = normalizeTextContent(choice?.message?.content);
  const reasoningContent = normalizeTextContent(choice?.message?.reasoning_content);
  const text = content || reasoningContent;

  if (!text) {
    throw new Error("模型没有返回内容");
  }

  if (choice?.finish_reason === "length") {
    throw new Error("模型回复过长，请再试一次");
  }

  return text;
}

function parseJsonBlock<T>(text: string) {
  const trimmed = text.trim();
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = (fenced?.[1] ?? trimmed).trim();
  try {
    return JSON.parse(candidate) as T;
  } catch {
    const jsonStart = candidate.indexOf("{");
    const jsonEnd = candidate.lastIndexOf("}");
    if (jsonStart >= 0 && jsonEnd > jsonStart) {
      return JSON.parse(candidate.slice(jsonStart, jsonEnd + 1)) as T;
    }
    throw new Error("模型没有返回可用结果");
  }
}

function pickEnumValue<T extends string>(value: string | undefined, allowed: readonly T[], fallback: T) {
  return value && allowed.includes(value as T) ? (value as T) : fallback;
}

function applyDirectIntentOverrides(rawText: string, intent: TravelIntent): TravelIntent {
  const text = rawText.trim().toLowerCase();
  const latestInstruction = text.split(/用户补充修改：|修改：/).pop() ?? text;
  const next = { ...intent };

  if (/预算.{0,8}(高|贵|品质)|(?:高|贵).{0,6}预算|改成高/.test(latestInstruction)) {
    next.budgetLevel = "high";
  } else if (/预算.{0,8}(低|少|便宜|省钱)|(?:低|少|便宜).{0,6}预算|改成低/.test(latestInstruction)) {
    next.budgetLevel = "low";
  } else if (/预算.{0,8}(中|适中|普通)|(?:中等|适中).{0,6}预算|改成中/.test(latestInstruction)) {
    next.budgetLevel = "medium";
  }

  if (/轻松|慢一点|松一点|不赶/.test(latestInstruction)) {
    next.pace = "relaxed";
  } else if (/紧凑|快一点|高效/.test(latestInstruction)) {
    next.pace = "compact";
  }

  return next;
}

function sanitizeIntentPatch(patch: ModelIntentPatch, draftIntent: TravelIntent): TravelIntent {
  const startMode = pickEnumValue(patch.startMode, ALLOWED_START_MODES, draftIntent.startMode);
  const startPointMode = pickEnumValue(patch.startPointMode, ALLOWED_START_POINT_MODES, draftIntent.startPointMode);
  const budgetLevel = pickEnumValue(patch.budgetLevel, ALLOWED_BUDGETS, draftIntent.budgetLevel);
  const pace = pickEnumValue(patch.pace, ALLOWED_PACES, draftIntent.pace);
  const durationValue = Number.isFinite(patch.durationHours) ? Math.round(patch.durationHours as number) : draftIntent.durationHours;
  const durationHours = Math.min(8, Math.max(2, durationValue));
  const preferences = Array.isArray(patch.preferences)
    ? patch.preferences.filter((item): item is string => ALLOWED_PREFERENCES.includes(item))
    : draftIntent.preferences;
  const poiTypes = Array.isArray(patch.poiTypes)
    ? patch.poiTypes.filter((item): item is PoiType => ALLOWED_POI_TYPES.includes(item as PoiType))
    : draftIntent.poiTypes;
  const manualStartName =
    startPointMode === "manual" ? patch.manualStartName?.trim() || draftIntent.manualStartName?.trim() || "" : undefined;

  return {
    ...draftIntent,
    startMode,
    startPointMode,
    manualStartName,
    durationHours,
    budgetLevel,
    pace,
    preferences: preferences.length > 0 ? [...new Set(preferences)] : draftIntent.preferences,
    poiTypes: poiTypes.length > 0 ? [...new Set(poiTypes)] : draftIntent.poiTypes,
    confirmed: false,
  };
}

export function getSelectedModelChoiceId(): ModelChoiceId {
  if (typeof localStorage !== "undefined") {
    const stored = localStorage.getItem(MODEL_CHOICE_STORAGE_KEY);
    if (stored === "mimo" || stored === "deepseek") return stored;
  }
  return "deepseek";
}

export function setSelectedModelChoiceId(choiceId: ModelChoiceId) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(MODEL_CHOICE_STORAGE_KEY, choiceId);
}

export function getSelectedCommentModelChoiceId(): ModelChoiceId {
  if (typeof localStorage !== "undefined") {
    const stored = localStorage.getItem(COMMENT_MODEL_CHOICE_STORAGE_KEY);
    if (stored === "mimo" || stored === "deepseek") return stored;
  }
  return "mimo";
}

export function setSelectedCommentModelChoiceId(choiceId: ModelChoiceId) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(COMMENT_MODEL_CHOICE_STORAGE_KEY, choiceId);
}

function getSelectedModelChoice() {
  const choiceId = getSelectedModelChoiceId();
  return getAvailableModelChoices().find((choice) => choice.id === choiceId) ?? getAvailableModelChoices()[0];
}

function getMimoEndpoint() {
  const choice = getSelectedModelChoice();
  if (choice.id === "deepseek") {
    return import.meta.env.DEV
      ? import.meta.env.VITE_DEEPSEEK_PROXY_PATH ?? DEFAULT_DEEPSEEK_PROXY_PATH
      : import.meta.env.VITE_DEEPSEEK_BASE_URL ?? DEFAULT_DEEPSEEK_BASE_URL;
  }
  return import.meta.env.DEV ? import.meta.env.VITE_MIMO_PROXY_PATH ?? DEFAULT_PROXY_PATH : import.meta.env.VITE_MIMO_BASE_URL ?? DEFAULT_BASE_URL;
}

function getMimoHeaders() {
  const choice = getSelectedModelChoice();
  const apiKey = choice.id === "deepseek" ? import.meta.env.VITE_DEEPSEEK_API_KEY : import.meta.env.VITE_MIMO_API_KEY;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (!import.meta.env.DEV && apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
  }

  return headers;
}

function assertMimoApiConfigured() {
  const choice = getSelectedModelChoice();
  if (!import.meta.env.DEV && choice.id === "mimo" && !import.meta.env.VITE_MIMO_API_KEY) {
    throw new Error("还没有配置 MiMo");
  }
  if (!import.meta.env.DEV && choice.id === "deepseek" && !import.meta.env.VITE_DEEPSEEK_API_KEY) {
    throw new Error("还没有配置 DeepSeek");
  }
}

async function requestMimoJson<T>(messages: Array<{ role: "system" | "user"; content: string }>, options: MimoRequestOptions = {}) {
  assertMimoApiConfigured();
  const model = getSelectedModelChoice().model;
  const maxTokens = options.maxTokens ?? 1024;
  const responseFormat = options.responseFormat ?? "json_object";
  const requestBody: Record<string, unknown> = {
    model,
    messages,
    max_completion_tokens: maxTokens,
    temperature: 0.2,
    top_p: 0.9,
    stream: false,
    frequency_penalty: 0,
    presence_penalty: 0,
  };

  if (responseFormat === "json_object") {
    requestBody.response_format = { type: "json_object" };
  }

  const response = await fetch(`${getMimoEndpoint()}/chat/completions`, {
    method: "POST",
    headers: getMimoHeaders(),
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    throw new Error(`当前模型请求失败：${response.status}`);
  }

  const data = (await response.json()) as MimoResponse;
  return parseJsonBlock<T>(extractAssistantText(data.choices?.[0]));
}

async function requestMimoJsonWithRetry<T>(
  messages: Array<{ role: "system" | "user"; content: string }>,
  preferredMaxTokens = 1024
) {
  try {
    return await requestMimoJson<T>(messages, {
      maxTokens: preferredMaxTokens,
      responseFormat: "json_object",
    });
  } catch (error) {
    const firstError = error instanceof Error ? error.message : String(error);

    return requestMimoJson<T>(messages, {
      maxTokens: Math.max(preferredMaxTokens, 1536),
      responseFormat: "text",
    }).catch((retryError) => {
      const secondError = retryError instanceof Error ? retryError.message : String(retryError);
      throw new Error(`当前模型解析失败：${firstError}；重试失败：${secondError}`);
    });
  }
}

export function inferRouteAdjustmentLocally(rawText: string): { action: RouteAdjustmentAction; note: string } {
  const text = rawText.trim().toLowerCase();
  if (!text) return { action: "unknown", note: "没有收到明确的调整要求。" };
  if (text.includes("排队") || text.includes("等待") || text.includes("少等")) {
    return { action: "lowQueue", note: "优先替换等待时间较高的地点。" };
  }
  if (text.includes("少走") || text.includes("近") || text.includes("距离") || text.includes("步行")) {
    return { action: "lessWalk", note: "优先压缩地点之间的步行距离。" };
  }
  if (text.includes("吃") || text.includes("餐") || text.includes("咖啡") || text.includes("饭")) {
    return { action: "moreFood", note: "增加餐饮占比，让路线更偏逛吃。" };
  }
  if (text.includes("文化") || text.includes("展") || text.includes("书店") || text.includes("艺术")) {
    return { action: "moreCulture", note: "增加文化空间占比。" };
  }
  if (text.includes("商场") || text.includes("购物") || text.includes("室内")) {
    return { action: "moreMall", note: "加入更稳妥的室内商场备选。" };
  }
  if (text.includes("轻松") || text.includes("慢") || text.includes("松一点")) {
    return { action: "relaxed", note: "放慢节奏，优先保证可执行。" };
  }
  if (text.includes("紧凑") || text.includes("快") || text.includes("压缩")) {
    return { action: "compact", note: "压缩停留和路线长度。" };
  }
  return { action: "unknown", note: "暂时无法识别调整目标，可以尝试说“少排队一点”或“少走路一点”。" };
}

function sanitizeRouteAdjustmentPatch(patch: RouteAdjustmentPatch, rawText: string) {
  const fallback = inferRouteAdjustmentLocally(rawText);
  const action = pickEnumValue(patch.action, ALLOWED_ROUTE_ADJUSTMENTS, fallback.action);
  return {
    action,
    note: patch.note?.trim() || fallback.note,
  };
}

export async function analyzeTravelIntentWithMimo(rawText: string, draftIntent: TravelIntent) {
  const patch = await requestMimoJsonWithRetry<ModelIntentPatch>(
    [
      {
        role: "system",
        content:
          "你是城市路线需求解析助手。你必须只输出一个合法 JSON 对象，不能输出解释、思考过程、Markdown、代码块或任何额外文字。字段必须使用这些英文枚举：startMode=now|planned，startPointMode=currentLocation|manual，budgetLevel=low|medium|high，pace=relaxed|balanced|compact。preferences 仅可使用：少排队、少走路、高评分、小众、适合拍照、体验轻松。poiTypes 仅可使用：餐饮、娱乐、商场、公园、文化。durationHours 输出 2 到 8 的整数。如果 rawText 里有“用户补充修改”或“修改”，最后一条修改必须覆盖之前的理解，例如“预算改成高”必须返回 budgetLevel=high。若用户没有明确提到某字段，请优先结合 rawText 推断，否则沿用 draft。除非用户明确说要用当前位置、当前定位、GPS 或 my location，否则 startPointMode 和 manualStartName 必须沿用 draft。若 startPointMode=manual 且没有 manualStartName，则使用 Philadelphia, PA, USA。返回格式固定为 {\"startMode\":\"now\",\"startPointMode\":\"manual\",\"manualStartName\":\"Philadelphia, PA, USA\",\"durationHours\":4,\"budgetLevel\":\"medium\",\"pace\":\"relaxed\",\"preferences\":[\"少排队\"],\"poiTypes\":[\"餐饮\",\"公园\",\"文化\"]}。",
      },
      {
        role: "user",
        content: JSON.stringify({
          rawText,
          draft: draftIntent,
        }),
      },
    ],
    1400
  );

  return applyDirectIntentOverrides(rawText, sanitizeIntentPatch(patch, draftIntent));
}

export async function parseRouteAdjustmentWithMimo(
  rawText: string,
  route: RoutePlan,
  routePois: Poi[],
  intent: TravelIntent | null
) {
  const patch = await requestMimoJsonWithRetry<RouteAdjustmentPatch>(
    [
        {
          role: "system",
          content:
          "你是城市路线二次调整解析助手。你必须只输出一个合法 JSON 对象，不能输出解释、思考过程、Markdown、代码块或任何额外文字。根据用户对当前路线的自然语言要求，在 action 中选择一个枚举：lowQueue=减少排队，lessWalk=少走路，moreFood=增加餐饮，moreCulture=增加文化点，moreMall=加入商场或室内点，relaxed=放慢节奏，compact=更紧凑，unknown=无法识别。note 输出一句中文说明，不超过 28 个字。返回结构固定为 {\"action\":\"lessWalk\",\"note\":\"优先压缩步行距离\"}。",
        },
        {
          role: "user",
          content: JSON.stringify({
            rawText,
            route: {
              name: route.name,
              totalDuration: route.totalDuration,
              totalDistance: route.totalDistance,
              totalQueueTime: route.totalQueueTime,
              status: route.status,
              poiNames: routePois.map((poi) => poi.name),
            },
            intent,
          }),
        },
      ],
    900
  );

  return sanitizeRouteAdjustmentPatch(patch, rawText);
}
