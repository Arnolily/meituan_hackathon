import { useAppStore } from "../store/appStore";

export function ToastHost() {
  const toast = useAppStore((s) => s.toast);
  if (!toast) return null;
  return (
    <div className="app-toast" role="status" aria-live="polite">
      {toast}
    </div>
  );
}
