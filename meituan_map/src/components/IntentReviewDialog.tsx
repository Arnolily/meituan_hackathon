import { useEffect, useState } from "react";
import {
  getAvailableModelChoices,
  getSelectedCommentModelChoiceId,
  getSelectedModelChoiceId,
  setSelectedCommentModelChoiceId,
  setSelectedModelChoiceId,
  type ModelChoiceId,
} from "../services/mimo";
import { useAppStore } from "../store/appStore";
import type { Pace, TravelIntent } from "../types";
import { describeRoutePreferences } from "../types/routePreferences";
import { parsePlannerIntent, type BackendIntentEvent, type BackendIntentSummary } from "../services/plannerBackend";

function paceLabel(value: Pace) {
  if (value === "compact") return "紧凑";
  if (value === "balanced") return "适中";
  return "轻松";
}

function budgetLabel(value: string | undefined) {
  if (value === "low") return "低预算";
  if (value === "medium") return "中等预算";
  if (value === "high") return "高预算";
  return "预算待确认";
}

function eventGoalLabel(value: string | undefined) {
  const labels: Record<string, string> = {
    breakfast: "早餐",
    coffee: "咖啡",
    lunch: "午餐",
    dinner: "晚餐",
    dessert: "甜品",
    drinks: "饮品",
    nightlife: "夜生活",
    shopping: "购物",
    sightseeing: "观光",
    museum: "博物馆",
    park: "公园",
    historical_site: "历史地点",
    art_gallery: "艺术空间",
    performance: "演出",
    tour: "游览",
    family_activity: "亲子活动",
    games: "娱乐活动",
  };
  return value ? labels[value] ?? value.replace(/_/g, " ") : "行程";
}

function categoryLabel(value: string) {
  const labels: Record<string, string> = {
    Chinese: "中餐",
    Japanese: "日料",
    Italian: "意餐",
    Mexican: "墨西哥菜",
    Indian: "印度菜",
    Korean: "韩餐",
    Vietnamese: "越南菜",
    Seafood: "海鲜",
    Restaurants: "餐厅",
    Food: "餐饮",
    "Breakfast & Brunch": "早午餐",
    "Coffee & Tea": "咖啡或茶饮",
    Cafes: "咖啡馆",
    Museums: "博物馆",
    "Art Museums": "艺术博物馆",
    "Art Galleries": "画廊或艺术空间",
    Parks: "公园",
    "Shopping Centers": "购物中心",
    "Arts & Entertainment": "文化娱乐空间",
    Arcades: "游戏厅",
  };
  return labels[value] ?? value.replace(/ & /g, "和");
}

function eventTitle(event: BackendIntentEvent, index: number) {
  return event.name || eventGoalLabel(event.goal) || `第 ${index + 1} 段`;
}

function eventDescription(event: BackendIntentEvent) {
  const parts = [
    ...(event.categories ?? []).slice(0, 2).map(categoryLabel),
    budgetLabel(event.budget_level),
    ...(event.soft_preferences ?? []).slice(0, 1),
  ].filter(Boolean);
  return parts.join("，") || "偏好待确认";
}

function comparableIntent(intent: TravelIntent, parsed: BackendIntentSummary | null) {
  return JSON.stringify({
    rawText: intent.rawText,
    startMode: intent.startMode,
    startPointMode: intent.startPointMode,
    manualStartName: intent.manualStartName ?? "",
    durationHours: intent.durationHours,
    pace: intent.pace,
    preferences: intent.preferences,
    poiTypes: intent.poiTypes,
    events: parsed?.events?.map((event) => ({
      name: event.name ?? "",
      goal: event.goal,
      categories: event.categories ?? [],
      budget: event.budget_level ?? "",
      targetArea: event.target_area ?? "",
    })) ?? [],
  });
}

