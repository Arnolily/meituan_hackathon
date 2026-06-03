import type { PoiCategory } from "../types";
import { CATEGORY_META } from "../data/constants";

const ICONS: Record<PoiCategory, string> = {
  food: "餐",
  mall: "商",
  restroom: "厕",
  study: "学",
  entertainment: "玩",
  life: "活",
};

export function createPinHtml(category: PoiCategory, selected = false, kind?: "start" | "end") {
  const color = kind === "start" ? "#27ae60" : kind === "end" ? "#e74c3c" : CATEGORY_META[category].color;
  const icon = kind === "start" ? "起" : kind === "end" ? "终" : ICONS[category];
  const cls = selected ? "map-pin map-pin--selected" : "map-pin";
  return `<div class="${cls}" style="--pin-color:${color}"><span class="map-pin__head"><span>${icon}</span></span><span class="map-pin__needle"></span></div>`;
}

export const PIN_STYLES = `
.map-pin { position:relative; width:32px; height:42px; transform:translate(-50%,-100%); cursor:pointer; transition:transform .2s, filter .2s; filter:drop-shadow(0 4px 6px rgba(0,0,0,.25)); }
.map-pin:hover { transform:translate(-50%,calc(-100% - 4px)); }
.map-pin--selected { transform:translate(-50%,calc(-100% - 2px)) scale(1.3); z-index:999; }
.map-pin--selected::after { content:""; position:absolute; left:50%; top:8px; width:36px; height:36px; margin-left:-18px; border-radius:50%; border:2px solid #f5c542; animation:pin-pulse 1.2s ease-out infinite; }
.map-pin__head { display:flex; align-items:center; justify-content:center; width:28px; height:28px; border-radius:50% 50% 50% 0; transform:rotate(-45deg); background:var(--pin-color); border:2px solid #fff; font-size:12px; color:#fff; font-weight:600; }
.map-pin__head span { transform:rotate(45deg); display:block; }
.map-pin__needle { position:absolute; left:50%; bottom:0; width:0; height:0; margin-left:-6px; border-left:6px solid transparent; border-right:6px solid transparent; border-top:10px solid var(--pin-color); }
@keyframes pin-pulse { 0%{opacity:.9;transform:scale(.8)} 100%{opacity:0;transform:scale(1.4)} }
.loc-pulse { position:relative; width:24px; height:24px; }
.loc-pulse__dot { position:absolute; left:50%; top:50%; width:8px; height:8px; margin:-4px 0 0 -4px; background:#0071e3; border-radius:50%; border:2px solid #fff; z-index:2; }
.loc-pulse__ring { position:absolute; inset:0; border:2px solid rgba(0,113,227,.5); border-radius:50%; animation:loc-ring 1.5s ease-out infinite; }
@keyframes loc-ring { 0%{transform:scale(.5);opacity:1} 100%{transform:scale(2);opacity:0} }
`;