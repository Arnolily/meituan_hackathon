import { useAppStore } from "./store/appStore";
import { MapContainer } from "./map/MapContainer";
import { IntentPage } from "./pages/IntentPage";
import { MapRoutePage } from "./pages/MapRoutePage";
import { ExecutionPage } from "./pages/ExecutionPage";
import { AccountSidebar } from "./components/AccountSidebar";
import { AccountEntryButton } from "./components/AccountEntryButton";
import { HomeEntryButton } from "./components/HomeEntryButton";
import { GoogleMapsPreloader } from "./map/GoogleMapsPreloader";
import "./styles/mvp.css";

export default function App() {
  const currentView = useAppStore((s) => s.currentView);
  const travelIntent = useAppStore((s) => s.travelIntent);
  const backendClarification = useAppStore((s) => s.backendClarification);
  const hasBlockingDialog = currentView === "map" && Boolean(backendClarification || (travelIntent && !travelIntent.confirmed));

  if (currentView === "execution") {
    return (
      <>
        <GoogleMapsPreloader />
        <MapContainer />
        <HomeEntryButton />
        <AccountEntryButton floating />
        <AccountSidebar />
        <ExecutionPage />
      </>
    );
  }
  if (currentView === "map") {
    return (
      <>
        <GoogleMapsPreloader />
        <MapContainer />
        {!hasBlockingDialog ? <HomeEntryButton /> : null}
        {!hasBlockingDialog ? <AccountEntryButton floating /> : null}
        {!hasBlockingDialog ? <AccountSidebar /> : null}
        <MapRoutePage />
      </>
    );
  }
  return (
    <>
      <GoogleMapsPreloader />
      <IntentPage />
      <AccountSidebar />
    </>
  );
}
