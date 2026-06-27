# [M4] 周期性触发(cron · dry-run)+ 真实 WeLink CLI 适配 + 部署

## 目标
让 agent 进入生产形态:周期性自动跑(无人值守 · 只决策不发送)+ wake 时切换为真实 CLI 发送。本 issue 完成后,**项目实际上线运行**。

## 范围
- **cron 模式实现**:
  - `python -m pm_agent cron` 子命令
  - system prompt 切换为 "cron 变体":明确告知 agent "PM 不在场,你不能调 ask_human,也不能调 send_welink"
  - 工具层强制:`ask_human` / `send_welink` 在 cron 模式下直接返回 `{status: 'unavailable', reason: 'cron_mode'}`
  - agent 该做的:读表、查规则、写决策、写 brief、列出"等 PM wake 时该确认的候选"
  - 把 cron 模式的输出存到 `state/pending_for_wake/{date}.json`,wake 模式启动时自动读取作为"建议候选"
- **Windows 任务计划脚本** `deploy/register_schedule.ps1`:
  - 注册工作日 9:00 / 14:00 / 18:00 三次 cron
  - 注册 PowerShell 脚本调用 `python -m pm_agent cron --quiet`
  - 失败时写日志到 `state/cron_failures.log`
- **真实 WeLink CLI 适配**:
  - `tools/notifier.py` 加 `WeLinkCliNotifier` 实现
  - 配置 `notifier.mode: welink_cli` 切换
  - 实现:
    - 命令构造(参数 shell escape)
    - subprocess + 超时
    - 退出码 + stdout 解析判定 success/failed
    - 失败重试(默认 1 次,间隔 30s)
- **部署文档** `docs/deploy.md`:
  - 首次安装步骤(Python 环境 / 依赖 / API key / 配置)
  - 任务计划注册步骤
  - 灰度建议:contacts.yaml 先只 enable 1-2 人,1 周后扩
  - 故障排查指南
- **观察期保护**:
  - 上线后前 2 周,即便 wake 模式也强制 `notifier.mode: mock`(在 config 加注释提醒)
  - 准确率稳定 2 周后,PM 手动切换为 `welink_cli`

## 设计要点(强约束)
1. **cron ≠ 自动发送**(P3 原则的延伸):cron 模式严格禁止任何对外副作用。这是 agent 上线的关键安全门。
2. **真实 CLI 接口由本 issue 启动时确认**,而不是按假设的 `welink send --to <id> --message` 硬编。本 issue 启动前先回答 5 问:
   - 命令名 + 真实"发单聊"命令长什么样
   - `--to` 接的 ID 类型(账号/工号/手机/邮箱)→ 决定 contacts.yaml 的 welink_id 字段含义
   - 认证方式(预先 login / token / 配置文件)→ 决定 cron 能不能无人值守
   - 成功判定方式(退出码 / stdout JSON)→ 决定 `send_welink` 怎么解析 result
   - 能力边界(单聊?群?markdown?频率限制?)
3. **CLI 参数严格 escape**,防命令注入。即便信任 Excel 来源,也按零信任处理。
4. **超时控制**:默认 30s,可配。超时算 failed,触发重试逻辑。
5. **失败不阻塞后续候选**:某条发送 failed → write_decision 记录 → agent 继续处理下一条。
6. **观察期内 cron 也跑,只是发送被 tool 层强制 mock**,这样 1)agent 持续积累决策上下文 2)PM wake 时能看到最新建议。
7. **任务计划失败要可见**:不能默默挂掉。stderr 重定向到日志,失败时还能通过 `python -m pm_agent retrospect` 看到。

## 输入 / 输出
**输入:** 真实 WeLink CLI(由 @ttttstc 提供 install + 接口确认)、生产配置
**输出:**
- cron 模式按计划自动跑,产出 brief + pending 候选
- wake 模式跑通真实发送 → WeLink 客户端真实收到消息
- 一周连续无意外退出

## 验收标准
1. ✅ `cron` 模式下,故意构造让 agent 调 `send_welink` → 工具返回 `unavailable: cron_mode`,agent 收到 observation 后改走 write_decision 留 pending
2. ✅ Windows 任务计划注册成功,9:00 准时触发,日志可追溯
3. ✅ wake 时能读到 cron 模式留下的 `pending_for_wake/{date}.json`
4. ✅ 配置切换为 `notifier.mode: welink_cli`,wake 后单白名单实际收到 WeLink 消息
5. ✅ CLI 返回非零退出码,`send_welink` 标 failed + error 字段含 stderr
6. ✅ 超时被正确捕获,不卡死后续候选
7. ✅ 失败重试 1 次后仍失败 → 标 failed,后续候选继续处理
8. ✅ 观察期保护生效:即使配置写 `welink_cli`,在观察期内仍走 mock 并提示 PM
9. ✅ 部署文档可让一个新人按步骤完成首次部署

## 依赖
- **阻塞前置**:#1 ~ #4 全部完成
- **外部依赖**:真实 WeLink CLI(由 @ttttstc 提供安装包 + 接口文档),5 个接口问题回答

## 参考
- 设计文档:§6(触发模式)、§2 P2/P3(安全边界 + 人工确认)、§13(安全与边界)
- 原 PRD:§10(WeLink CLI 集成)、§19(边界与安全)
