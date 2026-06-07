import { useEffect } from "react";
import { useAppStore } from "../store/appStore";
import { ToastHost } from "../components/ToastHost";
import { ShareModal } from "../components/ShareModal";
import { GenerationOverlay } from "../components/GenerationOverlay";
import { AgentPanel } from "../components/AgentPanel";
import { RouteEditorPanel } from "../components/RouteEditorPanel";
import { PoiDetailPanel } from "../components/PoiDetailPanel";
import { IntentReviewDialog } from "../components/IntentReviewDialog";
import { BackendClarificationDialog } from "../components/BackendClarificationDialog";

export function MapRoutePage() {
  const generationStage = useAppStore((s) => s.generationStage);
  const generationPanelMode = useAppStore((s) => s.generationPanelMode);
  const routesLength = useAppStore((s) => s.routes.length);
  const travelIntent = useAppStore((s) => s.travelIntent);
  const backendClarification = useAppStore((s) => s.backendClarification);
  const shareOpen = useAppStore((s) => s.shareOpen);
  const detailPoi = useAppStore((s) => s.detailPoi);
  const intentConfirmed = travelIntent?.confirmed;
  const runDemoGeneration = useAppStore((s) => s.runDemoGeneration);
  const showReview = Boolean(travelIntent && !intentConfirmed);
  const showClarification = Boolean(intentConfirmed && backendClarification);
  const generationActive = generationStage !== "idle" && generationStage !== "route_ready" && generationPanelMode === "open";
  const activeOverlay = showClarification
    ? "clarification"
    : showReview
      ? "review"
      : generationActive
        ? "generation"
        : shareOpen
          ? "share"
          : detailPoi
            ? "detail"
            : null;
  const showWorkspace = activeOverlay === null;
  const showRouteEditor = showWorkspace && routesLength > 0;

  useEffect(() => {
    if (intentConfirmed && !backendClarification && generationStage === "idle" && routesLength === 0) {
      void runDemoGeneration();
    }
  }, [backendClarification, generationStage, intentConfirmed, routesLength, runDemoGeneration]);

  return (
    <div className="mvp-map-shell">
      {showWorkspace ? <AgentPanel /> : null}
      {showRouteEditor ? <RouteEditorPanel /> : null}
      {generationPanelMode !== "closed" && !showReview && !showClarification ? <GenerationOverlay /> : null}
      {activeOverlay === "review" ? (
        <IntentReviewDialog key={backendClarification?.questions.map((question) => question.id).join("|") || "review"} />
      ) : null}
      {activeOverlay === "clarification" ? (
        <BackendClarificationDialog key={backendClarification?.questions.map((question) => question.id).join("|")} />
      ) : null}
      {activeOverlay === "share" ? <ShareModal /> : null}
      {activeOverlay === "detail" ? <PoiDetailPanel /> : null}
      <ToastHost />
    </div>
  );
}
