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
  const routesLength = useAppStore((s) => s.routes.length);
  const travelIntent = useAppStore((s) => s.travelIntent);
  const backendClarification = useAppStore((s) => s.backendClarification);
  const intentConfirmed = travelIntent?.confirmed;
  const runDemoGeneration = useAppStore((s) => s.runDemoGeneration);
  const showReview = Boolean(travelIntent && !intentConfirmed && !backendClarification);
  const showRouteEditor = !showReview && routesLength > 0;

  useEffect(() => {
    if (intentConfirmed && !backendClarification && generationStage === "idle" && routesLength === 0) {
      void runDemoGeneration();
    }
  }, [backendClarification, generationStage, intentConfirmed, routesLength, runDemoGeneration]);

  return (
    <div className="mvp-map-shell">
      {!showReview ? <AgentPanel /> : null}
      <GenerationOverlay />
      {showRouteEditor ? <RouteEditorPanel /> : null}
      <IntentReviewDialog />
      <BackendClarificationDialog />
      <PoiDetailPanel />
      <ShareModal />
      <ToastHost />
    </div>
  );
}
