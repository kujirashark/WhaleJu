# 鲸鲨漫剧 本地引擎（W1-W4 实现）
基于 `docs/鲸鲨漫剧-系统设计方案-合订本-v3.1.md` 的增量实现。当前完成 **W1-W4 后端与网关骨架**，桌面 UI 沿用 `prototype/鲸鲨漫剧-制作台-v2.0.html`。
> **先看这里**：本文记录 W1–W4 的历史实现，其中 Mock、桌面壳未搭建等描述已过时。当前启动、模型配置与调试请以 **`docs/鲸鲨漫剧-启动与调试手册.md`** 为准。生产路径已去演示化：所有能力由用户配置的真实 API 提供，未配置或测试未通过会明确拒绝。
## 运行
```bash
# 依赖（已安装则跳过）
python -m venv .venv
.venv/Scripts/python.exe -m pip install fastapi uvicorn httpx pytest pytest-asyncio cryptography
# 本地引擎（127.0.0.1:7420）
.venv/Scripts/python.exe -m uvicorn engine.app.main:app --host 127.0.0.1 --port 7420
# 云网关（模拟，本地联调）
.venv/Scripts/python.exe -m uvicorn gateway.app:app --host 127.0.0.1 --port 8080
# 测试
.venv/Scripts/python.exe -m pytest engine/tests -q   # 36 passed（临时数据目录，不影响真实数据）
```
引擎启动后 `GET /api/local-token` 取本地鉴权 token，后续请求带 `X-Local-Token: <token>`。
## 已实现（对应设计章节）
| 里程碑 | 内容 | 设计章节 |
|---|---|---|
| W1 | 11 表 DDL + 存储层、Provider 协议 + Mock 适配器 + Registry、钱包冻结/结算、项目/生成 API | §4 §5.2 §5.4 §6.1-6.2 |
| W2 | 凭证 AES-256-GCM 加密（零明文回显）、模型配置 CRUD + 连接测试、来源切换、可解释路由 reason | §4.9 §5.2 §6.4 |
| W3 | 对话 Agent（工具白名单 + 意图改写 + 确认门）、检查点挂起/恢复（绝不自动 approve） | §5.1 §5.3 |
| W4 | 作品库、导出合成 + AI 标识双层强制、发布文案锁定声明、网关幂等/鉴权骨架 | §5.5 §6.3 §6.6 |
## 目录
```
engine/
├── app/
│   ├── main.py              # FastAPI 入口（13+ 路由）
│   ├── storage/             # schema.sql(11表) / db.py / vault.py(加密) / util.py
│   ├── adapters/            # base.py(协议) / registry.py / mock_provider.py / openai_compat.py
│   ├── workflow/            # state_machine.py(表驱动) / checkpoints.py
│   ├── billing/ledger.py    # 冻结→结算→对账
│   ├── agent/agent.py       # 工具白名单 + 意图改写 + 确认门
│   └── publish/kit.py       # ffmpeg 合成 + AI 标识
└── tests/test_w1.py         # 17 用例
gateway/app.py               # 网关骨架（内存模拟，生产换 Redis + Lua）
```
## 关键安全设计（Never 层，已测试）
- Agent 工具白名单**没有** approve_checkpoint / start_generation / 任何扣费工具
- 未确认的写操作一律拒绝（E3001），越权工具拒绝（E3002）
- CP-2/CP-3 不可跳过；挂起态重启后重新弹窗，绝不自动推进
- 凭证只以密文入 SQLite；任何接口不回显明文（字段 `credential_cipher` BLOB）
- 导出强制带 AI 标识（API 层 + compose 层双重强制）
- 网关提示词只留哈希、幂等键防重复扣费
## 已知限制（未实现，按设计文档后续迭代）
1. **通用适配器按 OpenAI 兼容协议覆盖四类能力（文本/图片/视频/语音）**，视频走 submit→poll 两段式；不兼容的厂商（可灵原生协议等）需新增薄适配器。生产路径零 Mock，详见启动与调试手册 §6.4
2. **网关用内存态模拟**，生产需替换为 Redis + Lua 原子扣减（设计 §6.6）
3. **ffmpeg 在本机 WinGet shim 下无法直接 subprocess**，测试环境降级为文件复制；生产打包必须内置真实 ffmpeg
4. **桌面壳已搭建**（`desktop/`：Tauri v2 + Vue 3），但打包未做代码签名与自动更新；界面构建与启动步骤见启动与调试手册 §2–§3
5. **对话改写用规则兜底**（无 LLM Key 时），生产接 LLM 单次调用产出同结构 Intent
6. 支付回调、对账 cron、资产 sha256 落地、SSE 流式输出未实现
## 环境变量
| 变量 | 用途 | 默认 |
|---|---|---|
| `MANGJU_DATA_DIR` | 数据目录 | `engine/data` |
| `MANGJU_MASTER_KEY` | 凭证主密钥（base64 32 字节） | 数据目录下 `.master.key` |
| `MANGJU_GATEWAY_TOKEN` | 网关 Token | `dev-gateway-token`（仅开发） |
