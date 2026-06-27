# MobiusPM 项目决策助理 设计文档 v2

版本:v2.0(agentic loop 形态)
日期:2026-06-27
状态:Approved · 作为开发蓝图
原始 PRD:`docs/Excel自动跟催Agent_PRD.md`(保留存档,作为规则/模板/数据结构的真相源)
v1 设计:已被本文取代(git 历史可查)

---

## 0. 定位声明

> MobiusPM 是一个**周期性自主工作的项目决策助理**(agentic loop),以 Claude Agent SDK 为底座。**跟催只是它的第一项能力**,长期演进为完整的项目治理 agent(风险预警、依赖分析、会议建议、升级路径等)。

**不是什么:**
- ❌ 不是"PM 自己跑的跟催脚本"(那是 v1 定位,已废弃)
- ❌ 不是 Claude Code Skill(D 类形态承载不了"决策"语义)
- ❌ 不是 LangChain 工作流(workflow 不适合开放性决策任务)

**是什么:**
- ✅ 一个长期运行的 agentic 系统(Anthropic Building Effective Agents 定义的 "Agents" 类别)
- ✅ LLM 在 loop 里自主决定流程和工具使用
- ✅ 有长期记忆,跨周期累积决策上下文
- ✅ 工具层确定性、安全边界硬约束,LLM 不可绕过

---

## 1. 四层架构

```
┌─ Trigger 触发层
│   - cron (Windows 任务计划): 工作日 9:00 / 14:00 / 18:00
│   - 用户唤醒: python -m pm_agent wake
│
├─ Agent 决策层 (LLM in loop · Claude Agent SDK)
│   system_prompt: 项目决策助理身份 + 目标 + 安全边界
│   loop {
│     think → tool_call → observe → think → ... → done
│   }
│   工具: read_excel · query_state · query_rule_suggestions
│        gen_message · send_welink · ask_human
│        write_decision · update_context_brief
│
├─ Tools 工具层 (确定性、可独立测试)
│   pm_agent.tools.*  纯 Python 函数,无 LLM
│   每个 tool 都强制安全检查(幂等/频控/白名单)
│   LLM 绕不过 tool 层的硬规则
│
└─ Memory 记忆层 (SQLite,跨周期持久化)
    短期: agent loop 内 scratchpad (SDK 管理)
    长期: SQLite
      - item_state         事项级状态
      - follow_up_log      发送日志 (append-only)
      - decision_log       决策日志 (LLM 每次决策 + rationale)
      - context_brief      项目当前状态摘要 (每次 loop 结束更新)
```

---

## 2. 核心设计原则

### P1 LLM 不计算规则,但可以参考
旧规则引擎(R-001~R-009、DQ-001~005)**降级为 `query_rule_suggestions` 工具**。LLM 调用获得"按规则该催的清单",然后**自主决定听不听**——可以接受、可以补充、可以拒绝。理由必须写入 `decision_log`。

> **为什么**:规则覆盖不了边界情况(比如"这事虽然规则上该催,但说明字段里写着'对方在休假'");LLM 综合判断的价值就在这里。

### P2 安全边界是硬规则
**幂等、频控、发送白名单——这些不通过 LLM,直接在 tool 内强制**。LLM 永远绕不过去:
- `send_welink` 工具内:先查 `follow_up_log` dedupe → 命中直接返回 `blocked`,不发
- 单责任人当天 ≥ 5 条 → tool 返回 `rate_limited`
- 白名单不在 enabled 列表 → tool 返回 `not_whitelisted`

> **为什么**:LLM 不可信地处理"是否真的发出去"。把"能不能发"的最终决定权放在 deterministic code 里。

### P3 每个对外发送必经人工确认 (MVP)
agent 调 `send_welink` 前必须先调 `ask_human` 工具,把候选+消息+理由展示给 PM,得到确认才发送。**LLM 不能跳过 ask_human 直接 send**——这在 tool 层强制(`send_welink` 检查最近一次 `ask_human` 的 confirmation token)。

> **为什么**:agent 仍是新事物,信任要靠时间积累。等准确率稳定 2 周以上再考虑放开白名单自动发。

### P4 决策必须留 rationale
LLM 每次做出"催 / 不催 / 升级 / 等待"的决策都要在 `decision_log` 写理由。这条不是约定,**`write_decision` 工具强制 rationale 字段非空**。

> **为什么**:agent 可审计是上线前提。出问题时能复盘"为什么当时这么判断"。

