# MobiusPM Excel-native 跟催工具 设计文档

版本:v1.0(收敛版)
日期:2026-06-27
状态:Approved · 作为开发蓝图
原 PRD:`docs/Excel自动跟催Agent_PRD.md`(保留存档,作为需求与背景来源)

---

## 0. 这份文档的位置

| 文档 | 角色 |
|---|---|
| `Excel自动跟催Agent_PRD.md` | 原始 PRD,记录背景/现状分析/完整需求面。**保留不删**,仍是规则口径、数据分析、消息模板等内容的真相源。 |
| `MobiusPM_设计文档.md`(本文) | **收敛后的开发蓝图**。明确"做什么/不做什么/怎么做",作为 issue 拆分与代码实现的**单一事实源**。两者冲突时以本文为准。 |

本文不重复 PRD 的规则细节(R-001~R-009、DQ-001~005、状态映射表、消息模板),那些在 PRD 中已经写得很清楚,实现时直接照搬。本文只记录**经讨论收敛后的方案形态、与 PRD 的差异、为什么这么做**。

---

## 1. 一句话定义

> 一个**主 Excel 只读、催办状态外置的 Python 无状态批处理工具**:定时/手动扫表 → 规则筛 → 生成候选清单 → PM 命令行勾选确认 → Notifier(MVP 用 mock,后续接真实 WeLink CLI)发送 → 写外置状态 → 出 HTML/JSON 报告。

---

## 2. 核心架构

```
┌─ 触发层    Windows 任务计划 / 手动命令       (定时,非常驻)
│
├─ 跟催引擎  Python · 无状态批处理 · 跑完即退
│    读 Excel 快照 → WorkItem 规范化 → 规则筛 → 候选生成
│       → 命令行确认台 → Notifier 发送 → 写状态 → 出报告
│
├─ 数据层    源 Excel(只读) + 外置状态存储(sqlite 或 jsonl)
│
└─ 输出层    HTML 报告 + JSON 报告(本次扫描快照)
```

**关键性质:**
- **无状态**:进程跑完即退。事项的唯一真相源是"源 Excel + 外置状态文件",**不在进程内存里**。任何时候重跑都能完整恢复。
- **主表只读**:`项目630流水线排期计划.xlsx` 全程不写。
- **发送解耦**:`WeLinkNotifier` 接口隔离,MVP 用 mock 实现跑通主链路,真实 CLI 后续替换,业务代码 0 改动。
- **人在闭环里**:发送必经 PM 命令行勾选确认,杜绝自动群发的社交风险。

---

## 3. 核心决策与"为什么"

| # | 决策 | 替代了 PRD 的 | 为什么 |
|---|---|---|---|
| D1 | 半自动:扫→规则→草稿→**PM 命令行勾选**→发送 | 全自动群发 | 发消息是不可逆社交动作;责任人数据脏(`00853484` 工号当名、`李坤` vs `李坤(gitcode)` 等),不该让工具替 PM 得罪人。人工确认成本极低、风险消除最彻底。 |
| D2 | **主 Excel 全程只读**,催办状态外置(sqlite/jsonl) | 在主表追加 13 个系统字段 | xlsx 内嵌 12 张图(最大 2.2MB)+ 4 个 drawing;openpyxl 读写会丢失这些资源,等于破坏台账。+ PM 同时在编辑,并发冲突;+ "序号"会随增删行漂移,催办历史会错位。外置一招消三患。 |
| D3 | Python | TypeScript | 数据处理任务,openpyxl 已验证能正确读中文 xlsx;脚本短、依赖少、单 PM 部署/维护友好。 |
| D4 | `WeLinkNotifier` 接口 + mock | 直接拼 CLI 命令 | 真实 CLI 接口未知,**绝不照着 PRD 的 `welink send --to <id> --message` 拍脑袋写**。接口隔离让 M1/M2 完全不依赖 CLI 即可跑通。 |
| D5 | 定时触发 + 手动,**非常驻** | (PRD 隐含,易被误解为 daemon) | 数据源是天级人工维护;常驻无收益,反而引入内存泄漏、崩溃、重启等问题。短命进程最稳。 |
| D6 | **HTML/JSON 报告 + 命令行两步确认**(L0 看板) | (无看板) | 单 PM 自用场景,本地 Web 看板过重(YAGNI)。报告打开即最新,命令行勾选自然成为"确认台"。架构已解耦,**扩团队时随时可升级 Web,零沉没成本**。 |
| D7 | 看板的实时性=报告新鲜度 | "实时看板"幻想 | 数据源 Excel 是人工维护、天级更新。看板再"实时",数据新鲜度上限也只是 Excel 最后保存那一刻。"重跑一次即拿到最新"足够。 |

