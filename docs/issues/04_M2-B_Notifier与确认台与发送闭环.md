# [M2-B] WeLinkNotifier 接口 + Mock + 消息模板 + 命令行确认台 + send 闭环

## 目标
打通完整"扫描 → 确认 → 发送 → 写状态 → 报告"闭环,**全程零外部依赖**,通过 mock Notifier 演示真实发送行为。本 issue 完成后,MVP 已可独立交付使用(等真实 CLI 接入即上线)。

## 范围
- `WeLinkNotifier` 接口定义(对齐 PRD §10.1)
- `MockNotifier` 实现:把"发送"打印到 stdout + 写入一个 jsonl 文件 `state/mock_sent.jsonl`
- 消息模板渲染(PRD §10.3 四个模板:验收/进展/排期/计划缺失)
- `confirm.py`:候选清单命令行确认台
  - 读取 `candidates.yaml`
  - 校验 PM 是否把 `send: true`
  - 校验消息内容长度、必填字段
  - 输出 dry-run 预览(逐条确认要发的内容)
- `send` 子命令完整链路:
  - 加载 candidates.yaml(必须是 `send: true` 才发)
  - 对每条候选:幂等检查 → 频控检查 → 联系人映射 → Notifier.sendMessage
  - 成功后写入 `follow_up_log` 与 `item_state`
  - 失败按 PRD §10.1 接口约定记录 error
- 联系人映射(`contacts.yaml`):支持 `aliases` 字段,应对 `李坤(gitcode)` 这类脏数据

## 设计要点(已定决策)
1. **半自动闭环**(收敛决策 D1):**只有 `send: true` 才会发**,缺省 `false`。PM 编辑 yaml = 确认动作。
2. **接口隔离**(收敛决策 D4):`WeLinkNotifier` 接口在本 issue 完整定义,**真实 CLI 适配留给 M3**,业务代码 0 改动。
3. **MockNotifier 行为**:
   - 永远返回 success(可配置故意失败用于测试)
   - 把"发送内容"写 `state/mock_sent.jsonl`,字段对齐 `FollowUpLog`
   - stdout 打印格式化预览,便于肉眼审核
4. **消息模板**:严格按 PRD §10.3 四个模板渲染;占位符未填值时显示"未填写"而非空。
5. **联系人映射文件不入 git**(可能含工号/真名),`contacts.yaml` 加 `.gitignore`;但提交 `contacts.example.yaml` 作为模板。
6. **多责任人策略**:默认发给"第一责任人"(PRD §10.2),其余进 `cc_owners` 字段供报告展示,本 issue 不实现"逐个发送"模式。
7. **CLI 参数 escape**:即便走 mock,也按真发送规范处理,避免 M3 切换时埋雷。

## 输入 / 输出
**输入:** `state/reports/{ts}/candidates.yaml`(PM 已编辑过 `send: true`)、`config/contacts.yaml`
**输出:**
- `state/mock_sent.jsonl` 追加发送记录
- `pm-agent.db.follow_up_log` 写入发送日志
- `pm-agent.db.item_state` 更新 `last_reminder_at` + `reminder_count++`
- 最终执行报告 `state/reports/{ts}/send-report.md`

## 验收标准
1. ✅ `pm-agent send --from candidates.yaml` 跑完,只发送 `send: true` 的条目
2. ✅ 缺 `welink_id`(联系人映射查不到)的条目 → 不发送 + 进 send-report 的失败明细 + `send_status=skipped`
3. ✅ 同一 candidates.yaml 连续 send 两次,第二次全跳过(幂等)
4. ✅ `MockNotifier` 输出可在 stdout 看到 4 种模板的真实渲染结果
5. ✅ `contacts.yaml` 的 `aliases` 能把 `李坤(gitcode)` 解析到 `李坤` 的 welink_id
6. ✅ 多责任人事项,默认只给第一责任人发,report 标注 cc
7. ✅ 全程主 Excel 不写,mtime 不变
8. ✅ 故意把 mock 设置为返回 failed,`item_state.reminder_count` 不递增,log 中 `send_status=failed`

## 依赖
- **阻塞前置**:#01 (M1-A)、#02 (M1-B)、#03 (M2-A)
- 无外部依赖(全靠 mock)

## 参考
- 收敛设计文档:§9(CLI 设计)、§10(配置)、§3 D4(接口隔离)
- 原 PRD:§10(WeLink CLI 集成)、§12(回写设计中转为 follow_up_log)、§16(执行报告)
