import type { Poi, RoutePlan } from "../types";
import { useAppStore } from "../store/appStore";

export function PoiReplaceSheet({ route, poi, onClose }: { route: RoutePlan; poi: Poi; onClose: () => void }) {
  const pois = useAppStore((s) => s.pois);
  const replacePoiInRoute = useAppStore((s) => s.replacePoiInRoute);
  const alternatives = poi.alternatives.map((id) => pois.find((item) => item.id === id)).filter((item): item is Poi => Boolean(item));

  return (
    <div className="replace-sheet" role="dialog" aria-label={`替换 ${poi.name}`}>
      <div className="replace-sheet__head">
        <strong>替换“{poi.name}”</strong>
        <button type="button" className="btn-secondary" onClick={onClose}>关闭</button>
      </div>
      {alternatives.map((item) => (
        <article key={item.id} className="replace-option">
          <div>
            <strong>{item.name}</strong>
            <p>人均 ¥{item.avgPrice}｜排队 {item.queueTime} 分钟｜{item.tags.slice(0, 2).join("、")}</p>
          </div>
          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              replacePoiInRoute(route.id, poi.id, item.id);
              onClose();
            }}
          >
            替换
          </button>
        </article>
      ))}
    </div>
  );
}
