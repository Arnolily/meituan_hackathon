/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_GOOGLE_MAPS_API_KEY: string;
  readonly VITE_GOOGLE_MAP_ID?: string;
  readonly VITE_MIMO_API_KEY?: string;
  readonly VITE_MIMO_BASE_URL?: string;
  readonly VITE_MIMO_MODEL?: string;
  readonly VITE_MIMO_PROXY_PATH?: string;
  readonly VITE_DEEPSEEK_API_KEY?: string;
  readonly VITE_DEEPSEEK_BASE_URL?: string;
  readonly VITE_DEEPSEEK_MODEL?: string;
  readonly VITE_DEEPSEEK_PROXY_PATH?: string;
  readonly VITE_PLANNER_CLARIFICATION_API_PATH?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const google: any;
interface Window {
  google: typeof google;
  __googleMapsApiPromise?: Promise<typeof google.maps>;
  gm_authFailure?: () => void;
}
