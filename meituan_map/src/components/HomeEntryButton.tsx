import { useAppStore } from "../store/appStore";
import { IconHome } from "./icons";
import "./HomeEntryButton.css";

export function HomeEntryButton() {
  const setCurrentView = useAppStore((s) => s.setCurrentView);
  const setGenerationStage = useAppStore((s) => s.setGenerationStage);
  const setPois = useAppStore((s) => s.setPois);
  const setRoutes = useAppStore((s) => s.setRoutes);
  const setActiveRoute = useAppStore((s) => s.setActiveRoute);
  const setVisiblePois = useAppStore((s) => s.setVisiblePois);
  const setSelectedPoi = useAppStore((s) => s.setSelectedPoi);
  const setDetailPoi = useAppStore((s) => s.setDetailPoi);
  const clearAgentNotices = useAppStore((s) => s.clearAgentNotices);
  const setShareOpen = useAppStore((s) => s.setShareOpen);
  const setAccountSidebarOpen = useAppStore((s) => s.setAccountSidebarOpen);

  const returnHome = () => {
    setShareOpen(false);
    setAccountSidebarOpen(false);
    setGenerationStage("idle");
    setPois([]);
    setRoutes([]);
    setActiveRoute(null);
    setVisiblePois([]);
    setSelectedPoi(null);
    setDetailPoi(null);
    clearAgentNotices();
    setCurrentView("intent");
  };

  return (
    <button type="button" className="home-entry-button" aria-label="回到主页面" onClick={returnHome}>
      <IconHome size={18} />
    </button>
  );
}
