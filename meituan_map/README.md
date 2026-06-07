# 现在就出发 - MAP MVP Demo

一个城市路线规划前端 Demo。用户先用自然语言描述出行需求，系统解析需求并进入地图确认页，确认后生成路线方案，最后进入执行模式。当前项目默认调用仓库根目录的 Python 后端生成 POI 与路线；后端不可用时会回退到稳定 mock 数据，保证演示流程可以继续。

## 环境要求

- Node.js：建议 `20.x` 或更高版本。
- npm：建议 `10.x` 或更高版本，随 Node.js 安装。
- 操作系统：Windows / macOS / Linux 均可；当前开发环境为 Windows + PowerShell。
- 浏览器：建议使用最新版 Chrome / Edge。定位、语音输入、地图渲染等能力依赖浏览器支持。
- 网络：首次安装依赖需要访问 npm registry；运行地图和 MiMo API 时需要访问对应服务。

## 必需服务与 Key

- Google Maps JavaScript API Key：用于加载 Google 地图底图、定位预览和路线地图展示。
- Google Maps Map ID：可选。如果 Google Cloud 项目需要自定义地图样式或向量地图能力，可以配置 `VITE_GOOGLE_MAP_ID`。
- MiMo API Key：用于“分析需求”和确认弹窗中的自然语言修改。未配置或请求失败时，项目会使用本地兜底规则继续演示，但大模型解析能力不可用。
- OpenRouteService API Key：可选。后端设置 `OPENROUTESERVICE_API_KEY` 或 `ORS_API_KEY` 后会使用真实步行道路路线；未配置或请求失败时只保留距离估算，不会绘制直线，地图端会尝试通过 Google Directions 补全真实道路轨迹。

## 环境变量

复制示例文件并创建本地环境文件：

```bash
cp .env.example .env.local
```

在 `.env.local` 中配置：

```env
VITE_GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
VITE_GOOGLE_MAP_ID=your_google_maps_map_id_here

VITE_MIMO_API_KEY=your_mimo_api_key_here
MIMO_API_KEY=your_mimo_api_key_here
VITE_MIMO_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
VITE_MIMO_MODEL=mimo-v2-flash
VITE_MIMO_PROXY_PATH=/api/mimo

VITE_DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
VITE_DEEPSEEK_BASE_URL=https://api.siliconflow.cn/v1
VITE_DEEPSEEK_MODEL=deepseek-ai/DeepSeek-V4-Flash
VITE_DEEPSEEK_PROXY_PATH=/api/deepseek

VITE_PLANNER_API_BASE_URL=http://127.0.0.1:8000
VITE_PLANNER_API_PATH=/api/planner/routes
VITE_PLANNER_CLARIFICATION_API_PATH=/api/planner/clarifications
```

说明：

- `VITE_GOOGLE_MAPS_API_KEY` 是前端加载 Google Maps JavaScript API 的必填项。
- `VITE_GOOGLE_MAP_ID` 是可选项；不需要自定义地图样式时可以留空。
- 如果 Google Cloud Console 启用了 HTTP referrer 限制，请把本地开发地址加入白名单，例如 `localhost:5173` 和 `127.0.0.1:5173`。
- 如果地图无法加载，请确认 Google Cloud Console 已启用 Maps JavaScript API，项目已开启 Billing，当前网络可以访问 `maps.googleapis.com`，并在修改 `.env.local` 后重启 `npm run dev`。
- `VITE_MIMO_API_KEY` 供前端生产构建直接调用 MiMo 时使用。
- `MIMO_API_KEY` 供本地 Vite dev proxy 和 Python 测试脚本读取。
- `VITE_DEEPSEEK_API_KEY` 和 `DEEPSEEK_API_KEY` 分别供生产构建和本地 Vite proxy 使用 DeepSeek。
- 首页“需求解析模型”只能在 MiMo 和 DeepSeek 两个选项中切换，具体模型 id 由 `VITE_MIMO_MODEL` 和 `VITE_DEEPSEEK_MODEL` 决定。
- 开发环境下前端按用户选择请求 `/api/mimo` 或 `/api/deepseek`，由 `vite.config.ts` 代理到对应 base URL，避免浏览器端直接暴露 Authorization 注入逻辑。
- 开发环境下路线生成默认请求 `/api/planner/routes`，由 Vite 代理到本地 Python 后端 `http://127.0.0.1:8000`。
- 不要把真实 `.env.local`、真实 API Key 或 Token 提交到仓库。

## 安装与启动

```bash
npm run dev:backend
npm install
npm run dev
```

默认开发地址：

```text
http://localhost:5173
```

`npm run dev:backend` 需要在另一个终端保持运行，默认后端地址是：

```text
http://127.0.0.1:8000/api/planner/health
```

如果本机浏览器访问的是：

```text
http://127.0.0.1:5173
```

也属于同一个本地 Vite 服务。

## 默认演示行为