### P5 跨周期上下文用 context_brief
每次 loop 结束前,agent 必须调用 `update_context_brief` 写一份"项目当前状态摘要"(约 300-500 token)。下次 loop 启动时自动加载,作为长期记忆的入口。

> **为什么**:loop 之间没有共享 LLM context;靠 SQLite 持久化 + 启动时注入,实现"记性"。完整决策历史从 `decision_log` 按需查。

### P6 工具层独立可测
每个 tool 都是 pure Python function,**不依赖 LLM 即可单独运行**。这意味着 M1 工具层完成后,可以用脚本批跑全部 tool 验证正确性,再去接 agent。

> **为什么**:agentic 系统调试成本高(每次跑都烧 token + 不确定),工具层先扎实再上 agent 是最经济的路径。

---

## 3. 实现路径:Claude Agent SDK

### 3.1 为什么是 SDK,不是 Claude Code subagent / MCP

| 候选 | 否决理由 |
|---|---|
| Claude Code Subagent | "周期性"意味着 cron 无人值守触发,必须脱离 Claude Code 也能跑;subagent 做不到 |
| MCP Server + 任意 LLM | 工程复杂度过高;可以从 SDK 演进到 MCP,反之不行 |
| **Claude Agent SDK** ✅ | 独立 Python 进程 · 完全控制 · 可 cron · 长期演进灵活度最高 |

### 3.2 SDK 路径的最小依赖

```
anthropic           # 官方 Python SDK
openpyxl            # Excel 读取
pyyaml              # 配置
sqlite3             # 标准库,无需安装
```

### 3.3 Agent Loop 核心代码骨架

```python
# pm_agent/agent.py(伪代码,实际见 #8 issue)
from anthropic import Anthropic
client = Anthropic()

def run_agent(trigger_reason: str) -> AgentRunResult:
    messages = [{"role": "user", "content": load_initial_prompt(trigger_reason)}]

    while True:
        resp = client.messages.create(
            model="claude-opus-4-8",
            system=load_system_prompt(),
            tools=TOOL_SCHEMAS,
            messages=messages,
            max_tokens=4096,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "end_turn":
            break  # agent 完成

        if resp.stop_reason == "tool_use":
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = TOOL_REGISTRY[block.name](**block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            messages.append({"role": "user", "content": tool_results})

    return finalize_run(messages)
```

