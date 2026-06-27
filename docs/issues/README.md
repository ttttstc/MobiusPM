# Issues 文案目录

本目录存放 5 个开发 issue 的正文文案。`gh issue create` 时通过 `-F` 参数引用,提交后即可同步到 GitHub。

| # | 文件 | 标题 | 里程碑 | 依赖 |
|---|---|---|---|---|
| 1 | [01_M1-A_脚手架与Excel解析.md](01_M1-A_脚手架与Excel解析.md) | [M1-A] 项目脚手架 + Excel 读取与 WorkItem 规范化 | M1 | — |
| 2 | [02_M1-B_规则引擎与报告.md](02_M1-B_规则引擎与报告.md) | [M1-B] 跟催规则引擎 + HTML/JSON 报告(dry-run 看板) | M1 | #1 |
| 3 | [03_M2-A_状态存储与幂等频控.md](03_M2-A_状态存储与幂等频控.md) | [M2-A] 外置状态存储(SQLite)+ 幂等 + 频控去重 | M2 | #1 #2 |
| 4 | [04_M2-B_Notifier与确认台与发送闭环.md](04_M2-B_Notifier与确认台与发送闭环.md) | [M2-B] WeLinkNotifier + Mock + 消息模板 + 命令行确认台 + send 闭环 | M2 | #1 #2 #3 |
| 5 | [05_M3_真实CLI适配与定时部署.md](05_M3_真实CLI适配与定时部署.md) | [M3] 真实 WeLink CLI 适配 + 定时任务 + 失败重试 | M3 | #1-#4,真实 CLI |

## 批量提交命令

待 `gh auth login` 重新认证后执行:

```bash
gh issue create --title "[M1-A] 项目脚手架 + Excel 读取与 WorkItem 规范化" --label "M1,enhancement" -F docs/issues/01_M1-A_脚手架与Excel解析.md
gh issue create --title "[M1-B] 跟催规则引擎 + HTML/JSON 报告(dry-run 看板)" --label "M1,enhancement" -F docs/issues/02_M1-B_规则引擎与报告.md
gh issue create --title "[M2-A] 外置状态存储(SQLite)+ 幂等 + 频控去重" --label "M2,enhancement" -F docs/issues/03_M2-A_状态存储与幂等频控.md
gh issue create --title "[M2-B] WeLinkNotifier + Mock + 消息模板 + 命令行确认台 + send 闭环" --label "M2,enhancement" -F docs/issues/04_M2-B_Notifier与确认台与发送闭环.md
gh issue create --title "[M3] 真实 WeLink CLI 适配 + 定时任务 + 失败重试" --label "M3,enhancement" -F docs/issues/05_M3_真实CLI适配与定时部署.md
```
