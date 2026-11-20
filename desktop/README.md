# 鲸鲨漫剧 · 桌面工作台（Tauri v2 + Vue 3）
把设计文档 §6.7 的组件契约落地：**Vue 3 组件 + Pinia stores + 本地 FastAPI 引擎**，数据不出电脑、引擎自动拉起、令牌只走 IPC。
## 1. 架构
```
┌──────────────────────────────────────────────────┐
│ Tauri v2 桌面壳（Rust）                           │
│  ├─ WebView：Vue 3 SPA（hash 路由，4 视图）        │
│  │   ├─ App.vue：顶栏 + 路由 + 全局弹窗           │
│  │   ├─ views：Home / Workbench / Works / Settings│
│  │   └─ stores：ui / project / wallet / agent /   │
│  │      settings（纯渲染层，不含业务判断）        │
│  └─ IPC：start_engine / open_data_folder / ...    │
└──────────────┬───────────────────────────────────┘
               │ 端口 + 随机令牌（IPC，不经 HTTP）
               ▼
┌──────────────────────────────────────────────────┐
│ FastAPI 本地引擎（127.0.0.1:随机端口）            │
│   项目 / 生成 / 钱包 / 模型配置 / 作品库          │
│   SQLite + AES-GCM 凭证加密                       │
└──────────────────────────────────────────────────┘
```
**前端原则（设计 §6.7）**：纯渲染层——业务判断（守卫、CP 不可跳、AI 标识）全在引擎；不直连外网；Key 输入提交后内存即清、界面不回显。
## 2. 目录
| 路径 | 作用 |
|---|---|
| `src-tauri/` | Rust 壳与引擎进程管理（随机端口、IPC 令牌、关窗回收子进程） |
| `web/src/api/engine.ts` | 引擎连接层：Tauri IPC 拿令牌 / 浏览器预览走 7420；统一 API 调用 |
| `web/src/stores/` | Pinia：ui / project / wallet / agent / settings |
| `web/src/components/` | 按设计 §6.7 拆分：home(IdeaBox/ProjectList) / work(StepNav/StepBody/ChatStream/RightPanel) / works(WorkCard) / settings(SlotCard) |
| `web/src/views/` | 四路由视图 |
| `web/src/styles/app.css` | 原型视觉 token 原样保留（深色默认 + 等宽字体 + 小圆角 + 柔和阴影） |
| `frontend/` | Vite 构建产物（`npm run build` 覆盖生成），Tauri `frontendDist` 指向此处 |
## 3. 运行
前置：Node 22+、Rust（cargo）、Python 3.12+。
```bash
# Python 依赖（项目根目录）
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r engine/requirements.txt
# Vue 前端
cd desktop/web && npm install && npm run build
# 桌面壳
cd .. && npm install && npm run dev     # 或 npm run build 打包 msi/nsis
```
## 4. 设计 §6.7 组件映射
| 路由 | 设计组件 | 已实现 |
|---|---|---|
| `/` Home | IdeaBox / TemplateChips / ProjectList | `components/home/*` + HomeView |
| `/p/:id` Workbench | StepNav / ChatStream / RightPanel / CpModal | `components/work/*` + StepBody + App.vue 内 CP 弹窗 |
| `/works` Works | WorkCard[] / CaptionPreview | WorkCard + WorksView |
| `/settings` Settings | SlotCard×4 / SourcePicker / KeyVaultInput | SlotCard + SettingsView |
| stores | project / gen / wallet / agent | 合并为 project / wallet / agent / settings / ui |
> 差异说明：`ChatStream` 目前是输入栏 + 意图提示（引擎未接 SSE，设计中的三事件流待 W5）；`CpModal` 三合一为 CP-2 角色确认弹窗（CP-1/CP-3 在 8 步界面内以确认卡片呈现）；`SourcePicker`/`KeyVaultInput` 内聚在 SlotCard 中。
## 5. 安全边界
- 引擎仅绑定 127.0.0.1 + 随机端口，CORS 白名单仅 Tauri 来源与本地端口
- 令牌由 Rust 生成经 IPC 交接，桌面运行时不通过 HTTP 下发；存内存不落盘
- 凭证 AES-256-GCM 加密入 SQLite，任何接口不回显明文
- 导出强制带 AI 生成标识（API 层 + 合成层双强制）
## 6. 已知限制
- 视频槽仍是 Mock：无真实素材时导出生成 `demo=true` 演示片，不得作为正式作品发布
- 生成进度已接引擎真实 `/generation/progress`（W5 完成）；**播放器**仍是演示动画（未接真实素材）
- SSE 对话已接三事件流与意图确认门（`agent.confirm()` 调 `/api/agent/execute`）；LLM 改写目前是规则兜底
- 未做：桌面原生菜单、自动更新、代码签名
## 7. 验证记录
- TypeScript：`vue-tsc --noEmit` 通过
- 构建：Vite 产出 8 个 JS chunk + CSS + 6 张剧照，无 CSS 语法告警
- Playwright：`desktop/_test_vue.cjs` 全量通过——首页、8 步导航、角色多选 5→4、CP 弹窗锁定、生成提交、导出落库、作品库 4 卡、设置 4 组/密钥行、充值后端到账、主题切换、hash 路由，无 400/404、无 JS 错误
- Tauri 实机：`npx tauri dev` 加载 Vue 前端成功，IPC 拉起引擎（health 200）
- W5（真实进度 + SSE）：真实批次 start/pause/progress 全通；暂停后进度冻结实测 4/12 保持不变；
  SSE 三事件流逐字回显 + 意图确认条实测（确认文案与成本影响正确显示，取消不执行任何写操作）；
  原 Vue 全量回归无退化
