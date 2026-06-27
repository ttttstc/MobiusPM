# Handoff · M1-A 工具层基础

> 你是 **mimo**(Coder 角色),冷启动接手 MobiusPM 项目的 M1-A 实施。
> Claude 已完成 7 轮架构讨论与方案收敛,本文是你需要的**全部上下文 + 任务定义**。
> 完成后向 Claude 汇报,随后 Codex 会审,你按反馈迭代。

---

## 1. 项目一句话定位

**MobiusPM = 基于 Claude Agent SDK 的项目决策助理 agentic loop**。
首期能力是"跟催":读 Excel 项目台账 → 识别需要催办的事项 → 跟 PM 对话确认 → 通过 WeLink 发出。
你做的是**工具层第一块**:Excel 解析 + WorkItem 标准化 + SQLite 状态存储 + 幂等频控函数。

**架构定位**(必须在心里有这张图):
```
┌─ Trigger     (M4 做)
├─ Agent Loop  (M2 做 · Claude Agent SDK)
├─ Tools       (M1-A + M1-B 做 ← 你现在在这)
└─ Memory      (M1-A 建 schema · M3 做跨周期上下文)
```

---

## 2. 必读资料(按顺序)

1. **[docs/issues/01_M1-A_工具层基础.md]** — 你的任务定义 + 验收标准(权威)
2. **[docs/MobiusPM_设计文档.md]** — 全文都读,重点:
   - §1 四层架构(理解你在哪一层)
   - §2 P1~P6 六大原则(**这是硬约束,违反 = 任务失败**)
   - §5 SQLite schema(四张表你都要建)
   - §9 稳定 itemId 算法
   - §10 沿用 PRD 哪些资产
3. **[docs/Excel自动跟催Agent_PRD.md]** — 重点:
   - §2.3 数据现状(知道数据长什么样)
   - §8 状态映射表(**照搬到 status_mapper.py**)
   - §11.1 幂等 key 公式
   - §15.1 WorkItem 字段定义(**照搬,字段名用 snake_case**)
4. **[source/项目630流水线排期计划.xlsx]** — 真实数据,**先用 openpyxl 探查一次**,别照着 PRD 拍脑袋写

---

## 3. 你的范围(严格)

### ✅ 要做
- 项目脚手架:`requirements.txt`、`pm_agent/` 包、`pm_agent/__main__.py` CLI 入口
- 配置加载:`config/pm-agent.yaml`(读 yaml 即可,字段见设计文档示例)
- `pm_agent/domain/`:
  - `work_item.py` — WorkItem dataclass(字段对齐 PRD §15.1)
  - `status_mapper.py` — PRD §8 状态映射全表
  - `item_id.py` — `sha1(来源 + "::" + normalize(原文))[:12]`
- `pm_agent/tools/excel.py`:`read_excel()` tool
- `pm_agent/memory/`:
  - `schema.sql` — 设计文档 §5 **四张表全建**(item_state、follow_up_log、decision_log、context_brief)
  - `store.py` — SQLite 封装,WAL 模式,首次运行自动建表
- `pm_agent/tools/state.py`:`query_state(item_id?)` tool
- 安全函数(供 M1-B 的 send_welink 调用):
  - `dedupe_key(item_id, reminder_type, date)` 生成
  - `check_rate_limit(welink_id, today)` 检查单责任人当天上限
  - `check_run_limit(run_id)` 检查单次运行上限
- `python -m pm_agent debug --tool <name>` 子命令:绕过 agent 直接调工具,输出 JSON
- **pytest 测试**:每个 tool/domain 模块至少 1 个集成测试

