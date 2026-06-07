import { useState } from "react";
import { useAppStore } from "../store/appStore";
import { ToastHost } from "../components/ToastHost";
import { ShareModal } from "../components/ShareModal";
import { getPoisForRoute } from "../utils/routeCalculations";
import { PoiReplaceSheet } from "../components/PoiReplaceSheet";

export function ExecutionPage() {
  const routes = useAppStore((s) => s.routes);
  const pois = useAppStore((s) => s.pois);
  const executionRouteId = useAppStore((s) => s.executionRouteId);
  const currentStepIndex = useAppStore((s) => s.currentStepIndex);
  const executionArrived = useAppStore((s) => s.executionArrived);
  const markExecutionArrived = useAppStore((s) => s.markExecutionArrived);
  const advanceExecutionStep = useAppStore((s) => s.advanceExecutionStep);
  const skipExecutionStep = useAppStore((s) => s.skipExecutionStep);
  const endExecution = useAppStore((s) => s.endExecution);
  const setShareOpen = useAppStore((s) => s.setShareOpen);
  const setAccountSidebarOpen = useAppStore((s) => s.setAccountSidebarOpen);
  const [replaceOpen, setReplaceOpen] = useState(false);
  const route = routes.find((item) => item.id === executionRouteId) ?? routes[0];
  const routePois = route ? getPoisForRoute(route, pois) : [];
  const currentPoi = routePois[currentStepIndex];
  const nextPoi = routePois[currentStepIndex + 1];
  const currentStop = route?.stops[currentStepIndex];
  const nextStop = route?.stops[currentStepIndex + 1];

  const openReplacement = () => {
    setShareOpen(false);
    setAccountSidebarOpen(false);
    setReplaceOpen(true);
  };

  const openShare = () => {
    setReplaceOpen(false);
    setShareOpen(true);
  };

  return (
    <div className="execution-shell">
      <header className="execution-topbar">
        <strong>{route?.name ?? "执行模式"}</strong>
        <span>进度 {Math.min(currentStepIndex + 1, routePois.length)} / {routePois.length}</span>
      </header>

      {route && currentPoi ? (
        <section className="execution-card">
          <span className="panel-kicker">{executionArrived ? "已到达" : "执行中"}</span>
          <h1>{currentPoi.name}</h1>
          <p>建议停留 {currentPoi.stayTime} 分钟｜建议离开 {currentStop?.leaveTime}</p>
          {nextPoi ? (
            <div className="execution-next">
              <span>下一站</span>
              <strong>{nextPoi.name}</strong>
              <small>步行约 {nextStop?.walkMinutes ?? 12} 分钟｜预计到达 {nextStop?.arriveTime}</small>
            </div>
          ) : (
            <div className="execution-next">
              <span>行程即将完成</span>
              <strong>这是最后一站</strong>
            </div>
          )}

          {currentStepIndex >= 1 && nextPoi ? (
            <div className="execution-risk">
              下一站“{nextPoi.name}”预计排队增加，你可以替换为附近等待更少的地点。
            </div>
          ) : null}

          <div className="execution-actions">
            <button type="button" className={executionArrived ? "btn-secondary" : "btn-primary"} onClick={markExecutionArrived}>我已到达</button>
            <button type="button" className={executionArrived ? "btn-primary" : "btn-secondary"} onClick={advanceExecutionStep}>我已离开 / 下一站</button>
            <button type="button" className="btn-secondary" onClick={skipExecutionStep}>跳过此站</button>
            <button type="button" className="btn-secondary" disabled={!nextPoi} onClick={openReplacement}>替换下一站</button>
            <button type="button" className="btn-secondary" onClick={openShare}>分享路线</button>
            <button type="button" className="btn-secondary" onClick={endExecution}>结束行程</button>
          </div>
        </section>
      ) : null}

      {replaceOpen && route && nextPoi ? <PoiReplaceSheet route={route} poi={nextPoi} onClose={() => setReplaceOpen(false)} /> : null}
      <ShareModal />
      <ToastHost />
    </div>
  );
}
