-- MobiusPM 记忆层 schema（设计文档 §5）

-- 事项级状态
CREATE TABLE IF NOT EXISTS item_state (
  item_id          TEXT PRIMARY KEY,
  last_seen_at     TEXT NOT NULL,
  reminder_count   INTEGER NOT NULL DEFAULT 0,
  last_reminder_at TEXT,
  last_reminder_type TEXT,
  vanished_at      TEXT
);

-- 发送日志（append-only）
CREATE TABLE IF NOT EXISTS follow_up_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        TEXT NOT NULL,
  item_id       TEXT NOT NULL,
  owner         TEXT,
  welink_id     TEXT,
  reminder_type TEXT NOT NULL,
  send_status   TEXT NOT NULL,  -- success | failed | skipped | mock
  message       TEXT NOT NULL,
  dedupe_key    TEXT NOT NULL,
  error         TEXT,
  created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_log_dedupe ON follow_up_log(dedupe_key);

-- 决策日志（LLM 每次决策）
CREATE TABLE IF NOT EXISTS decision_log (
  id              TEXT PRIMARY KEY,         -- uuid
  run_id          TEXT NOT NULL,
  decision_type   TEXT NOT NULL,            -- followup | skip | escalate | wait | risk_alert | brief
  target_item_id  TEXT,                     -- 可空（全局决策）
  rationale       TEXT NOT NULL,            -- LLM 给出的理由
  action_taken    TEXT,                     -- 实际执行的工具调用
  human_confirmed INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL
);

-- 项目摘要（每次 loop 结束后更新，只保留最近 N 份）
CREATE TABLE IF NOT EXISTS context_brief (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id     TEXT NOT NULL,
  brief      TEXT NOT NULL,                  -- LLM 写的摘要
  token_count INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
