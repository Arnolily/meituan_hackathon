import { useAppStore } from "../store/appStore";

export function ToastHost() {
  const toast = useAppStore((s) => s.toast);
  if (!toast) return null;
  return (
    <div style={{
      position: "fixed", top: 72, left: "50%", transform: "translateX(-50%)",
      zIndex: 200, background: "rgba(29,29,31,0.92)", color: "#fff",
      padding: "10px 20px", borderRadius: 12, fontSize: 14, pointerEvents: "none",
    }}>
      {toast}
    </div>
  );
}