参考:[Anthropic Cookbook · Agents Pattern](https://github.com/anthropics/anthropic-cookbook)

### 3.4 默认模型

- 主 agent loop:`claude-opus-4-8`(决策质量优先)
- 子任务(如总结 brief):`claude-sonnet-4-6`(成本/速度均衡)
- 模型选择写入配置,可调

---

## 4. 工具层接口(全集)

| Tool 名 | 功能 | 强制安全 |
|---|---|---|
| `read_excel(sheet, only_active=true)` | 读主表 → 标准化 WorkItem 列表 | 主表只读;mtime 验证 |
| `query_state(item_id?)` | 查事项当前状态、历史催办次数、上次催办时间 | — |
| `query_rule_suggestions()` | 跑 R/DQ 规则给出建议(LLM 可参考) | 输出 read-only |
| `gen_message(item_id, reminder_type)` | 按模板渲染消息 | 长度限制、占位符校验 |
| `ask_human(candidates: list, question: str)` | 把候选 + 消息发给 PM,等确认 | 返回 confirmation token |
| `send_welink(item_id, message, confirmation_token)` | 真正发送(MVP 走 mock) | 幂等 · 频控 · 白名单 · 必须有 token |
| `write_decision(item_id, decision_type, rationale, action)` | 写决策日志 | rationale 非空 |
| `update_context_brief(brief: str)` | 写本次 loop 的项目摘要 | 长度 ≤ 1000 token |
| `list_vanished()` | 列出失联事项(本次没扫到的旧 itemId) | — |

---

## 5. 记忆层 schema

```sql
-- 事项级状态
CREATE TABLE item_state (
  item_id          TEXT PRIMARY KEY,
  last_seen_at     TEXT NOT NULL,
  reminder_count   INTEGER NOT NULL DEFAULT 0,
  last_reminder_at TEXT,
  last_reminder_type TEXT,
  vanished_at      TEXT
);

-- 发送日志(append-only)
CREATE TABLE follow_up_log (
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
CREATE INDEX idx_log_dedupe ON follow_up_log(dedupe_key);

-- 决策日志(LLM 每次决策)
CREATE TABLE decision_log (
  id              TEXT PRIMARY KEY,         -- uuid
  run_id          TEXT NOT NULL,
  decision_type   TEXT NOT NULL,            -- followup | skip | escalate | wait | risk_alert | brief
  target_item_id  TEXT,                     -- 可空(全局决策)
  rationale       TEXT NOT NULL,            -- LLM 给出的理由
  action_taken    TEXT,                     -- 实际执行的工具调用
  human_confirmed INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL
);

-- 项目摘要(每次 loop 结束后更新,只保留最近 N 份)
CREATE TABLE context_brief (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id     TEXT NOT NULL,
  brief      TEXT NOT NULL,                  -- LLM 写的摘要
  token_count INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
```

**load_initial_prompt 工作机制**:
1. 读 `context_brief` 最新 1 条 → 作为"上次活到哪了"
2. 读 `decision_log` 最近 N 条 → 作为"最近做了什么决策"
3. 读 `follow_up_log` 最近 N 条 → 作为"最近催了谁"
4. 拼成 user message 喂进 agent loop

---

## 6. 触发模式

| 模式 | 触发方式 | 行为 |
|---|---|---|
| **wake** | `python -m pm_agent wake` | 用户主动唤醒,有 PM 在场,可对话确认 |
| **cron** | Windows 任务计划 | 工作日 9/14/18 点,**dry-run 模式**——只决策、写日志、不真发(等 PM 来 wake 才走 ask_human + send 路径) |
| **debug** | `python -m pm_agent debug --tool read_excel` | 直接调工具,绕过 agent loop,用于工具层测试 |

**关键设计:cron 不发送**。理由:
1. 周期性触发时 PM 不一定在场,绕过 ask_human = 违反 P3
2. 把"决策"和"动作"解耦——cron 负责更新认知和准备建议,wake 负责执行
3. PM 早上 wake 时,agent 已经基于昨晚的数据想好建议,对话效率更高

---

## 7. 目录结构

```
MobiusPM/
├── source/                              # 源 Excel(只读 · gitignored)
│   └── 项目630流水线排期计划.xlsx
├── state/                               # SQLite + 报告(gitignored)
│   └── pm-agent.db
├── config/
│   ├── pm-agent.yaml                    # 主配置
│   ├── contacts.yaml                    # 联系人映射(gitignored)
│   └── contacts.example.yaml            # 模板
├── pm_agent/
│   ├── __init__.py
│   ├── __main__.py                      # CLI 入口
│   ├── agent.py                         # Agent loop 主体
│   ├── prompts/
│   │   ├── system.md                    # system prompt
│   │   └── initial_user.md.j2           # 初始 user message 模板
│   ├── tools/
│   │   ├── __init__.py                  # TOOL_REGISTRY + TOOL_SCHEMAS
│   │   ├── excel.py                     # read_excel
│   │   ├── state.py                     # query_state + write_decision + brief
│   │   ├── rules.py                     # query_rule_suggestions
│   │   ├── messages.py                  # gen_message
│   │   ├── human.py                     # ask_human
│   │   └── notifier.py                  # send_welink (Notifier 接口 + mock + 真 CLI)
│   ├── domain/
│   │   ├── work_item.py
│   │   ├── status_mapper.py
│   │   └── item_id.py                   # 稳定 itemId 算法
│   └── memory/
│       ├── store.py                     # SQLite 封装
│       └── schema.sql
├── tests/
├── docs/
│   ├── Excel自动跟催Agent_PRD.md         # 原始 PRD (规则真相源)
│   └── MobiusPM_设计文档.md              # 本文
├── requirements.txt
└── README.md
```

---

## 8. 数据现状(基于真实 Excel · 与 v1 一致)

> 详细见 v1(git 历史)。要点摘录:
- 主表 `630攻关问题清单` 共 **179 条**
- Open 118 / Close 61
- 必备(630前) 129 / 增强(争取630) 18 / 长期演进(630后) 28 / 拒绝 4
- **活跃跟催候选(推断) ≈ 77 条**
- xlsx 内嵌 12 张图 + 4 个 drawing → **决定主表全程只读**
- 责任人去重 31 人,含工号 / 同人不同写法等脏数据 → 联系人映射需要手工清洗

---

## 9. 稳定 itemId

```
itemId = sha1(来源 + "::" + normalize(用户问题原文))[:12]
```

`normalize`:NFKC + 空白压缩 + 中文标点统一。**主表不能写 ID 列**(xlsx 回写会丢图),只能用内容指纹。改原文 = 新事项,旧 itemId 标 `vanished`。

---

## 10. 沿用 PRD 的核心资产

> **PRD 的"大脑"几乎全保留,只是被 LLM 调用方式包装了一层。** 详细内容查 `Excel自动跟催Agent_PRD.md`。

| 资产 | 在 v2 的位置 |
|---|---|
| 状态映射表(PRD §8) | `domain/status_mapper.py` |
| 跟催规则 R-001~R-009(PRD §9.2) | `tools/rules.py` 的 `query_rule_suggestions` 输出 |
| 数据质量规则 DQ-001~005(PRD §9.1) | 同上 |
| 优先级映射(PRD §8) | `domain/work_item.py` |
| 4 个消息模板(PRD §10.3) | `tools/messages.py` |
| 幂等 key 公式(PRD §11.1) | `tools/notifier.py` 内部强制 |
| 频控规则(PRD §11.2) | 同上 |
| WorkItem / FollowUpLog 数据结构(PRD §15) | `domain/` + `memory/schema.sql` |

---

## 11. 里程碑

| 阶段 | 交付 | 验证方式 |
|---|---|---|
| **M1 工具层** | 全部 tools 可独立运行 + SQLite 状态 + Mock Notifier | 脚本批跑所有 tool,产出 JSON,肉眼/diff 验证 |
| **M2 Agent 骨架** | Agent SDK 集成 + 跟催场景最小 loop + ask_human + mock send | wake 模式跑通一次完整对话闭环 |
| **M3 记忆与决策** | context_brief 持久化 + decision_log + 启动时上下文注入 | 连续跑 3 次 wake,第 3 次能引用前 2 次决策 |
| **M4 上线** | cron 触发(dry-run)+ 真实 WeLink CLI 适配 + 部署文档 | 一周连续无意外退出 |
| **M5+ 决策扩展** | 风险预警 / 依赖分析 / 会议建议 / 升级路径 | 待定 |

> M1+M2 是核心闭环,完成后 agent 已可对话工作。

---

## 12. 验收标准(MVP 整体)

1. **工具正确性**:每个 tool 单独跑能产出预期输出;`read_excel` 解析 179 条;主表 mtime 不变。
2. **Agent 闭环**:`wake` 模式下,agent 能完成"读表→查规则→跟 PM 对话→确认→mock 发送→写决策→更新 brief→退出"完整流程。
3. **安全边界**:
   - 手动构造重复 candidates,`send_welink` 返回 `blocked: dedupe`
   - 手动构造单责任人 6 条,第 6 条返回 `blocked: rate_limited`
   - 未调 `ask_human` 直接调 `send_welink` → 返回 `error: no_confirmation_token`
4. **记忆**:连跑 3 次,第 3 次 system prompt 包含前 2 次 brief 摘要。
5. **可审计**:每个发送都在 `follow_up_log` + `decision_log` 各留一行,可对账。
6. **成本可控**:单次 wake loop token 用量 ≤ 50k(可观测,可配置上限触发自动结束)。

---

## 13. 安全与边界(扩展自 PRD §19)

1. 主 Excel 全程只读 → 任何时刻 mtime 不变
2. LLM 调用必须配 token 上限,防止失控
3. 所有 tool 调用日志可追溯
4. `contacts.yaml` 含真名/工号 → 不入 git
5. CLI 参数严格 escape(M4 接真 CLI 时)
6. cron 模式 = dry-run,不真发
7. agent 即便走偏,工具层硬约束保证"不会真发错消息"

---

## 14. 不在范围(MVP 不做)

- ❌ 多项目支持(MVP 单 Excel)
- ❌ Web 看板(对话即看板)
- ❌ 桌面 app
- ❌ 多人协作的 agent(单 PM 单 agent)
- ❌ Self-modifying agent(不让 LLM 改自己的 system prompt 或 tool)

---

## 15. 与原 PRD 的关系

| 文档 | 角色 |
|---|---|
| `Excel自动跟催Agent_PRD.md` | 原始需求 + 规则细节 + 数据现状,**保留作为规则/模板真相源** |
| `MobiusPM_设计文档.md`(本文) | **架构与决策真相源**,与 PRD 冲突时以本文为准 |