---

## 4. 与原 PRD 的差异总览

### 4.1 砍掉(过度设计,不做)

- ❌ 在主表追加 13 个系统字段(回写催办状态等)
- ❌ 3 个新 Sheet:`Config` / `Contacts` / `FollowUpLog` → 改用 yaml + 外置文件
- ❌ Excel 自动备份(不写表了就不需要)
- ❌ Excel 日期序列号转换(openpyxl 直接给 `datetime` 对象,PRD 17.1 第 5 条验收作废)
- ❌ 本地 Web 看板 / 桌面 app(MVP 不做,扩团队时再升)

### 4.2 改

- 🔁 全自动发送 → **PM 命令行勾选确认后发送**
- 🔁 TypeScript → **Python**
- 🔁 itemId 由 `sheet名+序号` 组成 → **序号不稳定,改用内容指纹**(见 §6)
- 🔁 催办状态回写主表 → **外置 sqlite/jsonl,主表只读**
- 🔁 直接调 `welink` 命令 → **`WeLinkNotifier` 接口 + mock**,真实 CLI 后接

### 4.3 加

- ➕ `WeLinkNotifier` 接口抽象 + mock 实现
- ➕ 稳定 itemId 方案(内容指纹 + 失联检测兜底)
- ➕ 候选清单命令行确认台(`pm-agent review` 子命令)

### 4.4 保留(PRD 的精华,**原文照搬**)

- ✅ **状态映射表**(PRD §8:问题状态 × 支持情况 → 标准状态)
- ✅ **跟催规则 R-001 ~ R-009**(PRD §9.2)
- ✅ **数据质量规则 DQ-001 ~ DQ-005**(PRD §9.1)
- ✅ **优先级映射 P0/P1/P2/Ignore**(PRD §8)
- ✅ **4 个消息模板**(PRD §10.3:待验收/进展/排期/计划缺失)
- ✅ **幂等 key 公式 + 频控规则**(PRD §11)
- ✅ **WorkItem / ReminderCandidate / FollowUpLog 数据结构**(PRD §15,字段不变,语言改 Python dataclass)

> 一句话:PRD 的"大脑"(规则/映射/模板/幂等)几乎全保留,要动的是"躯干"(发送方式、存储方式、技术栈、交互层)。

---

## 5. 数据现状(以真实 Excel 为准)

> 本次基于真实 Excel(`source/项目630流水线排期计划.xlsx`)直接探查所得。与 PRD §2.3 略有出入(+2 条新增),证明该表是活的,**任何统计都不能硬编码进代码**。

**工作簿:** 7 个 Sheet,主表 `630攻关问题清单` 共 **179 条有效行**(PRD 时 177)。

**主表表头(第 1 行):**
`序号 | 用户问题原文 | 问题状态 | 来源 | issue | 优先级 | 当前处理方(依次依赖) | 责任人 | 支持情况 | 计划时间 | 说明`

**问题状态:** Open 118 / Close 61
**优先级:** 必备(630前) 129 / 长期演进(630后) 28 / 增强(争取630) 18 / 拒绝(不处理) 4
**支持情况:** 待验收 67 / 已完成 63 / 挂起(630后分析) 23 / 待排期 9 / 开发中 7 / 重复单 6 / 拒绝 4
**来源:** CANN 98 / 计算 57 / GitCode 24
**空值:** 责任人 19 / 计划时间 117 / issue 154 / 说明 79
**多责任人行:** 32
**计划时间数据类型:** datetime(无 Excel 序列号,无需手动转换)
**去重责任人:** 31 人(含 `00853484` 工号、`李坤` vs `李坤(gitcode)` 等脏数据 → 联系人映射需手工清洗)

**活跃待跟催候选(推断):**
- Open 且 支持情况 ∉ {挂起,重复单,拒绝,已完成} = **77 条**(M1 首要扫描目标)
- Open 且 支持情况 ∉ {挂起,重复单,拒绝} = 85 条(含"Open+已完成 待关闭")

**xlsx 内部资源(影响是否回写):**
- 12 张图片(最大 2269KB)、4 个 drawing 对象 → **openpyxl 回写会丢失** → 决定 D2

---

## 6. 稳定 itemId 方案

**问题:** 主表只读 → 不能写 ID 列;序号会随增删行漂移 → 不能直接做 ID。

**方案:** **内容指纹 + 失联检测兜底**

```
itemId = sha1(来源 + "::" + normalize(用户问题原文))[:12]
```