- 首页默认起点为手动输入模式，默认值是 `Philadelphia, PA, USA`。
- 首页和地图页不会自动请求 GPS 定位权限；只有用户主动选择“当前位置”后才会触发浏览器定位。
- Demo Mode 会先进入地图页的需求确认弹窗，用户点击“确认并生成路线”后才开始生成三条路线。
- 当前路线、POI、距离和耗时优先来自 Python 后端的 Yelp 费城子集、POI 聚合模块与路线生成模块。
- 如果 Python 后端未启动或生成失败，前端会提示并回退到 mock 数据。
- MiMo API 不可用时，需求分析和修改会使用本地兜底规则，保证演示流程可以继续。

## 地图加载策略

项目当前使用 Google Maps JavaScript API，并按官方 `importLibrary` 方式动态加载：

- `src/map/loadGoogleMap.ts`：Google Maps 脚本加载、library 加载、错误解析和地图实例创建。
- `src/map/GoogleMapsPreloader.tsx`：应用进入后提前预热 `maps` 和 `marker` library。
- `src/map/MapContainer.tsx`：地图页主容器，负责真实地图、缓存底图、POI marker 和路线 polyline。
- `src/components/LocationPreviewMap.tsx`：首页起点缩略地图。

为了避免 Google Maps 网络慢或 API 配置异常导致演示页空白，地图页内置了缓存演示底图：

- 真实 Google Maps 未稳定渲染前，会先显示 `Philadelphia cached map`。
- 只有检测到 Google tile 图片连续稳定渲染后，才隐藏缓存底图。
- 如果 Google Maps 加载失败，缓存底图仍会显示 POI 和路线，演示流程不被阻断。
- React 开发模式下可能触发重复初始化，项目已用 `AbortSignal` 和 `loadId` 防止旧加载任务清空新地图容器。

## Google Maps 排查清单

如果地图只显示缓存图、白屏、闪一下消失，或控制台出现 Google Maps 相关错误，按下面顺序检查：

1. `.env.local` 中是否配置了 `VITE_GOOGLE_MAPS_API_KEY`。
2. 修改 `.env.local` 后是否重启了 `npm run dev`。
3. Google Cloud Console 是否启用了 `Maps JavaScript API`。
4. Google Cloud 项目是否开启 Billing。
5. API Key 的 HTTP referrer 白名单是否包含 `http://localhost:5173/*` 和 `http://127.0.0.1:5173/*`。
6. 当前网络是否能访问 `https://maps.googleapis.com` 和 `https://maps.gstatic.com`。
7. 浏览器是否拦截第三方脚本、地图 tile 图片或定位权限。
8. 如果曾经打开过旧版本页面，先强制刷新浏览器，避免旧脚本状态和 Vite 热更新缓存影响判断。

常见现象说明：

- `Map is not a constructor`：通常是没有按 Google 官方 library 加载方式取得 `Map` 构造器；当前代码已改为 `importLibrary("maps")`。
- `ApiNotActivatedMapError`：Google Cloud 项目没有启用 Maps JavaScript API。
- `BillingNotEnabledMapError`：Google Cloud 项目没有开启 Billing。
- `RefererNotAllowedMapError`：API Key referrer 白名单没有包含当前本地开发地址。
- 短暂出现真实地图后又回到缓存图：通常表示 tile 渲染未稳定或加载任务被取消，刷新后仍出现时优先检查控制台网络错误。

## 构建与检查

```bash
npm run lint
npm run build
```

脚本说明：

- `npm run dev`：启动 Vite 开发服务器。
- `npm run lint`：运行 ESLint 检查。
- `npm run build`：运行 TypeScript 构建和 Vite 生产构建。
- `npm run preview`：预览生产构建产物。

## 单独测试 MiMo

项目提供了独立的 Python 对话测试脚本，可在不启动前端的情况下验证 MiMo API：

```bash
python tools/test_mimo_chat.py
```

也可以显式传入配置：

```bash
python tools/test_mimo_chat.py --api-key your_mimo_api_key_here --base-url https://token-plan-cn.xiaomimimo.com/v1 --model mimo-v2-flash
```

脚本默认会读取 `.env.local` 中的 `MIMO_API_KEY` 或 `VITE_MIMO_API_KEY`。

## 项目结构

```text
src/
  components/      页面和地图浮窗组件
  data/            Demo POI 与路线 mock 数据
  map/             Google 地图加载、定位、图层绘制
  pages/           IntentPage / MapRoutePage / ExecutionPage
  services/        MiMo API 调用与解析逻辑
  store/           Zustand 全局状态
  styles/          MVP 视觉样式
  utils/           路线计算与确定性规则
tools/
  test_mimo_chat.py
```

## 相关文档

- `design.md`：视觉和交互设计规范。
- `.agents/log.md`：项目变更记录。
- `C:\Users\Administrator\Downloads\codex_mvp_frontend_design_demo.md`：原始 Demo Mode 改造参考文档。
