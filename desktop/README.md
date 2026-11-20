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
> **去演示化（2026-11-20）**：生产路径零 Mock。剧本/定妆图/镜头/成片全部由**用户自己配置的真实 API** 生成；没有配置或没测通的能力明确显示"未设置/未验证"，不返回任何预置示例内容、不生成演示片、不伪造进度。
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
## 6. 模型配置（必须配置才能用）
每个能力槽（写剧本 / 生成图片 / 生成视频 / 配音）都要在「设置」里配置，三种来源任选其一：
| 来源 | 必填 | 说明 |
|---|---|---|
| 用我自己的 API 密钥 | 服务地址 + 模型标识 + 密钥 | 走你的厂商账号（OpenAI 兼容接口），直连厂商、不经过平台 |
| 在你电脑上运行 | 服务地址 + 模型标识 | 需**自行部署**本地模型（Ollama/ComfyUI 等）；本机没部署这项就用不了 |
| 用平台额度 | 服务地址 + 模型标识 + 密钥 | 填平台网关地址 |
**关键规则**：
- 保存后状态为「未验证」，必须点「测试连接」真实探测（GET `{endpoint}/models`）通过才可用于生成。
- 四项能力默认全部「未设置」，不会假定任何来源可用；未配置时生成会返回明确错误（E4001）并引导去设置。
- 没有真实素材时导出返回 409（E4002），不生成演示片；花费用引擎真实账单事件统计。
## 7. 已知限制
- 写入/projects 的剧本、角色、镜头需要文本/图片模型返回 **OpenAI 兼容 JSON / 接口**；非兼容厂商需新增薄适配器（业务层零改动）
- 视频槽的真实进度依赖厂商 submit→poll 接口；`ConfiguredProvider` 默认按约定路径实现，特殊厂商需调整
- SSE 对话三事件流已接；LLM 意图改写目前是规则兜底（用户提供 LLM 后可换真实改写）
- 未做：桌面原生菜单、自动更新、代码签名
## 8. 验证记录
- 引擎：26/26 pytest 通过（新增：未配置生成拒绝 E4001、未配置测试连接失败、能力就绪接口、真实内容生成→存库→读回）
- TypeScript：`vue-tsc --noEmit` 通过；Vite 构建无告警
- Playwright（`desktop/_test_nodemo.cjs`）去演示化验证全通过：
  - 首页 0 项目（空状态，无假项目）、作品库 0 假作品（空状态）
  - 设置页 4 槽默认未设置、选来源后出现必填地址框、未填地址测试连接明确失败
  - 创建项目后第 1 步显示"未生成"引导、点生成返回 E4001 明确拒绝
  - 无 JS 错误
- Tauri 实机：`npx tauri dev` IPC 拉起引擎（端口 64802，health 200），capabilities 四槽默认全部未就绪（符合去演示化预期）
