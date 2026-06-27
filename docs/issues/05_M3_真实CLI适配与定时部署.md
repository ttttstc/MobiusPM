# [M3] 真实 WeLink CLI 适配 + 定时任务 + 失败重试

## 目标
把 MockNotifier 切换为真实 WeLink CLI 实现,部署 Windows 任务计划做天级定时,MVP 真正上线运行。

## 范围
- `notifier_welink_cli.py`:真实 CLI 适配
  - 命令构造(参数严格 escape)
  - 调用 subprocess + 超时控制
  - 退出码 / stdout 解析,识别成功/失败
  - 失败重试(默认 1 次,可配置)
- 配置项扩展:`notifier.welink_cli_path`、`notifier.timeout_seconds`、`notifier.retry_count`
- Windows 任务计划脚本(`deploy/schedule.ps1`),按配置时间触发 `pm-agent scan`
- 部署文档:首次安装 + 配置 + 任务计划注册 + 灰度建议(白名单先发)

## 设计要点(已定决策)
1. **接口契约不变**:沿用 M2-B 定义的 `WeLinkNotifier`,只换一个实现类。M2-B 的所有业务代码 0 改动。
2. **CLI 真实接口由本 issue 落地时确认**,而不是按 PRD `welink send --to <id> --message` 拍脑袋写。本 issue 启动前需先回答 5 问:
   - 命令名 + 一条真实"发单聊"命令长什么样
   - `--to` 接的 ID 类型(账号/工号/手机/邮箱)
   - 认证方式(预先 login / token / 配置文件)
   - 成功判定方式(退出码 / stdout JSON)
   - 能力边界(单聊?群?markdown?频率限制?)
3. **灰度策略**:首次上线前,在 `contacts.yaml` 中只把 1-2 个责任人 `enabled: true`,其余 `false`。观察 1 周再放开。
4. **失败重试**:默认 1 次,间隔 30 秒。重试仍失败 → 标 `failed`,**不阻塞后续候选**。
5. **定时频率建议**:工作日 9:00 / 14:00 / 18:00,三次扫描,周末不跑。可配置。
6. **观察期**:上线后前 2 周仍**保持 dry-run 模式**,只生成 candidates.yaml,PM 仍需命令行确认。准确率验证通过再放开 `auto-send: true`(若 v2 实现)。

## 输入 / 输出
**输入:** 真实 WeLink CLI、配置好的 `pm-agent.yaml`、`contacts.yaml`
**输出:** 真实 WeLink 消息发送 + 完整 follow_up_log

## 验收标准
1. ✅ 配置 `notifier.mode: welink_cli` 后,`pm-agent send` 调用真实 CLI 而不是 mock
2. ✅ 给一个白名单单人发送测试通过,WeLink 客户端真实收到
3. ✅ CLI 返回非零退出码时,`send_status=failed` + error 字段含 stderr
4. ✅ 超时被正确捕获,不卡死后续候选
5. ✅ 失败重试 1 次后仍失败 → 标 failed,后续候选继续
6. ✅ Windows 任务计划正确触发,日志可追溯
7. ✅ 整周连续运行无意外退出

## 依赖
- **阻塞前置**:#01 ~ #04 全部完成
- **外部依赖**:真实 WeLink CLI(由 @ttttstc 提供安装包/接口文档)

## 参考
- 收敛设计文档:§3 D4(接口隔离)、§11(里程碑)
- 原 PRD:§10(WeLink CLI 集成)、§19(边界与安全)
