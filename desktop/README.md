# 鲸鲨漫剧 · 桌面工作台（Tauri v2 壳）
把已验证的 HTML 原型接上本地 FastAPI 引擎：**数据不出电脑、引擎自动拉起、令牌只走 IPC**。
## 1. 架构
```
┌──────────────────────────────────────────────┐
│ Tauri v2 桌面壳（Rust）                       │
│  ├─ 前端 WebView：原型 index.html + bridge.js │
│  └─ 原生命令：start_engine / stop_engine /    │
│     open_data_folder / open_works_folder      │
└──────────────┬───────────────────────────────┘
               │ IPC（端口 + 随机令牌，不经 HTTP）
               ▼
┌──────────────────────────────────────────────┐
│ FastAPI 本地引擎（子进程，127.0.0.1:随机端口） │
│  项目 / 生成 / 钱包 / 模型配置 / 作品库        │
│  SQLite + AES-GCM 凭证加密                    │
└──────────────────────────────────────────────┘
```
**关键设计**：桌面壳启动时生成 64 位随机令牌，通过环境变量 `MANGJU_LOCAL_TOKEN` 注入引擎，并通过 IPC 交给前端；`/api/local-token` 仅用于浏览器预览验收，桌面运行时前端不依赖它。
## 2. 目录
| 路径 | 作用 |
|---|---|
| `src-tauri/` | Rust 壳、Tauri 配置、图标、引擎进程管理 |
| `src-tauri/src/engine.rs` | 拉起/停止引擎、选空闲端口、健康检查、令牌生成 |
| `frontend/index.html` | 由原型 + 桥接脚本生成的构建产物（**勿手改**） |
| `frontend/bridge.js` | 包装原型 `act()`，把动作映射到引擎 API |
| `build_frontend.py` | 从 `prototype/鲸鲨漫剧-制作台-v2.0.html` 重新生成前端 |
## 3. 运行
前置条件：Node 22+、Rust（cargo）、Python 3.12+。
```bash
# 1) Python 依赖（项目根目录）
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r engine/requirements.txt
# 2) 桌面壳依赖
cd desktop
npm install
# 3) 生成前端（原型有更新后重跑）
python build_frontend.py
# 4) 开发运行 / 打包
npm run dev
npm run build
```
`npm run dev` 会自动拉起引擎（无需手动开 uvicorn）；关闭窗口时自动杀掉子进程。
引擎数据目录：`engine/data/`（可用账户菜单里的「打开本地数据文件夹」进入）。
## 4. 桥接映射表
| 原型动作 | 引擎 API |
|---|---|
| 开始创作 | `POST /api/projects` |
| 继续上次 | `GET /api/projects` |
| 确认支付 | `POST /api/wallet/recharge`（余额以后端为准） |
| 按这个方案生成 | `POST /api/generation/submit`（展示路由理由） |
| 开始导出 | `POST /api/projects/{id}/export` |
| 发送消息 | `POST /api/chat`（只改写意图，不执行写操作） |
| 连接测试 / 保存设置 | `POST /api/model-configs/{slot}/test` / `PUT /api/model-configs/{slot}` |
| 打开数据/作品库文件夹 | Tauri 原生命令 `open_data_folder` / `open_works_folder` |
引擎不可用时自动降级为原型演示动画，状态栏显示「演示模式」，不假装成功。
## 5. 安全边界
- 引擎只绑定 `127.0.0.1` + 随机端口，CORS 白名单仅 Tauri 来源与本地开发端口
- 所有业务接口要求 `X-Local-Token`；令牌由 Rust 生成，桌面运行时不经过 HTTP 下发
- 凭证 AES-256-GCM 加密后入 SQLite，任何接口不回显明文
- 导出强制写入 AI 生成标识（API 层与合成层双重强制）
## 6. 已知限制
- 视频生成槽仍是 Mock：`/api/generation/submit` 返回模拟结果；无真实镜头素材时导出生成**明确标注 `demo=true` 的演示片**，不得作为正式作品发布
- 原型里的进度条、播放器是演示动画，不由引擎真实进度驱动
- 设置页展示的是掩码密钥，桥接层不会把假密钥写回引擎；真实密钥需后续做输入控件
- 尚未实现：桌面原生菜单、自动更新、代码签名（SmartScreen 会提示未知发布者）
- 浏览器预览（`python -m http.server`）走 `7420` 固定端口，仅用于开发验收
## 7. 验证记录
- 引擎：17/17 pytest 通过；CORS + 令牌鉴权生效
- 桥接：Playwright 实跑首页→创建项目→充值到账→设置保存→生成提交→导出作品库，零 JS 错误
- Rust：`cargo check` 通过；2 个单元测试通过（含真实拉起→健康检查→停止引擎）
- 桌面壳实机：`npx tauri dev` 启动成功，IPC `start_engine` 被调用，引擎在随机端口拉起且 `/health` 返回 200；关窗自动回收子进程
