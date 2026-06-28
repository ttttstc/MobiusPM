# [M6] 进度趋势 + Owner 负载 + Sponsor Brief

## 目标

补齐 PM 三类决策缺口：
1. **趋势可见**：PM 第一眼能判断项目在变好还是变坏
2. **瓶颈识别**：PM 30 秒内看到谁手里堆了最多 P0
3. **向上汇报**：Sponsor 30 秒读完一页 brief，能直接决策

完成本 issue 后，MobiusPM 从「现状快照工具」升级为「决策辅助系统」。

## 范围

### Feature 1：进度趋势 + 扫描差异
- 新工具 `tools/trend.py`
  - `query_trend(run_id, db_path, trend_dir)` → 返回 `{snapshot, diff, verdict}`
  - 内部：读上次 run 的 snapshot → 计算 diff → 判定趋势方向
- 新工具 `record_snapshot(run_id, work_items, suggestions, db_path, trend_dir)`
  - 每次 wake 结束写一个 snapshot 到 `state/trend/{date}_{run_id}.json`
  - 内容：`{run_id, timestamp, total, active, closed, high_risk, overdue, by_priority, by_status}`
  - 大小约束：< 2KB
- 集成到 `write_html_dashboard`：新增「趋势」section（health-pill 下方）

### Feature 2：Owner 负载仪表板
- 新工具 `tools/owner_load.py`
  - `query_owner_load(work_items, db_path)` → 返回 `[{owner, active, p0, blocking, weekly_added, weekly_closed, status}, ...]`
  - 状态判定：active >8 OR p0 >3 → "过载"；active <2 → "清闲"；其余 → "正常"
  - 多 owner 分摊：owner_list 含 n 人 → 该事项对每个 owner 贡献 1/n
  - 缺责任人不计入
- 集成到 `write_html_dashboard`：新增「人员负载」section（summary 后、风险明细前）

### Feature 3：Sponsor 一页 Brief
- 新工具 `tools/sponsor_brief.py`
  - `write_sponsor_brief(work_items, suggestions, trend_diff, owner_load, run_id, db_path)` → 返回 `{status, path, char_count}`
  - 文件输出：`state/sponsor_brief/{date}_{run_id}.md`
  - 结构（< 30 行）：
    ```
    # Sponsor Brief · 630 · {date}
    **距 630 节点**: X 天

    ## 核心判断
    1-2 句话

    ## 关键 Ask（≤3 项）
    1. [事项] 当前[状态] → 建议[动作] → Sponsor 需[决策] → 截止[时间]
    2. ...

    ## 数字变化 vs 上周
    | 指标 | 上周 | 本周 | Δ |
    | 活跃 | ... | ... | ... |

    ## 下周风险预判
    - ...
    ```
- 集成到 agent loop（Phase 1 完成后自动写一次）
- 不自动发送给 Sponsor（PM 决定是否转发）

## 设计要点（强约束）

1. **快照是事实，不可被覆写**：snapshot 文件只能写不能改，老 run 的数据永久可追溯。
2. **趋势判定只用 1 个比较点**：当前 run vs 最近 1 次 run（避免老数据干扰判断）。
3. **Owner 负载对 owner_list 分摊**：避免双计（一个事项多 owner 时，每人各得 1/n）。
4. **Sponsor Brief 必须 < 30 行**：超过就违反「30 秒读完」的核心承诺。
5. **Sponsor Ask 必须可决策**：每条 ask 必须是 Sponsor 一次拍板能解决的（不要"请关注 X"这种空话）。
6. **Owner 负载的"瓶颈"识别**：阻塞 ≥3 个其他事项的 owner 标红（依赖此 owner 完成的他人事项 ≥3）。
7. **Sponsor Brief 与 Dashboard 数据一致**：两个文件从同一 source 渲染，避免数字打架。

## 数据模型

### Snapshot JSON Schema
```json
{
  "run_id": "wake_2026-06-28_001",
  "timestamp": "2026-06-28T14:32:00+08:00",
  "total": 179,
  "active": 114,
  "closed": 65,
  "high_risk": 15,
  "overdue": 40,
  "by_priority": {"P0": 32, "P1": 55, "P2": 28},
  "by_status": {"待验收": 38, "开发中": 41, "待排期": 5, ...},
  "by_owner_count": 12
}
```

