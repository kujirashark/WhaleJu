# AI 漫剧制片流程 Agent：技术概要设计 v1.0
> 依据：v0.5 双模式方案（代采 + BYOM）、v0.3 Agent 交互方案、v0.4 BYOM 架构
> 范围：V1 MVP —— 桌面应用 + 本地引擎 + 轻量网关；单一"3 集短剧"流程模板；海螺（代采）+ 可灵（BYOM）双模式闭环。
---
## 一、系统总架构
```
┌────────────────────────── 用户电脑 ──────────────────────────┐
│                                                              │
│  ┌────────────────┐   IPC(Tauri)   ┌──────────────────────┐  │
│  │ 桌面前端        │ ◄───────────► │ 本地引擎             │  │
│  │ Tauri + Vue3   │               │ FastAPI (127.0.0.1)  │  │
│  │ 对话UI/资产库/  │               │                      │  │
│  │ 账单/检查点弹窗 │               │ ┌──────────────────┐ │  │
│  └────────────────┘               │ │ 流程状态机        │ │  │
│                                   │ │ (WorkflowEngine) │ │  │
│                                   │ └────────┬─────────┘ │  │
│                                   │ ┌────────▼─────────┐ │  │
│                                   │ │ 模型适配层        │ │  │
│                                   │ │ ProviderRegistry │ │  │
│                                   │ └──┬────────┬──────┘ │  │
│                                   └────┼────────┼────────┘  │
│                                        │        │           │
│              本地存储(SQLite+文件)      │        │           │
│              projects/assets/keys      │        │           │
└────────────────────────────────────────┼────────┼───────────┘
                                         │BYOM    │代采
                                         ▼        ▼
                                   ┌─────────┐ ┌──────────────┐
                                   │厂商API   │ │ 中转网关      │
                                   │可灵/即梦/│ │ 云主机FastAPI │
                                   │海螺直连  │ │ 鉴权/积分/转发│
                                   └─────────┘ └──────┬───────┘
                                                      ▼
                                                ┌──────────┐
                                                │厂商API    │
                                                │(MiniMax池)│
                                                └──────────┘
```
设计原则：
1. **单机可完整运行**（BYOM 模式下网关宕机零影响）
2. Key/素材只存本地，网关不留存任何用户素材
3. 流程引擎与适配层双向解耦（见 v0.4）
## 二、模块划分与目录结构
```
mangju/                          # 仓库根
├── desktop/                     # Tauri + Vue3 壳
│   ├── src/                     # 对话UI、资产库、账单、检查点弹窗
│   └── src-tauri/               # 侧车进程管理、本地文件对话框
├── engine/                      # 本地引擎（Python FastAPI）
│   ├── app/
│   │   ├── main.py              # FastAPI 入口(127.0.0.1:7420)
│   │   ├── workflow/            # ★ 流程引擎
│   │   │   ├── state_machine.py # 状态机+检查点暂停/恢复
│   │   │   ├── templates/       # 流程模板(逆袭3集 V1 唯一模板)
│   │   │   └── checkpoints.py   # CP-1/2/3 定义
│   │   ├── adapters/            # ★ 模型适配层
│   │   │   ├── base.py          # Provider 协议(四能力)
│   │   │   ├── registry.py      # 注册与路由(来源/能力/单价)
│   │   │   ├── helo_proxy.py    # 海螺-代采通道(走网关)
│   │   │   ├── kling_direct.py  # 可灵-BYOM直连
│   │   │   ├── openai_compat.py # OpenAI兼容文本(DeepSeek等)
│   │   │   └── local_ollama.py  # 本地模型
│   │   ├── storage/             # SQLite + 素材文件管理
│   │   ├── billing/             # 积分账本(代采) + 本地用量记录
│   │   └── compliance/          # 红线检查(Never层：原剧检测/红线词)
│   └── tests/
├── gateway/                     # 中转网关(独立部署，云主机)
│   ├── main.py                  # 鉴权/积分扣减/透传转发，无存储
│   └── rate_limit.py
├── docs/                        # 本设计文档系列
└── .workbuddy/
```
## 三、数据模型（本地 SQLite）
| 表 | 关键字段 | 说明 |
|----|----------|------|
| `projects` | id, name, template_id, status, created_at | 项目=一部剧 |
| `episodes` | id, project_id, idx, status | 集数（V1=3） |
| `characters` | id, project_id, name, ref_images(JSON), locked(bool), lock_prompt_ver | 角色资产（锁定后全剧注入） |
| `shots` | id, episode_id, idx, scene_desc, prompt, prompt_ver, ability(slot), source(代理/直连/本地), model_id, status | 分镜镜头 |
| `generation_tasks` | id, shot_id, provider_id, request_payload, response_ref, status(queued/running/done/failed/discarded), retry_count, fail_reason, discard_reason | 生成任务（重试与废弃原因→成片率统计源数据） |
| `assets` | id, project_id, kind(image/video/audio/script), local_path, shot_id?, character_id? | 素材文件索引（实际文件在项目目录） |
| `checkpoints` | id, project_id, type(cp1/cp2/cp3), status(pending/approved/rejected/resume_payload), decided_at | 检查点决策记录 |
| `usage_events` | id, ts, provider_id, source, ability, units, credits_spent, ok(bool) | 用量事件（本地账单+成片率统计源） |
| `model_configs` | id, provider_kind, name, source(owned/proxy/local), endpoint, credential_encrypted, abilities(JSON), status | 用户模型配置（Key 加密存本地） |
| `credit_wallet` | balance, frozen | 代采积分钱包（本地缓存+网关为准） |
> 敏感字段加密：credential_encrypted 用本机密钥（Tauri keychain/DPAPI）加密，SQLite 明文不含 Key。
## 四、模型适配层协议（核心接口）
### 4.1 Provider 协议
```python
class Provider(Protocol):
    meta: ProviderMeta   # id, kind, source, abilities, unit_price_hint
    async def probe(self) -> ProbeResult:
        """连接测试：返回可用能力、余额/单价(若可获取)、延迟。10s 超时。"""
    async def generate_text(self, req: TextGenRequest) -> TextGenResult: ...
    async def generate_image(self, req: ImageGenRequest) -> GenResult: ...
    async def generate_video(self, req: VideoGenRequest) -> GenResult: ...
    async def generate_speech(self, req: SpeechRequest) -> GenResult: ...
    # 仅实现所支持能力，其余抛 NotSupported → Registry 路由时过滤
```
### 4.2 能力槽与路由规则（V1）
| 槽 | V1 路由逻辑 |
|----|-------------|
| text | 用户配置的 OpenAI 兼容模型（自带/本地）；无则提示配置，不代采（剧本生成成本低） |
| image | 自带即梦 → 否则代采池（若有许可）→ 提示配置 |
| video | 按镜头类型：关键镜头→可灵(BYOM 优先) → 过场→海螺(代采) → 失败自动互换重试 ≤3 次 |
| tts | MiniMax 代采 / 本地 edge-tts 免费档 |
路由决策输出**必须给用户看理由**（"关键镜头走可灵：你的自带模型成片率更高"），路由规则不可静默。
### 4.3 统一结果信封
```python
@dataclass
class GenResult:
    ok: bool
    asset_ref: str | None        # 本地素材路径
    units_used: float            # 计费单位(条/秒/字)
    raw_cost_estimate: float     # 官方口径估算成本(仅参考展示)
    fail_reason: str | None
    provider_task_id: str | None # 视频类异步任务轮询用
```
视频生成统一异步两段式：`submit → poll(task_id, interval=5s, timeout=600s)`，桌面 UI 显示轮询进度。
## 五、流程状态机（含三检查点）
```
                    ┌─────────┐
        创建项目 ──►│ DRAFT   │ 剧本草稿生成(文本槽)
                    └────┬────┘
                    CP-1 剧本确认 ◄─── 拒绝 → 回 DRAFT 改写(保留原稿版本)
                         ▼ approved
                    ┌─────────┐
                    │ CHARACT │ 定妆图生成(生图槽, 每角色3张, 可重roll)
                    └────┬────┘
                    CP-2 定妆锁定 ◄─── 拒绝 → 重roll(锁定前不计入一致性统计)
                         ▼ locked → characters.locked=true
                    ┌─────────┐
                    │ PLANNED │ 分镜表生成+路由分配+成本预估展示
                    └────┬────┘
                         ▼ 用户确认预算
                    ┌─────────┐
                    │ RUNNING │ 批量生成(视频槽+TTS) 失败自动重试/换源
                    └────┬────┘
                    CP-3 样片验收 ◄─── 拒绝 → 标记废弃镜头，回到 PLANNED 局部重拍
                         ▼ approved
                    ┌─────────┐
                    │ DELIVER │ 拼接合成+字幕+AI标识 → 导出MP4+账单
                    └─────────┘
```
实现要点：
1. 状态机持久化于 `projects.status` + `checkpoints` 表，**引擎重启后从断点恢复**（断点续作是硬需求）
2. 每个检查点状态机挂起等待用户决策，决策超时不自动推进（Never 层：不得跳过检查点）
3. "信任模式"跳过 CP-1，但 CP-2/CP-3 不可跳（v0.3 约束）
## 六、关键链路时序
### 6.1 代采链路（视频槽-海螺）
```
UI → 引擎: 生成请求(shot#14, 过场镜头)
引擎: 路由决策=代采海螺 → 积分冻结(按预估单价)
引擎 → 网关: POST /v1/generate/video (Bearer 用户网关Token, 携带项目摘要脱敏)
网关: 鉴权 → 积分校验 → 转发 → MiniMax API
网关 → 引擎: task_id 透传
引擎: 轮询网关 GET /v1/tasks/{id} (5s间隔)
完成: 网关结算积分(冻结→扣减) → 引擎下载结果素材到本地 → 素材登记 → usage_events 记账
失败: 引擎自动重试/换源 → 网关退回冻结积分
```
### 6.2 BYOM 链路（视频槽-可灵）
```
引擎: 路由决策=BYOM可灵 → 读本地加密Key → 直连厂商API
      （全程不经过网关；usage_events 照记但 credits_spent=0，raw_cost_estimate 按公开单价估算）
```
### 6.3 检查点挂起/恢复
```
状态机到 CP-2: 持久化 resume_payload(角色图/已耗积分/版本号) → 推送UI弹窗 → 挂起
用户锁定: UI → 引擎 approve(checkpoint_id) → 状态机从 resume_payload 恢复 → 下一步
引擎崩溃恢复: 启动时扫描 status in (CP挂起/RUNNING) → RUNNING 任务重新入队轮询
```
## 七、网关 API 契约（最小集）
| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/auth/token` | POST | 桌面端登录换网关 Token |
| `/v1/wallet` | GET | 积分余额/冻结额 |
| `/v1/generate/{ability}` | POST | 统一生成入口（按 ability 转发对应厂商池） |
| `/v1/tasks/{task_id}` | GET | 异步任务状态轮询 |
| `/v1/usage` | GET | 代采用量账单 |
安全要求：全程 HTTPS；请求体不含用户素材（只含提示词与参数）；网关日志脱敏（不记 Key/完整提示词全文，提示词哈希留痕即可）。
## 八、开发里程碑（对应 30 天计划）
| 周 | 交付物 | 验收 |
|----|--------|------|
| W1 | 适配层骨架 + `openai_compat` + `helo_proxy`(代采) + SQLite schema | 海螺文生视频经网关跑通一条 5s 视频；MiniMax 分销政策确认（业务侧并行） |
| W2 | `kling_direct` + 路由器 + 来源切换器 | 同一项目混用代采+BYOM 各生成 1 镜头成功 |
| W3 | 状态机 + 三检查点 + 资产锁定 + 桌面壳(对话UI 原型) | 引擎重启断点恢复；CP-2 锁定后多镜头注入同一角色图 |
| W4 | 网关 MVP(鉴权/积分/转发) + 端到端串联 + 3-5 人内测 | 内测用户走完"代采起步→切自带 Key"完整路径 |
## 九、技术选型确认单
| 项 | 选型 | 理由 |
|----|------|------|
| 桌面壳 | Tauri 2 + Vue3 | 你的技术栈；包体小 |
| 本地引擎 | Python FastAPI（Tauri sidecar 打包） | 适配器生态、异步、你的熟悉度 |
| 本地存储 | SQLite + 本地文件目录 | 零运维 |
| 网关 | FastAPI 单机 + Redis(限流/积分原子扣减) | 初期负载极低 |
| 视频合成 | ffmpeg（拼接/字幕/AI标识水印） | 无依赖授权问题 |
| 对话编排 | LLM function calling（DeepSeek/Qwen，用户自带或本地 Ollama） | 不训练模型 |
---
*本设计为 V1 MVP 概要设计；详细设计（接口字段级定义）与代码实现随里程碑滚动补充。实施前请完成 MiniMax 分销政策确认（RK-B1，一票否决项）。*
