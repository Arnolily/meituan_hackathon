import { useEffect, useRef } from "react";
import { useAppStore } from "../store/appStore";
import type { PlannerStreamEvent } from "../services/plannerBackend";

interface ModelOutputLine {
  id: string;
  kind: "analysis" | "route" | "poi" | "review" | "notice" | "warning";
  text: string;
}

function modelOutputLines(events: PlannerStreamEvent[]): ModelOutputLine[] {
  const lines: ModelOutputLine[] = [];
  const seen = new Set<string>();
  const push = (line: ModelOutputLine) => {
    const key = `${line.kind}:${line.text}`;
    if (!seen.has(key)) {
      seen.add(key);
      lines.push(line);
    }
  };

  events.forEach((event) => {
    if (event.type === "analysis") {
      push({ id: `${event.requestId}-${event.sequence}`, kind: "analysis", text: event.message });
    }
    if (event.type === "warning" || event.type === "error") {
      push({ id: `${event.requestId}-${event.sequence}`, kind: "warning", text: event.message });
    }
    const data = event.data;
    if (!data || !("routes" in data) || !("pois" in data)) return;
    const prefix = event.type === "partial_result" ? "快速规划" : "深度分析";
    data.agentNotices?.forEach((notice, index) => {
      push({ id: `${event.requestId}-${event.sequence}-notice-${index}`, kind: "notice", text: notice });
    });
    data.routes.forEach((route, index) => {
      push({
        id: `${event.requestId}-${event.sequence}-route-${route.id}`,
        kind: "route",
        text: `${prefix}路线 ${index + 1}：${route.name}。${route.reason || route.preferenceReason || "已完成路线组合。"}`,
      });
    });
    data.pois.slice(0, 8).forEach((poi) => {
      push({
        id: `${event.requestId}-${event.sequence}-poi-${poi.id}`,
        kind: "poi",
        text: `候选地点：${poi.name}，评分 ${poi.rating}，预计排队 ${poi.queueTime} 分钟。${poi.recommendReason}`,
      });
      poi.reviewSummary.slice(0, 1).forEach((summary, index) => {
        push({
          id: `${event.requestId}-${event.sequence}-cached-review-${poi.id}-${index}`,
          kind: "review",
          text: `${poi.name} 缓存评论摘要：${summary}`,
        });
      });
    });
  });

  return lines.slice(-80);
}

export function GenerationOverlay() {
  const stage = useAppStore((s) => s.generationStage);
  const text = useAppStore((s) => s.generationProgressText);
  const progress = useAppStore((s) => s.generationProgress);
  const events = useAppStore((s) => s.generationEvents);
  const panelMode = useAppStore((s) => s.generationPanelMode);
  const setPanelMode = useAppStore((s) => s.setGenerationPanelMode);
  const cancelGeneration = useAppStore((s) => s.cancelGeneration);
  const streamRef = useRef<HTMLUListElement>(null);

  const outputLines = modelOutputLines(events);
  const hasFastResult = events.some((event) => event.type === "partial_result");
  const completed = stage === "route_ready";

  useEffect(() => {
    const stream = streamRef.current;
    if (stream) stream.scrollTo({ top: stream.scrollHeight, behavior: "smooth" });
  }, [outputLines.length]);

  if (panelMode === "closed" || (!events.length && stage === "idle")) return null;

  if (panelMode === "docked") {
    return (
      <aside className="generation-dock" aria-live="polite">
        <button type="button" className="generation-dock__main" onClick={() => setPanelMode("open")}>
          <span className={`generation-dock__status ${completed ? "is-complete" : ""}`} aria-hidden />
          <span>
            <strong>{completed ? "路线生成完成" : text}</strong>
            <small>{outputLines.length} 条生成记录 · 点击展开</small>
          </span>
          <b>{progress}%</b>
        </button>
        <button type="button" className="generation-dock__close" aria-label="关闭生成记录" onClick={() => setPanelMode("closed")}>
          ×
        </button>
      </aside>
    );
  }

  return (
    <section className={`generation-overlay ${completed ? "is-complete" : ""}`} aria-live="polite">
      <div className="generation-overlay__head">
        <div className={completed ? "generation-complete-mark" : "generation-spinner"} aria-hidden>{completed ? "✓" : ""}</div>
        <div>
          <span className="generation-overlay__eyebrow">{completed ? "生成记录已保留" : "模型实时规划"}</span>
          <h2>{text}</h2>
          <p>{completed ? "路线已可查看，下面保留本次生成过程与模型输出。" : hasFastResult ? "快速路线已经生成，正在继续校验道路与地点顺序。" : "正在逐步理解需求并筛选附近地点，请稍候。"}</p>
        </div>
        <span className={`generation-overlay__live ${completed ? "is-complete" : ""}`}><i />{completed ? "已完成" : "实时输出"}</span>
      </div>
      <div className="generation-progress" aria-label={`生成进度 ${progress}%`}>
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="generation-progress__meta">
        <span>{hasFastResult ? "快速结果已可用，继续校验道路路线" : "等待第一批真实结果"}</span>
        <strong>{progress}%</strong>
      </div>
      <div className="generation-stream">
        <div className="generation-stream__title">
          <strong>实时分析摘要</strong>
          <span>{outputLines.length} 条内容</span>
        </div>
        {outputLines.length ? (
          <ul className="generation-event-list" ref={streamRef}>
            {outputLines.map((line) => (
              <li key={line.id} className={`is-${line.kind}`}>
                <span className="generation-event-dot" />
                <span>{line.text}</span>
              </li>
            ))}
            {!completed ? (
              <li className="generation-stream__thinking" aria-label="模型仍在生成">
                <span className="generation-event-dot" />
                <span>正在等待下一段分析摘要<i /></span>
              </li>
            ) : null}
          </ul>
        ) : (
          <div className="generation-stream__empty">
            正在等待第一段分析摘要<span className="generation-stream__cursor" />
          </div>
        )}
      </div>
      <div className="generation-overlay__actions">
        {!completed ? <button type="button" className="generation-cancel" onClick={cancelGeneration}>停止生成</button> : null}
        <button type="button" className="generation-collapse" onClick={() => setPanelMode("docked")}>{completed ? "查看路线并收起记录" : "收起到侧边"}</button>
        {completed ? <button type="button" className="generation-close" onClick={() => setPanelMode("closed")}>关闭记录</button> : null}
      </div>
    </section>
  );
}
