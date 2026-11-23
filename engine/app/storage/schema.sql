-- 鲸鲨漫剧 本地 SQLite Schema（设计 v3.1 §4）
-- 11 张表；引擎为唯一写者；WAL 模式；ULID 时间有序
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS projects (
  id          TEXT PRIMARY KEY,      -- 项目唯一标识（ULID，时间有序：列表排序免二次转换）
  name        TEXT NOT NULL,         -- 项目名（LLM 从想法中提取，用户可改）
  template_id TEXT NOT NULL,         -- 流程模板标识；V1 固定 'life_3ep'（3集短剧），扩展题材时新增
  idea_text   TEXT NOT NULL,         -- 用户首页输入的原始一句话（不改写不清洗；审计与回归测试锚点）
  episode_count INTEGER NOT NULL DEFAULT 1,  -- 目标集数：从 idea 解析（用户没说就 1 集），不写死 3
  status      TEXT NOT NULL,         -- 状态机当前态：DRAFT/CP1_PENDING/CHARACT/CP2_PENDING/PLANNED/RUNNING/CP3_PENDING/DELIVER
  script_json TEXT,                  -- 真实生成的剧本结构（title + episodes）；NULL=还没生成
  shots_json  TEXT,                  -- 真实生成的分镜结构（shots）；NULL=还没生成
  script_ver  INTEGER NOT NULL DEFAULT 0,  -- 剧本稿号；0=尚未生成过
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  deleted_at  TEXT                   -- 软删时间戳；NULL=正常。删除进回收站目录，7 天后清理任务物理删除
);
CREATE TABLE IF NOT EXISTS episodes (
  id         TEXT PRIMARY KEY,       -- 集唯一标识（ULID）
  project_id TEXT NOT NULL REFERENCES projects(id),  -- 所属项目（级联删除）
  idx        INTEGER NOT NULL,       -- 集序号 1..3（由模板决定，不硬编码上限）
  status     TEXT NOT NULL DEFAULT 'pending',  -- 本集进度：pending/scripted/generated/exported
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(project_id, idx)            -- 同项目内集号唯一
);
CREATE TABLE IF NOT EXISTS characters (
  id              TEXT PRIMARY KEY,        -- 角色唯一标识（ULID）
  project_id      TEXT NOT NULL REFERENCES projects(id),  -- 所属项目
  name            TEXT NOT NULL,           -- 角色名（如"少年·十八岁"）
  desc_text       TEXT NOT NULL,           -- 外貌文字描述：定妆图和后续所有镜头注入的一致性锚点；锁定后视为冻结基准
  ref_images      TEXT NOT NULL,           -- JSON 数组：[{asset_id, score, rank}]；锁定后不再变更
  locked          INTEGER NOT NULL DEFAULT 0,  -- 0=未锁定（重roll免费）/1=已锁定（CP-2 确认，全剧注入）
  lock_prompt_ver INTEGER,                 -- 锁定瞬间提示词版本号；用于判断"哪些镜头需要一致性重拍"
  created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CHECK (locked IN (0,1))
);
CREATE TABLE IF NOT EXISTS shots (
  id          TEXT PRIMARY KEY,      -- 镜头唯一标识（ULID）
  episode_id  TEXT NOT NULL REFERENCES episodes(id),  -- 所属集
  idx         INTEGER NOT NULL,      -- 集内镜头序号（决定成片拼接顺序）
  scene_desc  TEXT NOT NULL,         -- 场景描述（自然语言，"院子·晾衣绳·黄昏"），给用户看
  prompt      TEXT NOT NULL,         -- 生成提示词（scene_desc+角色注入+风格模板组装；每次修改 ver+1，旧版不覆盖）
  prompt_ver  INTEGER NOT NULL DEFAULT 1,  -- 提示词版本；与 generation_tasks.request_hash 联动实现"改过的镜头才重新生成"
  importance  TEXT NOT NULL,         -- key(关键镜头，画质优先)/transition(过场镜头，成本优先)——路由规则主输入
  ability     TEXT NOT NULL,         -- 能力槽：text/image/video/speech
  source      TEXT NOT NULL,         -- 算力来源：proxy(平台代采)/owned(自带密钥)/local(本地模型)
  provider_id TEXT,                  -- 路由决策写入的具体 Provider（PLANNED 阶段快照，运行期不变）
  status      TEXT NOT NULL DEFAULT 'planned',  -- planned/queued/running/done/failed/discarded
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS generation_tasks (
  id               TEXT PRIMARY KEY,      -- 任务唯一标识（ULID）
  shot_id          TEXT NOT NULL REFERENCES shots(id),  -- 目标镜头
  provider_id      TEXT NOT NULL,         -- 本次尝试使用的 Provider
  request_hash     TEXT NOT NULL,         -- sha256(shot_id+prompt_ver+provider_id+参数)；幂等键，防重复提交重复扣费
  status           TEXT NOT NULL,         -- queued/running/done/failed/discarded
  retry_count      INTEGER NOT NULL DEFAULT 0,  -- 已重试次数（换源累计），上限 3
  fail_reason      TEXT,                  -- timeout/rate_limit/content_blocked/provider_error/unknown
  discard_reason   TEXT,                  -- cp3_rejected/user_discard——与 fail_reason 分离：废弃是用户决策
  provider_task_id TEXT,                  -- 厂商侧异步任务号；崩溃恢复凭它续轮询
  created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(shot_id, request_hash)           -- 幂等约束
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON generation_tasks(status);
CREATE TABLE IF NOT EXISTS assets (
  id           TEXT PRIMARY KEY,      -- 素材唯一标识（ULID）
  project_id   TEXT NOT NULL REFERENCES projects(id),  -- 所属项目（素材按项目目录隔离）
  kind         TEXT NOT NULL,         -- image/video/audio/script/work
  local_path   TEXT NOT NULL,         -- 相对用户数据目录的路径（不存绝对路径——数据目录可迁移）
  sha256       TEXT NOT NULL,         -- 文件内容哈希：完整性校验、去重、导出幂等
  shot_id      TEXT REFERENCES shots(id),      -- 关联镜头（生成类素材）
  character_id TEXT REFERENCES characters(id), -- 关联角色（定妆类素材）
  size_bytes   INTEGER NOT NULL,      -- 文件大小（字节）
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS checkpoints (
  id             TEXT PRIMARY KEY,      -- 检查点记录唯一标识（ULID）
  project_id     TEXT NOT NULL REFERENCES projects(id),  -- 所属项目
  type           TEXT NOT NULL,         -- cp1(剧本确认)/cp2(角色锁定)/cp3(样片验收)
  status         TEXT NOT NULL,         -- pending/approved/rejected
  resume_payload TEXT NOT NULL,         -- 挂起现场完整快照(JSON)；恢复时零重算
  decided_at     TEXT,                  -- 用户决策时间戳（审计）
  created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS usage_events (
  id                TEXT PRIMARY KEY,  -- 事件唯一标识（ULID）
  ts                TEXT NOT NULL,     -- 事件时间(ISO 8601)；账单按月聚合分组键
  project_id        TEXT,              -- 关联项目（可空：账户级操作也记账）
  provider_id       TEXT NOT NULL,     -- Provider 标识
  source            TEXT NOT NULL,     -- proxy/owned/local——账单页"按来源分列"依据
  ability           TEXT NOT NULL,     -- text/image/video/speech
  units             REAL NOT NULL,     -- 计费单位数（视频秒/图片张/文本千字）
  credits_spent     REAL NOT NULL DEFAULT 0,  -- 实扣平台积分；BYOM/local 恒 0
  raw_cost_estimate REAL NOT NULL DEFAULT 0,  -- 厂商公开单价估算；BYOM"如果走代采要花多少"
  ok                INTEGER NOT NULL,  -- 1=成功 0=失败（成片率分子分母）
  fail_reason       TEXT               -- 失败原因（冗余自 tasks，便于单表统计）
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_events(ts);
CREATE TABLE IF NOT EXISTS model_configs (
  id                TEXT PRIMARY KEY,  -- 配置唯一标识（ULID）
  slot              TEXT NOT NULL,     -- text/image/video/speech
  source            TEXT NOT NULL,     -- proxy/owned/local
  provider_kind     TEXT NOT NULL,     -- openai_compat/kling/jimeng/helo/ollama/comfyui——决定实例化哪个 adapter
  name              TEXT NOT NULL,     -- 用户可读名
  endpoint          TEXT NOT NULL,     -- 模型服务地址（真实必填：云端厂商填官方地址，本地填 http://host:port/v1）
  model             TEXT,              -- 模型标识（如 deepseek-chat / MiniMax-Text-01 / 本地模型名）
  credential_cipher BLOB,              -- 密钥密文(AES-256-GCM，主密钥在 OS 凭证库)；查询接口绝不返回
  abilities         TEXT NOT NULL,     -- JSON：probe 实测可用能力清单
  verified          INTEGER NOT NULL DEFAULT 0,  -- 0=未通过真实连接测试（不可用于生成）；1=实测可用
  is_active         INTEGER NOT NULL DEFAULT 1,  -- 同槽仅一条激活
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_active ON model_configs(slot) WHERE is_active=1;
CREATE TABLE IF NOT EXISTS credit_wallet (
  id        INTEGER PRIMARY KEY CHECK (id=1),  -- 恒为 1：全库唯一钱包（单用户桌面）
  balance   REAL NOT NULL DEFAULT 0,  -- 可用额度（本地缓存视图；网关 Redis 为准）
  frozen    REAL NOT NULL DEFAULT 0,  -- 冻结额度（在途任务预估占用）
  synced_at TEXT                      -- 最近一次与网关对齐时间
);
INSERT OR IGNORE INTO credit_wallet(id,balance,frozen) VALUES (1, 86.4, 0);
CREATE TABLE IF NOT EXISTS agent_history (
  id          TEXT PRIMARY KEY,  -- 消息唯一标识（ULID）
  project_id  TEXT,              -- 关联项目（可空：全局闲聊）
  role        TEXT NOT NULL,     -- user/agent/system
  content     TEXT NOT NULL,     -- 消息正文
  intent_json TEXT,              -- agent 消息的结构化意图快照 {op,scope,cost_impact,confirmed}
  summary_to  TEXT,              -- 压缩标记：指向某消息 id，该 id 之前历史已压缩
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
-- 触发器：projects 表 updated_at 自动维护（必须在表创建之后）
CREATE TRIGGER IF NOT EXISTS trg_projects_updated AFTER UPDATE ON projects
BEGIN
  UPDATE projects SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=NEW.id;
END;
