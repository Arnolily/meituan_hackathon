import { useEffect, useRef, useState } from "react";
import { useAppStore } from "../store/appStore";
import { captureShareImage, downloadDataUrl } from "../utils/shareImage";
import { getPoisForRoute } from "../utils/routeCalculations";

export function ShareModal() {
  const open = useAppStore((s) => s.shareOpen);
  const setShareOpen = useAppStore((s) => s.setShareOpen);
  const currentView = useAppStore((s) => s.currentView);
  const activeRouteId = useAppStore((s) => s.activeRouteId);
  const executionRouteId = useAppStore((s) => s.executionRouteId);
  const routes = useAppStore((s) => s.routes);
  const pois = useAppStore((s) => s.pois);
  const showToast = useAppStore((s) => s.showToast);
  const shareRouteId = currentView === "execution" ? executionRouteId : activeRouteId;
  const route = routes.find((r) => r.id === shareRouteId) || routes[0];
  const routePois = route ? getPoisForRoute(route, pois) : [];
  const [preview, setPreview] = useState<string | null>(null);
  const fallbackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const mapEl = document.getElementById("map-root");
    const fb = fallbackRef.current;
    if (!fb) return;
    setPreview(null);
    captureShareImage(mapEl, fb).then(setPreview);
  }, [open, route?.id, route?.totalDuration]);

  if (!open) return null;

  return (
    <div className="share-overlay">
      <div className="share-dialog">
        <h3>分享行程</h3>
        {preview ? <img src={preview} alt="路线分享预览" /> : <p>正在生成预览...</p>}
        <div ref={fallbackRef} className="share-fallback">
          <p className="share-fallback__brand">现在就出发</p>
          <h2>{route?.name ?? "城市路线"}</h2>
          <p>{route?.totalDuration} 分钟｜{route?.totalDistance.toFixed(1)} 公里｜排队 {route?.totalQueueTime} 分钟｜人均 ¥{route?.avgCost}</p>
          <ol>
            {routePois.map((poi) => (
              <li key={poi.id}>{poi.name}</li>
            ))}
          </ol>
        </div>
        <div className="share-dialog__actions">
          <button type="button" className="btn-primary" disabled={!preview} onClick={() => preview && downloadDataUrl(preview, `route-${route?.id || "share"}.png`)}>
            保存图片
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              navigator.clipboard.writeText(location.href);
              showToast("已复制链接");
            }}
          >
            复制链接
          </button>
          <button type="button" className="btn-secondary" onClick={() => setShareOpen(false)}>关闭</button>
        </div>
      </div>
    </div>
  );
}
