# Issues 文案目录(v2 · agentic loop)

本目录存放 5 个开发 issue 的正文文案。`gh issue create -F` 引用提交到 GitHub。

> **v1 历史**:首版 5 个 issue(基于"PM 跟催工具 · Skill+CLI"定位)已全部关闭,见 GitHub issues #1-#5。
> **v2 定位**:项目决策助理 · Claude Agent SDK · agentic loop。
> 详见 `docs/MobiusPM_设计文档.md`(v2)。

## 5 个新 issue

| 文件 | 标题 | 里程碑 | 依赖 |
|---|---|---|---|
| [01_M1-A_工具层基础.md](01_M1-A_工具层基础.md) | [M1-A] 工具层 Part 1:Excel + WorkItem + itemId + SQLite + 幂等频控 | M1 | — |
| [02_M1-B_工具层完成.md](02_M1-B_工具层完成.md) | [M1-B] 工具层 Part 2:规则建议器 + Notifier + 消息渲染 + ask_human + write_decision | M1 | M1-A |
| [03_M2_Agent骨架.md](03_M2_Agent骨架.md) | [M2] Agent 骨架:Claude Agent SDK + 跟催场景最小可跑 loop | M2 | M1-A, M1-B |
| [04_M3_记忆层.md](04_M3_记忆层.md) | [M3] 记忆层:context_brief + decision_log 跨周期上下文加载 | M3 | M1, M2 |
| [05_M4_周期触发与真实CLI.md](05_M4_周期触发与真实CLI.md) | [M4] 周期性触发(cron)+ 真实 WeLink CLI 适配 + 部署 | M4 | M1-M3 + 真实 CLI |

## 推进顺序

```
M1-A ──▶ M1-B ──▶ M2 ──▶ M3 ──▶ M4
   工具层               agent      记忆       上线
```

M1+M2 是核心闭环,完成后 agent 即可对话工作(走 mock)。
M3 让 agent 有"记性"。
M4 接真实 CLI + cron 上线。

## 批量提交命令

```bash
gh issue create --title "[M1-A] 工具层 Part 1:Excel + WorkItem + itemId + SQLite + 幂等频控" --label "enhancement" -F docs/issues/01_M1-A_工具层基础.md
gh issue create --title "[M1-B] 工具层 Part 2:规则建议器 + Notifier + 消息渲染 + ask_human + write_decision" --label "enhancement" -F docs/issues/02_M1-B_工具层完成.md
gh issue create --title "[M2] Agent 骨架:Claude Agent SDK + 跟催场景最小可跑 loop" --label "enhancement" -F docs/issues/03_M2_Agent骨架.md
gh issue create --title "[M3] 记忆层:context_brief + decision_log 跨周期上下文加载" --label "enhancement" -F docs/issues/04_M3_记忆层.md
gh issue create --title "[M4] 周期性触发(cron)+ 真实 WeLink CLI 适配 + 部署" --label "enhancement" -F docs/issues/05_M4_周期触发与真实CLI.md
```
