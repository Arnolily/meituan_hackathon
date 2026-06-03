import { useEffect, useState, type FormEvent } from "react";
import { useAppStore, type AccountSection } from "../store/appStore";
import {
  IconChevronLeft,
  IconChevronRight,
  IconClock,
  IconHistory,
  IconLogIn,
  IconUser,
  IconX,
} from "./icons";
import { RoutePreferencesForm } from "./RoutePreferencesForm";
import { describeRoutePreferences } from "../types/routePreferences";
import "./AccountSidebar.css";

type MenuItem = {
  id: Exclude<AccountSection, "login" | "profile" | "preferences">;
  label: string;
  desc: string;
  Icon: typeof IconHistory;
};

const MENU_GROUPS: { title: string; items: MenuItem[] }[] = [
  {
    title: "记录",
    items: [{ id: "history", label: "历史记录", desc: "保存路线与复用", Icon: IconHistory }],
  },
];

const DETAIL_TITLES: Record<AccountSection, string> = {
  login: "登录",
  profile: "个人资料",
  preferences: "路线偏好",
  history: "历史记录",
};

function sectionTitle(id: AccountSection) {
  return DETAIL_TITLES[id] ?? "";
}

function formatHistoryTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function AccountIdentityCard({
  user,
  onLoginClick,
  onProfileClick,
}: {
  user: ReturnType<typeof useAppStore.getState>["accountUser"];
  onLoginClick: () => void;
  onProfileClick: () => void;
}) {
  const prefsSummary = useAppStore((s) => describeRoutePreferences(s.routePreferences));

  if (user) {
    return (
      <button type="button" className="account-identity account-identity--logged-in" onClick={onProfileClick}>
        <span className="account-avatar account-avatar--lg" aria-hidden>
          {user.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="account-identity__body">
          <strong>{user.name}</strong>
          <span>{user.email}</span>
          <span className="account-identity__meta">点击查看个人资料</span>
        </span>
        <IconChevronRight size={18} className="account-identity__chevron" aria-hidden />
      </button>
    );
  }

  return (
    <div className="account-identity account-identity--guest">
      <div className="account-identity__guest-top">
        <span className="account-avatar account-avatar--guest" aria-hidden>
          <IconUser size={28} />
        </span>
        <div className="account-identity__body">
          <strong>登录美团地图</strong>
          <span>同步路线偏好与历史记录</span>
        </div>
      </div>
      <ul className="account-identity__benefits">
        <li>保存路线偏好，对话规划更懂你</li>
        <li>跨设备查看历史行程</li>
      </ul>
      <button type="button" className="btn-primary account-identity__login-btn" onClick={onLoginClick}>
        <IconLogIn size={18} />
        登录 / 注册
      </button>
      <p className="account-identity__guest-hint">当前偏好：{prefsSummary}</p>
    </div>
  );
}

function PreferenceOverviewCard({ onOpenPreferences }: { onOpenPreferences: () => void }) {
  const prefsSummary = useAppStore((s) => describeRoutePreferences(s.routePreferences));

  return (
    <section className="account-glass-card account-overview-card" aria-label="个人偏好摘要">
      <div className="account-overview-card__head">
        <div>
          <span className="account-overview-card__eyebrow">个人偏好</span>
          <strong>已为你长期保存</strong>
        </div>
        <span className="account-overview-card__status">当前设备</span>
      </div>
      <p>{prefsSummary}</p>
      <button type="button" className="btn-secondary account-btn-full" onClick={onOpenPreferences}>
        打开偏好设置
      </button>
    </section>
  );
}

function AccountLoginForm({
  onSuccess,
}: {
  onSuccess: () => void;
}) {
  const loginAccount = useAppStore((s) => s.loginAccount);
  const [email, setEmail] = useState("demo@meituan-map.com");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setLoginError("请输入邮箱或手机号");
      return;
    }
    if (password.length < 4) {
      setLoginError("密码至少 4 位");
      return;
    }
    setLoginError(null);
    loginAccount({
      name: email.includes("@") ? email.split("@")[0] : "旅行者",
      email: email.trim(),
    });
    onSuccess();
  };

  return (
    <div className="account-section">
      <p className="account-section__lead">登录后偏好与历史将保存在你的账号下（演示环境为本地模拟）。</p>
      <form className="account-form account-login-form" onSubmit={onSubmit}>
        <label className="account-field">
          <span>手机号 / 邮箱</span>
          <input
            type="text"
            name="account"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="请输入手机号或邮箱"
            autoComplete="username"
          />
        </label>
        <label className="account-field">
          <span>密码</span>
          <input
            type="password"
            name="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="演示：任意 4 位以上"
            autoComplete="current-password"
          />
        </label>
        {loginError ? (
          <p className="account-error" role="alert">
            {loginError}
          </p>
        ) : null}
        <button type="submit" className="btn-primary account-btn-full">
          登录
        </button>
      </form>
      <p className="account-hint account-hint--center">继续即表示同意用户协议与隐私政策（演示）</p>
    </div>
  );
}

function AccountProfileDetail() {
  const user = useAppStore((s) => s.accountUser);
  if (!user) return null;

  return (
    <div className="account-section">
      <div className="account-profile-hero">
        <span className="account-avatar account-avatar--xl" aria-hidden>
          {user.name.slice(0, 1).toUpperCase()}
        </span>
        <strong>{user.name}</strong>
        <span>美团地图 · 网页端</span>
      </div>
      <dl className="account-dl">
        <div>
          <dt>显示名称</dt>
          <dd>{user.name}</dd>
        </div>
        <div>
          <dt>邮箱</dt>
          <dd>{user.email}</dd>
        </div>
        <div>
          <dt>手机</dt>
          <dd>{user.phone ?? "未绑定"}</dd>
        </div>
        <div>
          <dt>会员</dt>
          <dd>体验用户</dd>
        </div>
      </dl>
      <button type="button" className="btn-secondary account-btn-full">
        编辑资料（演示）
      </button>
    </div>
  );
}