- `normalize`:去首尾空白、压缩内部空白、Unicode NFKC、小写化中文标点统一(不去原文,仅做空白/标点归一化)。
- "来源 + 问题原文"在业务上构成事项的天然唯一性(同一来源不可能两条一字不差的同问题原文)。
- 改"用户问题原文"会换 ID → **业务上视为新事项**,这正是我们想要的(原文改了语义就变了,催办上下文也变了)。
- **失联检测**:每次扫描后,对外置状态文件里"上次有、本次无"的 itemId 标记 `vanished`,在报告里独立一节展示,提示 PM 是否被改了原文或删除。

> 注:状态时效短(催办幂等 key 自带日期),itemId 仅需在一个跟催周期内稳定,该方案足够。

---

## 7. 外置状态存储

**选型:** **SQLite**(单文件、零运维、并发安全、未来扩展性最好)。位置:`state/pm-agent.db`,git 忽略。

**两张表:**

```sql
-- 事项级催办状态(每事项一行)
CREATE TABLE item_state (
  item_id        TEXT PRIMARY KEY,
  last_seen_at   TEXT NOT NULL,         -- ISO8601
  reminder_count INTEGER NOT NULL DEFAULT 0,
  last_reminder_at TEXT,
  last_reminder_type TEXT,
  vanished_at    TEXT                   -- 失联标记
);

-- 发送日志(每次发送一行,append-only)
CREATE TABLE follow_up_log (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id         TEXT NOT NULL,
  item_id        TEXT NOT NULL,
  owner          TEXT,
  welink_id      TEXT,
  reminder_type  TEXT NOT NULL,
  rule_id        TEXT NOT NULL,
  send_status    TEXT NOT NULL,         -- dry_run | success | failed | skipped
  message        TEXT NOT NULL,
  dedupe_key     TEXT NOT NULL,
  error          TEXT,
  created_at     TEXT NOT NULL
);

CREATE INDEX idx_log_dedupe ON follow_up_log(dedupe_key);
CREATE INDEX idx_log_item ON follow_up_log(item_id, created_at);
```

幂等查询:每次发送前 `SELECT 1 FROM follow_up_log WHERE dedupe_key=? AND send_status IN ('success','dry_run')` 命中即跳过。

---

## 8. 目录结构

```
MobiusPM/
├── source/                              # 源 Excel(只读)
│   └── 项目630流水线排期计划.xlsx
├── state/                               # 外置状态(gitignore)
│   ├── pm-agent.db                      # sqlite
│   └── reports/                         # 历次报告归档
│       ├── 2026-06-27-0900/
│       │   ├── report.html
│       │   ├── report.json
│       │   └── candidates.yaml          # 待确认候选清单
├── config/
│   ├── pm-agent.yaml                    # 主配置
│   └── contacts.yaml                    # 责任人 → WeLinkID 映射
├── pm_agent/                            # Python 包
│   ├── __init__.py
│   ├── cli.py                           # 入口:scan/review/send/report
│   ├── excel_reader.py                  # 读 Excel,产 WorkItem
│   ├── work_item.py                     # WorkItem dataclass + 规范化
│   ├── status_mapper.py                 # 状态映射(PRD §8)
│   ├── rules.py                         # DQ + R 规则
│   ├── candidate.py                     # 候选生成 + 幂等 key
│   ├── messages.py                      # 模板渲染(PRD §10.3)
│   ├── store.py                         # sqlite 存储
│   ├── notifier.py                      # WeLinkNotifier 接口 + MockNotifier
│   ├── notifier_welink_cli.py           # 真实 CLI 适配(M3)
│   ├── contacts.py                      # 联系人映射
│   ├── report.py                        # HTML + JSON 报告
│   └── confirm.py                       # 候选清单命令行确认台
├── tests/
├── docs/
│   ├── Excel自动跟催Agent_PRD.md         # 原 PRD(保留)
│   └── MobiusPM_设计文档.md              # 本文
├── requirements.txt
└── README.md
```

---

## 9. CLI 设计

```bash
# 1) 扫描 + 生成候选清单 + dry-run 报告(不发送)
pm-agent scan
  → 写 state/reports/{ts}/{report.html, report.json, candidates.yaml}
  → 打开 report.html 看本次状态

# 2) PM 编辑 candidates.yaml,把要发的项 send: true,可改 message
notepad state/reports/{ts}/candidates.yaml

# 3) 真正发送(MVP 走 mock,M3 走真实 CLI)
pm-agent send --from state/reports/{ts}/candidates.yaml

# 4) 单独看上次报告
pm-agent report --latest
```

`candidates.yaml` 形态:

