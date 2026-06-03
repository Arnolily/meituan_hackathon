import { useAppStore } from "../store/appStore";
import { IconUser } from "./icons";
import "./AccountEntryButton.css";

export function AccountEntryButton({ floating = false }: { floating?: boolean }) {
  const accountSidebarOpen = useAppStore((s) => s.accountSidebarOpen);
  const toggleAccountSidebar = useAppStore((s) => s.toggleAccountSidebar);
  const user = useAppStore((s) => s.accountUser);

  return (
    <button
      type="button"
      className={[
        "account-entry-button",
        floating ? "account-entry-button--floating" : "account-entry-button--inline",
        accountSidebarOpen ? "account-entry-button--active" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-label="打开个人中心"
      aria-expanded={accountSidebarOpen}
      onClick={toggleAccountSidebar}
    >
      {user ? <span className="account-entry-button__avatar">{user.name.slice(0, 1).toUpperCase()}</span> : <IconUser size={18} />}
    </button>
  );
}
