import { useState } from "react";
import type { Pace, StartMode, StartPointMode, TravelIntent } from "../types";
import { useAppStore } from "../store/appStore";
import { ToastHost } from "../components/ToastHost";
import {
  getAvailableModelChoices,
  getSelectedCommentModelChoiceId,
  getSelectedModelChoiceId,
  setSelectedCommentModelChoiceId,
  setSelectedModelChoiceId,
  type ModelChoiceId,
} from "../services/mimo";
import { parsePlannerIntent } from "../services/plannerBackend";
import { AccountEntryButton } from "../components/AccountEntryButton";
import { LocationPreviewMap } from "../components/LocationPreviewMap";
import { DEFAULT_LOCATION_LABEL, DEFAULT_MANUAL_START } from "../data/constants";

const DEFAULT_TEXT = "我今天下午想在费城玩 4 小时，想吃饭、逛公园、喝咖啡，不想排队太久";
const DEFAULT_POI_TYPES = ["餐饮", "公园", "文化"] as const;

const DEMO_TEXT = "我今天下午想在费城玩 4 个小时，想吃点东西、逛公园、看点有意思的文化空间，不想排队太久，预算中等。";

export function IntentPage() {
  const travelIntent = useAppStore((s) => s.travelIntent);
  const setTravelIntent = useAppStore((s) => s.setTravelIntent);
  const setCurrentView = useAppStore((s) => s.setCurrentView);
  const setGenerationStage = useAppStore((s) => s.setGenerationStage);
  const setPois = useAppStore((s) => s.setPois);
  const setRoutes = useAppStore((s) => s.setRoutes);
  const setActiveRoute = useAppStore((s) => s.setActiveRoute);
  const setVisiblePois = useAppStore((s) => s.setVisiblePois);
  const setSelectedPoi = useAppStore((s) => s.setSelectedPoi);
  const setDetailPoi = useAppStore((s) => s.setDetailPoi);
  const setBackendClarification = useAppStore((s) => s.setBackendClarification);
  const setBackendIntent = useAppStore((s) => s.setBackendIntent);
  const clearAgentNotices = useAppStore((s) => s.clearAgentNotices);
  const showToast = useAppStore((s) => s.showToast);

  const [rawText, setRawText] = useState(travelIntent?.rawText ?? DEFAULT_TEXT);
  const [startMode, setStartMode] = useState<StartMode>(travelIntent?.startMode ?? "now");
  const [startPointMode, setStartPointMode] = useState<StartPointMode>(travelIntent?.startPointMode ?? "manual");
  const [manualStartName, setManualStartName] = useState(travelIntent?.manualStartName ?? DEFAULT_MANUAL_START);
  const [durationHours, setDurationHours] = useState(travelIntent?.durationHours ?? 4);
  const [pace, setPace] = useState<Pace>(travelIntent?.pace ?? "relaxed");
  const [preferences, setPreferences] = useState<string[]>(travelIntent?.preferences ?? ["少排队", "少走路"]);
  const [modelChoice, setModelChoice] = useState<ModelChoiceId>(getSelectedModelChoiceId());
  const [commentModelChoice, setCommentModelChoice] = useState<ModelChoiceId>(getSelectedCommentModelChoiceId());
  const modelChoices = getAvailableModelChoices();
  const [approximateArea, setApproximateArea] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isMapExpanding, setIsMapExpanding] = useState(false);

  const locationPreviewTitle =
    startPointMode === "manual" ? manualStartName.trim() || DEFAULT_MANUAL_START : approximateArea || "当前位置";
  const locationPreviewHint =
    startPointMode === "manual"
      ? `将以 ${manualStartName.trim() || DEFAULT_MANUAL_START} 作为路线起点`
      : approximateArea
        ? `系统会从 ${approximateArea} 附近开始生成路线`
        : `选择后会请求定位权限；未开启时保留${DEFAULT_LOCATION_LABEL}`;
  const locationPreviewMode = startMode === "now" ? "现在出发" : "计划路线";

  const resetMapDraft = () => {
    setGenerationStage("idle");
    setPois([]);
    setRoutes([]);
    setActiveRoute(null);
    setVisiblePois([]);
    setSelectedPoi(null);
    setDetailPoi(null);
    clearAgentNotices();
  };

  const openMapReview = () => {
    resetMapDraft();
    setIsMapExpanding(true);
    window.setTimeout(() => setCurrentView("map"), 360);
  };

  const buildIntent = (confirmed = false): TravelIntent => ({
    rawText,
    startMode,
    startPointMode,
    manualStartName: startPointMode === "manual" ? manualStartName.trim() : undefined,
    durationHours,
    budgetLevel: travelIntent?.budgetLevel ?? "medium",
    pace,
    preferences,
    poiTypes: [...DEFAULT_POI_TYPES],
    confirmed,
  });

  const syncFormFromIntent = (intent: TravelIntent) => {
    setStartMode(intent.startMode);
    setStartPointMode(intent.startPointMode);
    setManualStartName(intent.manualStartName ?? DEFAULT_MANUAL_START);
    setDurationHours(intent.durationHours);
    setPace(intent.pace);
    setPreferences(intent.preferences);
  };

  const analyze = async () => {
    const draftIntent = buildIntent(false);
    setIsAnalyzing(true);
    setSelectedModelChoiceId(modelChoice);
    setSelectedCommentModelChoiceId(commentModelChoice);

    try {
      const clarification = await parsePlannerIntent(draftIntent, undefined, modelChoice);
      const reviewIntent = { ...draftIntent, confirmed: false };
      setTravelIntent(reviewIntent);
      setBackendIntent(clarification.intent);
      syncFormFromIntent(reviewIntent);
      setBackendClarification(clarification.needsClarification ? clarification : null);
      showToast("已经整理好这次计划");
    } catch {
      setTravelIntent(draftIntent);
      setBackendIntent(null);
      setBackendClarification(null);
      showToast("当前理解方式暂时不可用，已先保留你填写的内容");
    } finally {
      setIsAnalyzing(false);
      openMapReview();
    }
  };

  const startDemo = async () => {
    const demoIntent: TravelIntent = {
      rawText: DEMO_TEXT,
      startMode: "now",
      startPointMode: "manual",
      manualStartName: DEFAULT_MANUAL_START,
      durationHours: 4,
      budgetLevel: "medium",
      pace: "relaxed",
      preferences: ["少排队", "少走路", "体验轻松"],
      poiTypes: [...DEFAULT_POI_TYPES],
      confirmed: false,
    };

    setRawText(DEMO_TEXT);
    syncFormFromIntent(demoIntent);
    setIsAnalyzing(true);
    setSelectedModelChoiceId(modelChoice);
    setSelectedCommentModelChoiceId(commentModelChoice);
    try {
      const clarification = await parsePlannerIntent(demoIntent, undefined, modelChoice);
      setTravelIntent(demoIntent);
      setBackendIntent(clarification.intent);
      setBackendClarification(clarification.needsClarification ? clarification : null);
    } catch {
      setTravelIntent(demoIntent);
      setBackendIntent(null);
      setBackendClarification(null);
    } finally {
      setIsAnalyzing(false);
      openMapReview();
    }
  };

  return (
    <main className="intent-page">
      <header className="intent-nav">
        <strong>现在就出发</strong>
        <span>城市路线智能规划</span>
        <div className="intent-nav__spacer" />
        <AccountEntryButton />
      </header>

      <section className="intent-stage" aria-label="出行需求输入">
        <div className="intent-copy intent-store-hero">
          <h1>
            <span>路线都称心，</span>
            <br />
            体验更如意。
          </h1>
          <p>用一句话，把附近餐饮、公园和文化空间组合成可执行的城市路线。</p>

          <article className={`intent-location-card${isMapExpanding ? " is-map-expanding" : ""}`} aria-label="起点位置预览">
            <LocationPreviewMap
              startPointMode={startPointMode}
              manualStartName={manualStartName}
              onApproximateAreaChange={setApproximateArea}
            />
            <div className="intent-location-card__body">
              <div className="intent-location-card__meta">
                <span className="intent-location-card__eyebrow">{locationPreviewMode}</span>
                <span className="intent-location-card__badge">
                  {startPointMode === "manual" ? "手动输入" : "当前位置"}
                </span>
              </div>
              <strong>{locationPreviewTitle}</strong>
              <p>{locationPreviewHint}</p>
            </div>
          </article>
        </div>

        <div className="intent-card intent-store-card intent-store-card--primary">
          <span className="intent-card__eyebrow">开始规划</span>
          <h2>今天想怎么出发？</h2>

          <label className="intent-field">
            <span>出行需求</span>
            <textarea value={rawText} onChange={(event) => setRawText(event.target.value)} rows={5} />
          </label>

          <p className="intent-helper">描述你想去的类型、时长和节奏，系统会把它组合成一条可演示的城市路线。</p>

          <div className="intent-model-grid">
            <label className="intent-field intent-model-field">
              <span>理解行程模型</span>
              <select value={modelChoice} onChange={(event) => setModelChoice(event.target.value as ModelChoiceId)}>
                {modelChoices.map((choice) => (
                  <option value={choice.id} key={choice.id}>
                    {choice.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="intent-field intent-model-field">
              <span>解析评论模型</span>
              <select value={commentModelChoice} onChange={(event) => setCommentModelChoice(event.target.value as ModelChoiceId)}>
                {modelChoices.map((choice) => (
                  <option value={choice.id} key={choice.id}>
                    {choice.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="intent-grid">
            <SegmentedControl
              label="出发类型"
              value={startMode}
              options={[
                ["now", "现在出发"],
                ["planned", "计划路线"],
              ]}
              onChange={(value) => setStartMode(value as StartMode)}
            />
            <SegmentedControl
              label="起点"
              value={startPointMode}
              options={[
                ["currentLocation", "当前位置"],
                ["manual", "手动输入"],
              ]}
              onChange={(value) => setStartPointMode(value as StartPointMode)}
            />
            <SegmentedControl
              label="节奏"
              value={pace}
              options={[
                ["relaxed", "轻松"],
                ["balanced", "适中"],
                ["compact", "紧凑"],
              ]}
              onChange={(value) => setPace(value as Pace)}
            />
          </div>

          {startPointMode === "manual" ? (
            <label className="intent-field intent-manual-start">
              <span>手动输入起点</span>
              <input
                type="text"
                value={manualStartName}
                placeholder="例如：Philadelphia, PA, USA"
                onChange={(event) => setManualStartName(event.target.value)}
              />
            </label>
          ) : null}

          <label className="intent-range">
            <span>总时长：{durationHours} 小时</span>
            <input
              min={2}
              max={8}
              step={1}
              type="range"
              value={durationHours}
              onChange={(event) => setDurationHours(Number(event.target.value))}
            />
          </label>

          <div className="intent-actions">
            <button className="btn-primary" type="button" onClick={() => void analyze()} disabled={isAnalyzing}>
              {isAnalyzing ? "分析中..." : "分析需求"}
            </button>
          </div>

          <div className="intent-demo-entry">
            <button className="intent-demo-entry__button" type="button" onClick={() => void startDemo()} disabled={isAnalyzing}>
              启动演示流程
            </button>
          </div>
        </div>
      </section>

      <ToastHost />
    </main>
  );
}

function SegmentedControl({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="intent-segment">
      <span>{label}</span>
      <div
        className="intent-segment__control"
        role="group"
        aria-label={label}
        style={{ ["--segment-count" as string]: options.length }}
      >
        {options.map(([id, text]) => (
          <button
            key={id}
            type="button"
            aria-pressed={value === id}
            className={value === id ? "is-active" : ""}
            onClick={() => onChange(id)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