export function IntentReviewDialog() {
  const travelIntent = useAppStore((s) => s.travelIntent);
  const backendIntent = useAppStore((s) => s.backendIntent);
  const routePreferences = useAppStore((s) => s.routePreferences);
  const setTravelIntent = useAppStore((s) => s.setTravelIntent);
  const confirmTravelIntent = useAppStore((s) => s.confirmTravelIntent);
  const setCurrentView = useAppStore((s) => s.setCurrentView);
  const setGenerationStage = useAppStore((s) => s.setGenerationStage);
  const setPois = useAppStore((s) => s.setPois);
  const setRoutes = useAppStore((s) => s.setRoutes);
  const setActiveRoute = useAppStore((s) => s.setActiveRoute);
  const setVisiblePois = useAppStore((s) => s.setVisiblePois);
  const setSelectedPoi = useAppStore((s) => s.setSelectedPoi);
  const setDetailPoi = useAppStore((s) => s.setDetailPoi);
  const clearAgentNotices = useAppStore((s) => s.clearAgentNotices);
  const setBackendClarification = useAppStore((s) => s.setBackendClarification);
  const setBackendIntent = useAppStore((s) => s.setBackendIntent);
  const showToast = useAppStore((s) => s.showToast);
  const [editableText, setEditableText] = useState(travelIntent?.rawText ?? "");
  const [parsedIntent, setParsedIntent] = useState<BackendIntentSummary | null>(backendIntent);
  const [isReparsing, setIsReparsing] = useState(false);
  const [modelChoice, setModelChoice] = useState<ModelChoiceId>(getSelectedModelChoiceId());
  const [commentModelChoice, setCommentModelChoice] = useState<ModelChoiceId>(getSelectedCommentModelChoiceId());
  const modelChoices = getAvailableModelChoices();

  const resetRouteWorkspace = () => {
    setGenerationStage("idle");
    setPois([]);
    setRoutes([]);
    setActiveRoute(null);
    setVisiblePois([]);
    setSelectedPoi(null);
    setDetailPoi(null);
    clearAgentNotices();
  };

  const handleBack = () => {
    resetRouteWorkspace();
    setCurrentView("intent");
  };

  useEffect(() => {
    if (!travelIntent || travelIntent.confirmed) return;
    setEditableText(travelIntent.rawText);
  }, [travelIntent?.rawText, travelIntent, travelIntent?.confirmed]);

  useEffect(() => {
    setParsedIntent(backendIntent);
  }, [backendIntent]);

  useEffect(() => {
    if (!travelIntent || travelIntent.confirmed) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleBack();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  if (!travelIntent || travelIntent.confirmed) return null;

  const reparseText = async (text: string) => {
    const nextIntent = { ...travelIntent, rawText: text, confirmed: false };
    const clarification = await parsePlannerIntent(nextIntent, undefined, modelChoice);
    setTravelIntent(nextIntent);
    setBackendIntent(clarification.intent);
    setParsedIntent(clarification.intent);
    setBackendClarification(clarification.needsClarification ? clarification : null);
    return { nextIntent, parsed: clarification.intent };
  };

  const handleReparse = async () => {
    if (isReparsing) return;
    setIsReparsing(true);
    setSelectedModelChoiceId(modelChoice);
    setSelectedCommentModelChoiceId(commentModelChoice);
    try {
      const before = comparableIntent(travelIntent, parsedIntent);
      const text = editableText.trim() || travelIntent.rawText;
      const result = await reparseText(text);
      const after = comparableIntent(result.nextIntent, result.parsed);
      showToast(before === after ? "这次理解结果没有变化" : "已经重新整理计划");
    } catch {
      showToast("当前理解方式暂时不可用，计划没有改变");
    } finally {
      setIsReparsing(false);
    }
  };

  const handleConfirm = () => {
    resetRouteWorkspace();
    setSelectedModelChoiceId(modelChoice);
    setSelectedCommentModelChoiceId(commentModelChoice);
    confirmTravelIntent();
  };

  return (
    <section className="intent-review-shell" aria-label="确认出行计划">
      <div className="intent-review-dialog" role="dialog" aria-modal="true" aria-labelledby="intent-review-title">
        <p className="intent-confirm__eyebrow">我理解你的需求是</p>
        <h2 id="intent-review-title">先确认这次计划，再开始生成路线。</h2>
        <p className="intent-review-dialog__summary">
          {travelIntent.startPointMode === "currentLocation" ? "当前位置附近" : travelIntent.manualStartName || "手动起点附近"}，
          安排一条约 {travelIntent.durationHours} 小时的城市休闲路线。
        </p>

        <label className="intent-review-text">
          <span>这次出行需求</span>
          <textarea value={editableText} onChange={(event) => setEditableText(event.target.value)} rows={3} />
        </label>

        {parsedIntent?.events?.length ? (
          <div className="intent-review-events" aria-label="分段理解结果">
            {parsedIntent.events.map((event, index) => (
              <article className="intent-review-event" key={`${event.goal}-${index}`}>
                <strong>{eventTitle(event, index)}</strong>
                <span>{eventDescription(event)}</span>
              </article>
            ))}
          </div>
        ) : null}

        <dl className="intent-review-list">
          <div><dt>出发方式</dt><dd>{travelIntent.startMode === "now" ? "现在出发" : "计划路线"}</dd></div>
          <div><dt>起点</dt><dd>{travelIntent.startPointMode === "currentLocation" ? "当前位置" : travelIntent.manualStartName || "手动输入起点"}</dd></div>
          <div><dt>节奏</dt><dd>{paceLabel(travelIntent.pace)}</dd></div>
          <div><dt>想去类型</dt><dd>{travelIntent.poiTypes.join("、")}</dd></div>
          <div><dt>核心偏好</dt><dd>{travelIntent.preferences.join("、") || "按默认偏好"}</dd></div>
          <div><dt>长期偏好</dt><dd>{describeRoutePreferences(routePreferences)}</dd></div>
        </dl>

        <div className="intent-review-model">
          <label>
            <span>理解行程模型</span>
            <select value={modelChoice} onChange={(event) => setModelChoice(event.target.value as ModelChoiceId)}>
              {modelChoices.map((choice) => (
                <option value={choice.id} key={choice.id}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>解析评论模型</span>
            <select value={commentModelChoice} onChange={(event) => setCommentModelChoice(event.target.value as ModelChoiceId)}>
              {modelChoices.map((choice) => (
                <option value={choice.id} key={choice.id}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn-secondary" onClick={() => void handleReparse()} disabled={isReparsing}>
            {isReparsing ? "正在重新理解..." : "重新理解这句话"}
          </button>
        </div>

        <div className="intent-review-actions">
          <button type="button" className="btn-secondary" onClick={handleBack}>
            返回首页修改
          </button>
          <button type="button" className="btn-primary" onClick={handleConfirm}>
            确认并生成路线
          </button>
        </div>
      </div>
    </section>
  );
}