### ❌ 不要做(留给后续 issue)
- LLM 调用 / Claude SDK 集成(M2)
- Notifier / 真实发送 / Mock 发送(M1-B 的 #7)
- 跟催规则引擎(M1-B 的 #7)
- 消息模板渲染(M1-B 的 #7)
- ask_human / write_decision / update_context_brief 工具(M1-B 的 #7)
- HTML 报告(整体架构已不需要,删掉这个想法)

---

## 4. 强约束(违反即任务失败)

| # | 约束 | 出处 | 验证 |
|---|---|---|---|
| 1 | **主 Excel 全程只读** | D2 决策(内嵌 12 张图,openpyxl 写回会丢) | 运行前后 mtime 不变 |
| 2 | **每个 tool 是 pure function** | P6 原则 | 不依赖 LLM 即可独立调 |
| 3 | **itemId 不准包含"序号"** | §9 | 序号会随增删行漂移 |
| 4 | **不写 status_mapper.py 时硬编当前统计数字** | 表是活的 | 用映射表逻辑,不是 if/else 把 179 当常量 |
| 5 | **TOOL 返回 JSON-serializable dict**,不要返回自定义对象 | M2 集成 SDK 时直接喂 | json.dumps 能跑通 |
| 6 | **SQLite WAL 模式** | 设计文档 §5 | 启动时 PRAGMA journal_mode=WAL |
| 7 | **type hint 完整 + dataclass** | Python 3.10+ | mypy / pyright 无重大警告 |

---

## 5. 真实数据要点(已用 openpyxl 探查验证,你也要再跑一次确认)

- 主表 **179 条有效行**(PRD 写 177,因为表持续在长——**不要硬编**)
- 工作簿 7 个 sheet,主表是 `630攻关问题清单`
- 表头第 1 行:`序号 | 用户问题原文 | 问题状态 | 来源 | issue | 优先级 | 当前处理方(依次依赖) | 责任人 | 支持情况 | 计划时间 | 说明`
- **计划时间**字段类型 = Python `datetime`(openpyxl 直接读出,**不需要 Excel 序列号转换**)
- **多责任人** 32 行,分隔符可能是 `/` `、` `,` `,` 任意一种
- **责任人脏数据**:`00853484`(工号当姓名)、`李坤` vs `李坤(gitcode)`(同人不同写法)——M1-A **保留原文不修正**,联系人映射在 M1-B 处理
- **xlsx 内嵌 12 张图 + 4 个 drawing**,最大单图 2.2MB — 这就是为什么不能写回
- 状态映射 9 种已知组合:
  - Open+待验收 61 · Close+已完成 55 · Open+挂起 23 · Open+待排期 9 · Open+已完成 8
  - Open+开发中 7 · Close+待验收 6 · Open+重复单 6 · Open+拒绝 4
  - **这 9 种全部不能映射为"未知"**

---

## 6. 验收方式(Claude 会跑这些)

1. `python -m pm_agent debug --tool read_excel` 输出 179 ±5 条 WorkItem JSON
2. 运行前后 `项目630流水线排期计划.xlsx` 的 mtime 不变
3. 同一 Excel 连跑 2 次,所有 itemId 完全一致
4. 手动改一条事项的"用户问题原文",该 itemId 变化,旧 itemId 出现在 `vanished_item_ids`
5. 32 条多责任人行的 `owner_list` 长度 ≥ 2
6. 9 种状态组合**全部不为"未知"**
7. 首次运行自动创建 `state/pm-agent.db`,4 张表 schema 与设计文档 §5 完全一致
8. 安全函数有 pytest 单元测试覆盖:幂等冷却、单人上限、单次运行上限三种场景

---

## 7. 输出预期(完成时向 Claude 汇报这几样)

1. **文件清单**:你建了哪些文件,各自职责一句话
2. **关键决策**:实现中有 2-3 个值得说的判断(如:多责任人分隔符正则怎么写、normalize 用哪种 Unicode 归一化、SQLite 连接生命周期管理)
3. **`pytest -v` 输出**:全绿
4. **`python -m pm_agent debug --tool read_excel` 的前 3 条 JSON 样例**
5. **一行总结**:做完了什么,踩到什么坑,有什么待澄清

---

## 8. 协作协议(CCG)

完成后:
- 你向 Claude 报告完成状态
- Claude 快速验收
- **Codex 进行 review**(用户协议要求,阶段性必审)
- 有反馈时你按反馈迭代,直到 Codex 通过

如果**实现过程中遇到设计文档/Issue 里没说清楚的判断点**:
- 简单的(分隔符、命名风格等)→ 你自己定,在汇报里说明理由
- 重大的(影响架构、影响验收)→ **停下问 Claude**,不要自己硬走
