import { useAppStore } from "../store/appStore";
import type { TransportPreference, TripPace } from "../types/routePreferences";
import { describeRoutePreferences } from "../types/routePreferences";

const TRANSPORT: { id: TransportPreference; label: string }[] = [
  { id: "walk", label: "多走路" },
  { id: "balanced", label: "均衡" },
  { id: "transit", label: "偏地铁" },
];

const PACE: { id: TripPace; label: string }[] = [
  { id: "relaxed", label: "慢游" },
  { id: "normal", label: "适中" },
  { id: "tight", label: "紧凑" },
];

export function RoutePreferencesForm() {
  const prefs = useAppStore((s) => s.routePreferences);
  const setRoutePreferences = useAppStore((s) => s.setRoutePreferences);
  const resetRoutePreferences = useAppStore((s) => s.resetRoutePreferences);

  return (
    <div className="account-section account-prefs">
      <div className="account-glass-card account-prefs-hero">
        <span className="account-pref-label">个人偏好设置</span>
        <strong>这些设置会长期保存在当前设备</strong>
        <p>之后每次规划路线、生成建议和对话理解，都会优先参考这里的个人默认偏好。</p>
      </div>

      <p className="account-section__lead">
        规划路线时的默认倾向。对话生成路线时会参考这些设置（演示环境已本地保存）。
      </p>

      <div className="account-glass-card account-pref-block">
        <span className="account-pref-label">出行方式</span>
        <div className="account-pref-segments" role="group" aria-label="出行方式">
          {TRANSPORT.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={[
                "account-pref-segment",
                prefs.transport === id ? "account-pref-segment--active" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-pressed={prefs.transport === id}
              onClick={() => setRoutePreferences({ transport: id })}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="account-pref-hint">影响步行段与公共交通的权重</p>
      </div>

      <div className="account-glass-card account-pref-block">
        <div className="account-pref-label-row">
          <span className="account-pref-label">行程侧重</span>
          <span className="account-pref-value">
            {prefs.foodVsPlay <= 30 ? "吃为主" : prefs.foodVsPlay >= 70 ? "玩为主" : "吃玩兼顾"}
          </span>
        </div>
        <div className="account-pref-range-labels">
          <span>吃</span>
          <span>玩</span>
        </div>
        <input
          type="range"
          className="account-pref-range"
          min={0}
          max={100}
          step={5}
          value={prefs.foodVsPlay}
          aria-label="吃与玩的侧重"
          onChange={(e) => setRoutePreferences({ foodVsPlay: Number(e.target.value) })}
        />
        <p className="account-pref-hint">餐馆、小吃店 vs 景点、体验类停留的优先级</p>
      </div>

      <div className="account-glass-card account-pref-block">
        <div className="account-pref-label-row">
          <span className="account-pref-label">乐意步行</span>
          <span className="account-pref-value">约 {prefs.walkMinutes} 分钟 / 段</span>
        </div>
        <input
          type="range"
          className="account-pref-range"
          min={5}
          max={40}
          step={5}
          value={prefs.walkMinutes}
          aria-label="乐意步行时长"
          onChange={(e) => setRoutePreferences({ walkMinutes: Number(e.target.value) })}
        />
        <p className="account-pref-hint">超过时倾向推荐公交或地铁</p>
      </div>

      <div className="account-glass-card account-pref-block">
        <span className="account-pref-label">行程节奏</span>
        <div className="account-pref-segments" role="group" aria-label="行程节奏">
          {PACE.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={[
                "account-pref-segment",
                prefs.pace === id ? "account-pref-segment--active" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-pressed={prefs.pace === id}
              onClick={() => setRoutePreferences({ pace: id })}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <label className="account-glass-card account-toggle">
        <span>
          <strong>尽量少换乘</strong>
          <small>地铁规划时优先直达或少换乘方案</small>
        </span>
        <input
          type="checkbox"
          checked={prefs.avoidTransfers}
          onChange={(e) => setRoutePreferences({ avoidTransfers: e.target.checked })}
        />
      </label>

      <div className="account-glass-card account-pref-summary">
        <span className="account-pref-label">当前摘要</span>
        <p>{describeRoutePreferences(prefs)}</p>
      </div>

      <button type="button" className="btn-secondary account-btn-full" onClick={resetRoutePreferences}>
        恢复默认
      </button>
    </div>
  );
}