function AccountHistoryDetail() {
  const routes = useAppStore((s) => s.routes);
  const travelIntent = useAppStore((s) => s.travelIntent);
  const routeHistory = useAppStore((s) => s.routeHistory);
  const reuseRouteHistory = useAppStore((s) => s.reuseRouteHistory);
  const clearRouteHistory = useAppStore((s) => s.clearRouteHistory);

  return (
    <div className="account-section">
      <div className="account-history-head">
        <p className="account-section__lead">这里保存你手动收藏的路线，可长期保存在当前设备并一键复用。</p>
        {routeHistory.length > 0 ? (
          <button type="button" className="btn-secondary" onClick={clearRouteHistory}>
            清空
          </button>
        ) : null}
      </div>
      {routeHistory.length > 0 ? (
        <ul className="account-history-list">
          {routeHistory.map((item) => (
            <li key={item.id}>
              <button type="button" className="account-glass-card account-history-item" onClick={() => reuseRouteHistory(item.id)}>
                <span className="account-history-item__icon" aria-hidden>
                  <IconClock size={16} />
                </span>
                <span className="account-history-item__body">
                  <strong>{item.route.name}</strong>
                  <span>
                    {formatHistoryTime(item.createdAt)} · {item.route.poiIds.length} 个地点 · {item.route.totalDistance.toFixed(1)} 公里
                  </span>
                  <span>
                    {item.route.totalDuration} 分钟 · 排队 {item.route.totalQueueTime} 分钟 · 匹配 {item.route.preferenceScore ?? 80} 分
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="account-glass-card account-empty-state">
          <strong>还没有保存路线</strong>
          <p>在地图路线面板点击“保存路线”，之后就能从这里快速复用。</p>
        </div>
      )}
      <div className="account-glass-card account-history-chat">
        <h3>当前规划摘要</h3>
        <ul>
          {travelIntent ? <li>{travelIntent.rawText}</li> : null}
          {routes.slice(0, 3).map((route) => (
            <li key={route.id}>
              {route.name}：{route.totalDuration} 分钟，{route.poiIds.length} 个地点，{route.status}
            </li>
          ))}
          {!travelIntent && routes.length === 0 ? <li className="account-muted">暂无规划记录</li> : null}
        </ul>
      </div>
    </div>
  );
}

export function AccountSidebar() {
  const open = useAppStore((s) => s.accountSidebarOpen);
  const view = useAppStore((s) => s.accountView);
  const section = useAppStore((s) => s.accountSection);
  const user = useAppStore((s) => s.accountUser);
  const setOpen = useAppStore((s) => s.setAccountSidebarOpen);
  const openDetail = useAppStore((s) => s.openAccountDetail);
  const backToMenu = useAppStore((s) => s.backToAccountMenu);
  const logoutAccount = useAppStore((s) => s.logoutAccount);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (view === "detail") backToMenu();
        else setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, view, backToMenu, setOpen]);

  if (!open) return null;

  const isMenu = view === "menu";

  return (
    <aside className="account-sidebar" aria-label="我的">
      <div className="account-sidebar__toolbar">
        {isMenu ? (
          <span className="account-sidebar__toolbar-title">我的</span>
        ) : (
          <button type="button" className="account-sidebar__back" onClick={backToMenu}>
            <IconChevronLeft size={20} />
            <span>{sectionTitle(section)}</span>
          </button>
        )}
        <button
          type="button"
          className="account-sidebar__close"
          aria-label="关闭"
          onClick={() => setOpen(false)}
        >
          <IconX size={20} />
        </button>
      </div>

      <div className="account-sidebar__scroll">
        {isMenu ? (
          <>
            <AccountIdentityCard
              user={user}
              onLoginClick={() => openDetail("login")}
              onProfileClick={() => openDetail("profile")}
            />

            <PreferenceOverviewCard onOpenPreferences={() => openDetail("preferences")} />

            {MENU_GROUPS.map((group) => (
              <section key={group.title} className="account-menu-group" aria-label={group.title}>
                <h3 className="account-menu-group__title">{group.title}</h3>
                <ul className="account-menu-list">
                  {group.items.map(({ id, label, desc, Icon }) => (
                    <li key={id}>
                      <button
                        type="button"
                        className="account-menu-list__row"
                        onClick={() => openDetail(id)}
                      >
                        <span className="account-menu-list__icon" aria-hidden>
                          <Icon size={18} />
                        </span>
                        <span className="account-menu-list__text">
                          <strong>{label}</strong>
                          <span>{desc}</span>
                        </span>
                        <IconChevronRight size={16} className="account-menu-list__chevron" aria-hidden />
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}

            {user ? (
              <footer className="account-sidebar__footer">
                <button type="button" className="account-logout-btn" onClick={logoutAccount}>
                  退出登录
                </button>
              </footer>
            ) : null}
          </>
        ) : (
          <div className="account-sidebar__detail" role="region" aria-label={sectionTitle(section)}>
            {section === "login" && <AccountLoginForm onSuccess={backToMenu} />}
            {section === "profile" && <AccountProfileDetail />}
            {section === "preferences" && <RoutePreferencesForm />}
            {section === "history" && <AccountHistoryDetail />}
          </div>
        )}
      </div>
    </aside>
  );
}