```yaml
run_id: run_20260627_090000
items:
  - item_id: a1b2c3d4e5f6
    title: "流水线支持自定义 Action(自定..."
    owner: 曹禹
    welink_id: caoyu
    rule_id: R-001
    reminder_type: acceptance_confirm
    severity: high
    send: false          # PM 改 true 才会发
    message: |
      【项目事项验收确认】
      ...
```

---

## 10. 配置项

`config/pm-agent.yaml`:

```yaml
excel:
  path: source/项目630流水线排期计划.xlsx
  sheet: 630攻关问题清单

reminder:
  same_item_cooldown_hours: 24
  max_messages_per_owner_per_day: 5
  max_messages_per_run: 50
  auto_priorities:
    - "必备(630前)"
    - "增强(争取630)"
  skip_support_statuses:
    - "挂起(630后分析)"
    - "重复单"
    - "拒绝"

notifier:
  mode: mock          # mock | welink_cli
  welink_cli_path: ""  # M3 填

state:
  db_path: state/pm-agent.db
  reports_dir: state/reports
```

`config/contacts.yaml`:

```yaml
- name: 叶红达
  welink_id: yehongda
  team: Pipeline
  enabled: true
- name: 李坤
  aliases: ["李坤(gitcode)"]   # 应对脏数据
  welink_id: likun
  team: GitCode
  enabled: true
```

---

## 11. 里程碑

| 阶段 | 交付 | 见价值点 | 依赖外部 |
|---|---|---|---|
| **M1-A** | 项目脚手架 + 配置 + Excel 读取 + WorkItem 规范化(含状态映射、稳定 itemId) | 能解析 179 条事项为标准化数据 | 无 |
| **M1-B** | 规则引擎(DQ + R)+ 候选生成 + HTML/JSON 报告(dry-run) | **一跑就能看到"今天该催什么"**,验证规则准不准 | 无 |
| **M2-A** | 外置状态存储(sqlite)+ 幂等 + 频控去重 | 重跑不重发 | 无 |
| **M2-B** | Notifier 接口 + Mock + 消息模板 + 候选清单确认台 + send 闭环 + 联系人映射 | 完整"扫→确认→发→记"闭环可演示 | 无 |
| **M3** | 真实 WeLink CLI 适配 + 定时任务 + 失败重试 | 真正上线 | 你提供真实 CLI |

> M1 + M2 全部**零外部依赖**,本机即可跑通完整闭环(走 mock 通道)。

---

## 12. 验收标准(MVP 整体)

1. **解析正确性:** 主表 179 条全部能解析为 WorkItem,字段无丢失。
2. **规则正确性:** dry-run 报告中,M1-B 跑出的活跃候选数量与现状分析推断一致(Open ∩ 非跳过支持状态 ≈ 77,允许 ±5 偏差因状态映射边界)。
3. **稳定性:** 同一 Excel 连续两次 `scan` 产生的 itemId 一致;改一条事项的"用户问题原文",该事项被视为"vanished + 新增"。
4. **幂等:** `send` 同一个 candidates.yaml 两次,第二次全部跳过,sqlite 无重复 `success` 记录。
5. **频控:** 单责任人当天超过 `max_messages_per_owner_per_day` 时,后续候选标记 `blocked`,不进入发送。
6. **安全:** 全流程主 Excel 文件 mtime 不变(只读验证)。
7. **报告:** HTML 报告可独立打开,包含本次扫描摘要、待催明细、数据质量异常、失联事项 4 个区块。

---

## 13. 安全与边界

继承 PRD §19 全部条款,补充:

- **主 Excel 全程只读**,任何时刻被工具打开都不持有写锁。
- **联系人映射文件不入 git**(可能含工号/真名)。
- **CLI 参数严格 escape**,即便走 mock 也按真发送规范处理,避免 M3 切换时埋雷。
- **失联事项**(vanished)不自动清理,保留 30 天供 PM 排查。

---

## 14. 不在范围(明确不做)

继承 PRD §3.2 全部"非目标",补充:

- ❌ MVP 不做本地 Web 看板(待扩团队再做)
- ❌ MVP 不做桌面 app
- ❌ MVP 不引入 LLM(规则引擎够用;LLM 待 v2 用于话术生成/说明字段解析)
- ❌ 不解析"说明"字段的多行时间线(PRD §2.4 已明确)

---

## 15. 后续演进(v2+)

继承 PRD §21,优先级排序:

1. 接入真实 WeLink CLI 后,观察 1-2 周准确率,再考虑放开"白名单自动发"
2. LLM 话术生成(替代固定模板,根据"说明"字段定制开场)
3. 升级本地 Web 看板(扩团队、多人确认时)
4. 多 Sheet 联合(GitCode issue 清单 ↔ 630 攻关清单)
5. 大路标访谈、Project Audit 等(PRD §21 完整列表)
