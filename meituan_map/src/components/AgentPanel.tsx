import { useEffect, useRef, useState } from "react";
import { useAppStore } from "../store/appStore";
import type { GenerationStage } from "../types";
import { IconChat, IconMinimize } from "./icons";

const EXPLANATION: Record<GenerationStage, string> = {
  idle: "我会先理解你的目的、时长和偏好，再把附近地点组合成可执行路线。",
  intent_parsing: "正在识别你的出行目标、预算、节奏和个人偏好。",
  poi_filtering: "正在优先筛选距离适中、排队较短、评价稳定的地点。",
  route_comparing: "正在比较地点顺序、步行距离、停留时间和等待风险。",
  route_generating: "正在生成效率优先、体验优先、低排队优先 3 条方案。",
  route_ready: "路线已生成。推荐先查看当前匹配度最高的路线，再按需要继续微调。",
};

const DESKTOP_MIN_WIDTH = 768;

export function AgentPanel() {
  const stage = useAppStore((s) => s.generationStage);
  const notices = useAppStore((s) => s.agentNotices);
  const generationEvents = useAppStore((s) => s.generationEvents);
  const isBackgroundEnriching = useAppStore((s) => s.isBackgroundEnriching);
  const panelRef = useRef<HTMLElement | null>(null);
  const dragPointerId = useRef<number | null>(null);
  const dragOffset = useRef({ x: 0, y: 0 });
  const [position, setPosition] = useState({ left: 24, top: 80 });
  const [isDragging, setIsDragging] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const clampToViewport = () => {
      const panel = panelRef.current;
      if (!panel || window.innerWidth <= DESKTOP_MIN_WIDTH) return;

      const rect = panel.getBoundingClientRect();
      const maxLeft = Math.max(16, window.innerWidth - rect.width - 16);
      const maxTop = Math.max(72, window.innerHeight - rect.height - 24);

      setPosition((current) => ({
        left: Math.min(Math.max(16, current.left), maxLeft),
        top: Math.min(Math.max(72, current.top), maxTop),
      }));
    };

    clampToViewport();
    window.addEventListener("resize", clampToViewport);
    return () => window.removeEventListener("resize", clampToViewport);
  }, []);

  const stopDragging = (pointerId?: number) => {
    if (pointerId != null && panelRef.current?.hasPointerCapture(pointerId)) {
      panelRef.current.releasePointerCapture(pointerId);
    }
    dragPointerId.current = null;
    setIsDragging(false);
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (window.innerWidth <= DESKTOP_MIN_WIDTH || !panelRef.current) return;

    dragPointerId.current = event.pointerId;
    dragOffset.current = {
      x: event.clientX - position.left,
      y: event.clientY - position.top,
    };
    panelRef.current.setPointerCapture(event.pointerId);
    setIsDragging(true);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLElement>) => {
    if (dragPointerId.current !== event.pointerId || !panelRef.current || window.innerWidth <= DESKTOP_MIN_WIDTH) return;

    const rect = panelRef.current.getBoundingClientRect();
    const maxLeft = Math.max(16, window.innerWidth - rect.width - 16);
    const maxTop = Math.max(72, window.innerHeight - rect.height - 24);
    const nextLeft = event.clientX - dragOffset.current.x;
    const nextTop = event.clientY - dragOffset.current.y;

    setPosition({
      left: Math.min(Math.max(16, nextLeft), maxLeft),
      top: Math.min(Math.max(72, nextTop), maxTop),
    });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLElement>) => {
    if (dragPointerId.current !== event.pointerId) return;
    stopDragging(event.pointerId);
  };

  if (isMinimized) {
    return (
      <button
        type="button"
        className="map-panel-orb map-panel-orb--agent"
        title="展开路线解释"
        aria-label="展开路线解释"
        onClick={() => setIsMinimized(false)}
      >
        <IconChat size={20} />
      </button>
    );
  }

  return (
    <aside
      ref={panelRef}
      className={`agent-panel${isDragging ? " is-dragging" : ""}`}
      style={{ left: `${position.left}px`, top: `${position.top}px` }}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      <div
        className="agent-panel__dragbar"
        role="button"
        tabIndex={0}
        aria-label="拖动 Agent 面板"
        onPointerDown={handlePointerDown}
      >
        <div>
          <span className="panel-kicker">Agent</span>
          <h2>路线解释</h2>
        </div>
        <button
          type="button"
          className="panel-icon-button"
          title="最小化路线解释"
          aria-label="最小化路线解释"
          onClick={() => setIsMinimized(true)}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <IconMinimize />
        </button>
      </div>
      <p>{EXPLANATION[stage]}</p>
      {generationEvents.length ? (
        <div className="agent-stream">
          <div className="agent-stream__header">
            <strong>实时规划进度</strong>
            <span className={isBackgroundEnriching ? "is-live" : ""}>
              {isBackgroundEnriching ? "深度分析中" : "已更新"}
            </span>
          </div>
          <ol>
            {generationEvents.slice(-6).map((event) => (
              <li key={`${event.requestId}-${event.sequence}`}>
                <span className={`generation-event-dot is-${event.type}`} />
                <span>{event.message}</span>
                <small>{(event.elapsedMs / 1000).toFixed(1)}s</small>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      {notices.length ? (
        <ul>
          {notices.map((notice, index) => (
            <li key={`${notice}-${index}`}>{notice}</li>
          ))}
        </ul>
      ) : null}
    </aside>
  );
}
