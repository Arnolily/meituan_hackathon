import { useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { inferRouteAdjustmentLocally, parseRouteAdjustmentWithMimo } from "../services/mimo";
import { useAppStore } from "../store/appStore";
import type { Poi, RoutePlan } from "../types";
import { getPoisForRoute } from "../utils/routeCalculations";
import { PoiReplaceSheet } from "./PoiReplaceSheet";
import { IconMap, IconMinimize } from "./icons";

const DESKTOP_MIN_WIDTH = 768;
const PANEL_DESKTOP_WIDTH = 440;
const PANEL_RIGHT_GUTTER = 24;
const PANEL_MIN_GUTTER = 16;
const PANEL_INITIAL_TOP = 80;

function getInitialPanelPosition() {
  if (typeof window === "undefined") {
    return { left: 832, top: PANEL_INITIAL_TOP };
  }

  const estimatedWidth = Math.min(PANEL_DESKTOP_WIDTH, Math.max(0, window.innerWidth - PANEL_RIGHT_GUTTER * 2));
  return {
    left: Math.max(PANEL_MIN_GUTTER, window.innerWidth - estimatedWidth - PANEL_RIGHT_GUTTER),
    top: PANEL_INITIAL_TOP,
  };
}

export function RouteEditorPanel() {
  const routes = useAppStore((s) => s.routes);
  const pois = useAppStore((s) => s.pois);
  const activeRouteId = useAppStore((s) => s.activeRouteId);
  const selectedPoiId = useAppStore((s) => s.selectedPoiId);
  const travelIntent = useAppStore((s) => s.travelIntent);
  const setActiveRoute = useAppStore((s) => s.setActiveRoute);
  const setSelectedPoi = useAppStore((s) => s.setSelectedPoi);
  const reorderRoutePois = useAppStore((s) => s.reorderRoutePois);
  const removePoiFromRoute = useAppStore((s) => s.removePoiFromRoute);
  const updatePoiStayTime = useAppStore((s) => s.updatePoiStayTime);
  const updateRouteDurationTarget = useAppStore((s) => s.updateRouteDurationTarget);
  const startExecution = useAppStore((s) => s.startExecution);
  const setShareOpen = useAppStore((s) => s.setShareOpen);
  const applyRouteInstruction = useAppStore((s) => s.applyRouteInstruction);
  const saveRouteToHistory = useAppStore((s) => s.saveRouteToHistory);
  const showToast = useAppStore((s) => s.showToast);
  const [replacePoi, setReplacePoi] = useState<Poi | null>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const [routeInstruction, setRouteInstruction] = useState("");
  const [isApplyingInstruction, setIsApplyingInstruction] = useState(false);
  const panelRef = useRef<HTMLElement | null>(null);
  const dragPointerId = useRef<number | null>(null);
  const dragOffset = useRef({ x: 0, y: 0 });
  const hasDraggedPanel = useRef(false);
  const [panelPosition, setPanelPosition] = useState(getInitialPanelPosition);
  const [isDraggingPanel, setIsDraggingPanel] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);

  const openPoiDetail = (poiId: string) => {
    setReplacePoi(null);
    setSelectedPoi(poiId);
  };

  const openPoiReplacement = (poi: Poi) => {
    setSelectedPoi(null);
    setShareOpen(false);
    setReplacePoi(poi);
  };

  const openShare = () => {
    setReplacePoi(null);
    setShareOpen(true);
  };

  const activeRoute = routes.find((route) => route.id === activeRouteId) ?? routes[0];
  const activePois = activeRoute ? getPoisForRoute(activeRoute, pois) : [];
  const stopByPoi = new Map(activeRoute?.stops.map((stop) => [stop.poiId, stop]) ?? []);

  useLayoutEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const syncPosition = () => {
      const panel = panelRef.current;
      if (!panel || window.innerWidth <= DESKTOP_MIN_WIDTH) {
        return;
      }

      const rect = panel.getBoundingClientRect();
      const defaultLeft = Math.max(PANEL_MIN_GUTTER, window.innerWidth - rect.width - PANEL_RIGHT_GUTTER);
      const maxLeft = Math.max(PANEL_MIN_GUTTER, window.innerWidth - rect.width - PANEL_MIN_GUTTER);
      const maxTop = Math.max(72, window.innerHeight - rect.height - 24);

      setPanelPosition((current) => ({
        left: hasDraggedPanel.current ? Math.min(Math.max(PANEL_MIN_GUTTER, current.left), maxLeft) : defaultLeft,
        top: Math.min(Math.max(72, current.top), maxTop),
      }));
    };

    syncPosition();
    window.addEventListener("resize", syncPosition);

    return () => window.removeEventListener("resize", syncPosition);
  }, []);

  const finishDrag = () => {
    if (activeRoute && dragIndex !== null && overIndex !== null && dragIndex !== overIndex) {
      reorderRoutePois(activeRoute.id, dragIndex, overIndex);
    }
    setDragIndex(null);
    setOverIndex(null);
  };

  const stopPanelDrag = (pointerId?: number) => {
    if (pointerId != null && panelRef.current?.hasPointerCapture(pointerId)) {
      panelRef.current.releasePointerCapture(pointerId);
    }
    dragPointerId.current = null;
    setIsDraggingPanel(false);
  };

  const handlePanelPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (window.innerWidth <= DESKTOP_MIN_WIDTH || !panelRef.current) {
      return;
    }

    hasDraggedPanel.current = true;
    dragPointerId.current = event.pointerId;
    dragOffset.current = {
      x: event.clientX - panelPosition.left,
      y: event.clientY - panelPosition.top,
    };
    panelRef.current.setPointerCapture(event.pointerId);
    setIsDraggingPanel(true);
  };

  const handlePanelPointerMove = (event: React.PointerEvent<HTMLElement>) => {
    if (dragPointerId.current !== event.pointerId || !panelRef.current || window.innerWidth <= DESKTOP_MIN_WIDTH) {
      return;
    }

    const rect = panelRef.current.getBoundingClientRect();
    const maxLeft = Math.max(16, window.innerWidth - rect.width - 16);
    const maxTop = Math.max(72, window.innerHeight - rect.height - 24);
    const nextLeft = event.clientX - dragOffset.current.x;
    const nextTop = event.clientY - dragOffset.current.y;

    setPanelPosition({
      left: Math.min(Math.max(16, nextLeft), maxLeft),
      top: Math.min(Math.max(72, nextTop), maxTop),
    });
  };

  const handlePanelPointerUp = (event: React.PointerEvent<HTMLElement>) => {
    if (dragPointerId.current !== event.pointerId) {
      return;
    }
    stopPanelDrag(event.pointerId);
  };

  const handleRouteInstruction = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const instruction = routeInstruction.trim();
    if (!activeRoute || !instruction || isApplyingInstruction) return;

    setIsApplyingInstruction(true);
    try {
      const parsed = await parseRouteAdjustmentWithMimo(instruction, activeRoute, activePois, travelIntent);
      applyRouteInstruction(activeRoute.id, parsed.action, parsed.note);
    } catch {
      const parsed = inferRouteAdjustmentLocally(instruction);
      applyRouteInstruction(activeRoute.id, parsed.action, parsed.note);
      showToast("模型暂不可用，已用本地规则完成微调");
    } finally {
      setRouteInstruction("");
      setIsApplyingInstruction(false);
    }
  };

  if (isMinimized) {
    return (
      <button
        type="button"
        className="map-panel-orb map-panel-orb--route"
        title="展开路线方案"
        aria-label="展开路线方案"
        onClick={() => setIsMinimized(false)}
      >
        <IconMap size={20} />
      </button>
    );
  }

  return (
    <aside
      ref={panelRef}
      className={`route-editor${isDraggingPanel ? " is-dragging" : ""}`}
      style={{ left: `${panelPosition.left}px`, top: `${panelPosition.top}px` }}
      onPointerMove={handlePanelPointerMove}
      onPointerUp={handlePanelPointerUp}
      onPointerCancel={handlePanelPointerUp}
    >
      <div className="route-editor__sticky">
        <div
          className="route-editor__dragbar"
          role="button"
          tabIndex={0}
          aria-label="拖动路线面板"
          onPointerDown={handlePanelPointerDown}
        >
          <div className="route-editor__head">
            <span className="panel-kicker">路线方案</span>
            <h2>{activeRoute ? `${routes.length} 条路线已生成` : "正在生成路线"}</h2>
          </div>
          <button
            type="button"
            className="panel-icon-button"
            title="最小化路线方案"
            aria-label="最小化路线方案"
            onClick={() => setIsMinimized(true)}
            onPointerDown={(event) => event.stopPropagation()}
          >
            <IconMinimize />
          </button>
        </div>

        {activeRoute ? (
          <div className="route-editor__titlebar">
            <strong>{activeRoute.name}</strong>
            <span>
              {activeRoute.totalDuration} 分钟｜{activeRoute.totalDistance.toFixed(1)} 公里｜排队 {activeRoute.totalQueueTime} 分钟
            </span>
          </div>
        ) : null}
      </div>

      <div className="route-cards">
        {routes.map((route) => (
          <RoutePlanCard key={route.id} route={route} selected={route.id === activeRoute?.id} onSelect={() => setActiveRoute(route.id)} />
        ))}
      </div>

      {activeRoute ? (
        <>
          <div className="route-summary">
            <strong>{activeRoute.name}</strong>
            <span>
              {activeRoute.totalDuration} 分钟｜{activeRoute.totalDistance.toFixed(1)} 公里｜排队 {activeRoute.totalQueueTime} 分钟｜人均 ¥
              {activeRoute.avgCost}｜{activeRoute.status}
            </span>
            {activeRoute.preferenceScore ? (
              <span className="route-summary__match">个人偏好匹配度 {activeRoute.preferenceScore} 分</span>
            ) : null}
            {activeRoute.preferenceReason ? <p className="route-summary__reason">{activeRoute.preferenceReason}</p> : null}
          </div>

          <form className="route-ai-box" onSubmit={handleRouteInstruction}>
            <label htmlFor="routeInstruction">
              <span>用模型二次调整</span>
              <input
                id="routeInstruction"
                value={routeInstruction}
                onChange={(event) => setRouteInstruction(event.target.value)}
                placeholder="例如：少走路一点 / 换成少排队 / 加一个商场"
              />
            </label>
            <button type="submit" className="btn-primary" disabled={!routeInstruction.trim() || isApplyingInstruction}>
              {isApplyingInstruction ? "调整中..." : "应用微调"}
            </button>
          </form>

          <label className="route-duration">
            <span>目标总时长：{travelIntent?.durationHours ?? 4} 小时</span>
            <input
              type="range"
              min={2}
              max={8}
              step={1}
              value={travelIntent?.durationHours ?? 4}
              onChange={(event) => updateRouteDurationTarget(Number(event.target.value))}
            />
          </label>

          <div className="route-timeline">
            {activePois.map((poi, index) => (
              <article
                key={poi.id}
                className={[
                  "poi-item",
                  poi.commentParsed ? "poi-item--commented" : "poi-item--uncommented",
                  selectedPoiId === poi.id ? "is-selected" : "",
                  dragIndex === index ? "is-dragging" : "",
                  overIndex === index ? "is-over" : "",
                ].filter(Boolean).join(" ")}
                onPointerEnter={() => dragIndex !== null && setOverIndex(index)}
                onPointerUp={finishDrag}
              >
                <button
                  type="button"
                  className="poi-item__drag"
                  aria-label={`拖拽 ${poi.name}`}
                  onPointerDown={(event) => {
                    event.currentTarget.setPointerCapture(event.pointerId);
                    setDragIndex(index);
                    setOverIndex(index);
                  }}
                  onPointerUp={finishDrag}
                >
                  {index + 1}
                </button>
                <div className="poi-item__body">
                  <div className="poi-item__title">
                    <strong>{poi.name}</strong>
                    <span>{poi.type}</span>
                  </div>
                  <p>
                    {stopByPoi.get(poi.id)?.arriveTime} - {stopByPoi.get(poi.id)?.leaveTime}｜停留 {poi.stayTime} 分钟｜步行{" "}
                    {stopByPoi.get(poi.id)?.walkMinutes ?? 0} 分钟｜排队 {poi.queueTime} 分钟｜人均 ¥{poi.avgPrice}
                  </p>
                  <div className="poi-item__comment">
                    <span className={["poi-comment-badge", poi.commentParsed ? "poi-comment-badge--ready" : "poi-comment-badge--missing"].join(" ")}>
                      {poi.commentParsed ? "已解析评论" : "未解析评论"}
                    </span>
                    <p>{poi.reviewSummary[0]}</p>
                    {poi.riskNotes[0] ? <small>风险：{poi.riskNotes[0]}</small> : null}
                  </div>
                  <input
                    type="range"
                    min={30}
                    max={90}
                    step={5}
                    value={poi.stayTime}
                    onChange={(event) => updatePoiStayTime(poi.id, Number(event.target.value))}
                    aria-label={`${poi.name} 停留时间`}
                  />
                  <div className="poi-item__actions">
                    <button type="button" className="btn-secondary" onClick={() => openPoiDetail(poi.id)}>
                      详情
                    </button>
                    <button type="button" className="btn-secondary" onClick={() => openPoiReplacement(poi)}>
                      替换
                    </button>
                    <button type="button" className="btn-secondary" onClick={() => removePoiFromRoute(activeRoute.id, poi.id)}>
                      删除
                    </button>
                    <button type="button" className="btn-secondary" disabled={index === 0} onClick={() => reorderRoutePois(activeRoute.id, index, index - 1)}>
                      上移
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={index === activePois.length - 1}
                      onClick={() => reorderRoutePois(activeRoute.id, index, index + 1)}
                    >
                      下移
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>

          <div className="route-editor__actions">
            <button type="button" className="btn-primary" onClick={() => startExecution(activeRoute.id)}>
              进入执行模式
            </button>
            <button type="button" className="btn-secondary" onClick={() => saveRouteToHistory(activeRoute.id)}>
              保存路线
            </button>
            <button type="button" className="btn-secondary" onClick={openShare}>
              分享路线
            </button>
          </div>
        </>
      ) : null}

      {replacePoi && activeRoute ? <PoiReplaceSheet route={activeRoute} poi={replacePoi} onClose={() => setReplacePoi(null)} /> : null}
    </aside>
  );
}

function RoutePlanCard({ route, selected, onSelect }: { route: RoutePlan; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={["route-card-v2", selected ? "is-active" : ""].filter(Boolean).join(" ")} onClick={onSelect}>
      <span>{route.name}</span>
      <strong>
        {Math.floor(route.totalDuration / 60)}小时{route.totalDuration % 60}分｜{route.poiIds.length}个地点｜{route.totalDistance.toFixed(1)} 公里
      </strong>
      <small>
        排队 {route.totalQueueTime} 分钟｜人均 ¥{route.avgCost}｜{route.status}
      </small>
      {route.preferenceScore ? <b className="route-card-v2__score">偏好匹配 {route.preferenceScore} 分</b> : null}
      {route.preferenceTags?.length ? (
        <span className="route-card-v2__tags">
          {route.preferenceTags.map((tag) => (
            <em key={tag}>{tag}</em>
          ))}
        </span>
      ) : null}
      {route.preferenceReason ? <small className="route-card-v2__reason">{route.preferenceReason}</small> : null}
      <p>{route.reason}</p>
    </button>
  );
}
