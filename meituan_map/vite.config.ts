import { defineConfig, loadEnv, type ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const mimoBaseUrl = env.VITE_MIMO_BASE_URL || "https://token-plan-cn.xiaomimimo.com/v1";
  const mimoApiKey = env.VITE_MIMO_API_KEY || env.MIMO_API_KEY;
  const deepseekBaseUrl = env.VITE_DEEPSEEK_BASE_URL || "https://api.siliconflow.cn/v1";
  const deepseekApiKey = env.VITE_DEEPSEEK_API_KEY || env.DEEPSEEK_API_KEY;
  const plannerApiBaseUrl = env.VITE_PLANNER_API_BASE_URL || "http://127.0.0.1:8000";

  const proxy: Record<string, string | ProxyOptions> = {
    "/api/planner": {
      target: plannerApiBaseUrl,
      changeOrigin: true,
      secure: false,
    },
  };

  if (mimoApiKey) {
    proxy["/api/mimo"] = {
      target: mimoBaseUrl,
      changeOrigin: true,
      secure: true,
      headers: {
        Authorization: `Bearer ${mimoApiKey}`,
      },
      rewrite: (requestPath) => requestPath.replace(/^\/api\/mimo/, ""),
    };
  }

  if (deepseekApiKey) {
    proxy["/api/deepseek"] = {
      target: deepseekBaseUrl,
      changeOrigin: true,
      secure: true,
      headers: {
        Authorization: `Bearer ${deepseekApiKey}`,
      },
      rewrite: (requestPath) => requestPath.replace(/^\/api\/deepseek/, ""),
    };
  }

  return {
    plugins: [react()],
    resolve: { alias: { "@": path.resolve(__dirname, "src") } },
    server: {
      port: 5173,
      host: true,
      proxy,
    },
  };
});