### Owner Load Item Schema
```python
{
  "owner": "张三",
  "active": 8.5,        # 分摊后的活跃数
  "p0": 3.0,            # P0 分摊数
  "blocking_count": 2,  # 该 owner 阻塞他人事项数
  "weekly_added": 2,
  "weekly_closed": 1,
  "status": "过载",     # 过载/正常/清闲
  "items": ["item1", "item2", ...]  # top 5 关键事项
}
```

### Sponsor Brief Section
- 由 LLM 在 Phase 1 完成后自动写
- PM 可手动编辑后转发

## 输入 / 输出

**输入：**
- 现有 work_items（来自 `read_excel`）
- 现有 suggestions（来自 `query_rule_suggestions`）
- trend 快照目录（`state/trend/`）
- follow_up_log + decision_log（已有数据）

**输出：**
- `state/trend/{date}_{run_id}.json` — 每次 wake 写一个
- Dashboard 新增 2 个 section（趋势 / 人员负载）
- `state/sponsor_brief/{date}_{run_id}.md` — Phase 1 后自动写

## 验收标准

### Feature 1：进度趋势
1. ✅ `record_snapshot` 写出的 JSON < 2KB，含全部指标
2. ✅ 首次运行无 diff（不报错）
3. ✅ 第二次运行返回 diff，含数字变化和趋势判定
4. ✅ Dashboard 趋势 section 显示：与上次差异 + 趋势 pill + 健康度对比
5. ✅ Trend JSON 不会覆盖（10 次 wake 后目录有 10 个文件）
6. ✅ 测试覆盖：snapshot 写入、diff 计算、趋势判定（恶化/好转/持平）

### Feature 2：Owner 负载
1. ✅ 多人 owner 事项按 1/n 分摊（如 2 人 owner，每人得 0.5）
2. ✅ 缺责任人不计入（不归到"未指派"桶）
3. ✅ 过载判定准确（active >8 OR p0 >3）
4. ✅ 瓶颈识别：阻塞 ≥3 个其他事项的 owner 标红
5. ✅ Dashboard 人员负载 section：表格 + 状态 badge
6. ✅ 测试覆盖：分摊、阈值判定、瓶颈识别

### Feature 3：Sponsor Brief
1. ✅ Brief 文件 < 30 行
2. ✅ Ask ≤3 条，每条含 事项/状态/动作/决策/截止 5 字段
3. ✅ 数字与 Dashboard 一致（同一 source 渲染）
4. ✅ Phase 1 完成后自动生成，Phase 2 完成后可重生成
5. ✅ 测试覆盖：brief 生成、行数限制、ask 字段完整

## 不在本 issue 范围

- Sponsor 飞书/邮件自动发送（先只生成文件，未来再做）
- Owner 负载的历史曲线（只快照，不画 sparkline）
- 多项目支持（仍单 630 项目）
- 自动调度 Sponsor brief 时机（PM 手动控制）

## 实施顺序

1. `tools/trend.py` + 集成到 dashboard（先做这个，因为它最独立）
2. `tools/owner_load.py` + 集成到 dashboard
3. `tools/sponsor_brief.py` + agent loop 集成
4. 测试 + 真实数据回归
5. 设计文档回顾 + 收尾

预计工作量：3-4 天（含测试）。

## 风险与权衡

| 风险 | 影响 | 缓解 |
|---|---|---|
| Snapshot 文件膨胀 | 磁盘占用 | 每个 < 2KB，10 次/wake 约 20KB，可忽略 |
| Owner 分摊导致小数 | 显示不直观 | Dashboard 表格内仍显示小数（如 8.5），不四舍五入 |
| Sponsor brief 由 LLM 写 | 可能不一致 | 数字部分用代码渲染，叙事部分才让 LLM 写 |
| Trend 判定过于敏感 | 抖动 | 阈值保守：>3 项变化才算恶化 |

## 设计回滚预案

如果某 feature 上线后 PM 觉得不够用：
- Trend → 扩展为 sparkline（增加 trend_series 字段即可，schema 兼容）
- Owner load → 增加"释放日"字段（基于历史闭环平均速度预测）
- Sponsor brief → 增加"上周 Sponsor 已决策项"对照（拉 decision_log）

如果觉得过度设计：
- Owner load 可降级为 send 时的提醒，不在 dashboard 展示
- Sponsor brief 可改为可选生成（默认关闭）
- Trend 可只在 dashboard 显示数字，不存快照文件