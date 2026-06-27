# [M2] Agent 骨架:Claude Agent SDK 集成 + 跟催场景最小可跑 loop

## 目标
把 M1 的工具层接入 Claude Agent SDK,实现第一个可跑的 agentic loop。本 issue 完成后,**`python -m pm_agent wake` 能跑出完整闭环**:agent 自主决策 → 调 ask_human 跟 PM 对话 → 确认后 mock 发送 → 写决策 → 退出。**这是项目的核心里程碑——agent 真正"活"起来。**

## 范围
- 安装 `anthropic` Python SDK,配置 API key 加载(env / config 二选一)
- `pm_agent/agent.py` 核心 loop 骨架(见设计文档 §3.3 伪代码,落成真实代码)
- `pm_agent/prompts/system.md` — 系统提示:
  - 身份("你是 MobiusPM 项目决策助理...")
  - 目标("帮 PM 在 630 前完成 P0/P1 事项闭环,识别风险,提出建议")
  - 当前 loop 规则("每轮先查规则建议,综合判断后跟 PM 确认,确认后发送,最后写 brief 退出")
  - 安全边界声明("发送必经 ask_human · 决策必须 write_decision · token 上限 N")
  - 工具使用指引(每个 tool 什么时候用)
- `pm_agent/prompts/initial_user.md.j2` — 初始 user message 模板:
  - 本次触发原因(wake / cron)
  - 上次 context_brief(可空,首次跑时空)
  - 最近 decision_log(可空)
  - 最近 follow_up_log(可空)
- `pm_agent/__main__.py` 的 `wake` 子命令:
  - 调用 `run_agent(trigger_reason='wake')`
  - 显示 loop 进度(每轮工具调用打印到 stderr)
  - 退出时显示本次 token 用量 + 决策摘要
- Token 上限保护:超过配置 `max_tokens_per_loop`(默认 50k)时强制结束,落 brief 后退出
- 错误恢复:工具调用抛异常时,把异常作为 `tool_result.content` 喂回 agent,让 LLM 决定下一步
- 日志:每轮 LLM 调用 + 工具调用全程写 `state/agent_runs/{run_id}.jsonl`,便于复盘
- ask_human 工具升级(从 M1-B 的 stdin 临时方案 → 终端友好显示):
  - candidates 列表用 rich 库或纯文本表格展示
  - 支持 PM 输入 "all" / "none" / 指定 ID / 跳过
  - 输入"q" 中断 loop

## 设计要点(强约束)
1. **system prompt 必须明确所有 P1~P6 原则**,让 LLM 理解:它可以判断规则、不能跳过 ask_human、必须写 rationale、必须更新 brief 后才结束。
2. **退出条件**:`stop_reason == "end_turn"` 即退出。但在退出前,system prompt 要求 agent 必须先调用 `update_context_brief`——通过 prompt 引导 + 工具描述提醒。
3. **wake 模式 = 有 PM 在场 = 可以调 ask_human**;cron 模式(M4 实现)= PM 不在场 = system prompt 切换为禁用 send,只做"决策准备"。
4. **token 用量监控**:每轮记录 input/output token,累计超过上限触发强制结束(写 brief → 退出)。
5. **错误透传**:工具异常不让 agent 崩溃,而是作为 observation 喂回去,LLM 自己处理。这是 agentic loop 的健壮性关键。
6. **每个 run 一个 run_id**(uuid 或 `wake_yyyymmdd_HHMMSS`),贯穿 follow_up_log / decision_log / agent_runs 日志,可对账。
7. **不实现 cron 触发** — 那是 M4。
8. **不实现真 WeLink CLI** — 仍走 mock。
9. **不实现 brief 跨周期注入** — 那是 M3。本 issue 只写 brief,不读旧 brief。

## 输入 / 输出
**输入:** `wake` 命令、ANTHROPIC_API_KEY、M1 全部工具
**输出:**
- 一次完整 agent 对话日志(stderr + jsonl)
- 一次决策写入 `decision_log`
- 一次 brief 写入 `context_brief`
- 若 PM 确认了发送,`follow_up_log` 多几行(mock)

## 验收标准
1. ✅ `python -m pm_agent wake` 跑通,无异常退出
2. ✅ Agent 至少调用了 4 个不同的工具(read_excel / query_rule_suggestions / ask_human / send_welink/write_decision)
3. ✅ PM 在 ask_human 阶段输入"跳过",所有候选都 skip,decision_log 仍记录"PM 决定本轮不发"
4. ✅ PM 在 ask_human 阶段输入有效 ID,confirmation_token 流转正确,send_welink 走通
5. ✅ Agent 在 end_turn 前调用了 update_context_brief(可观察 db 内新增一行)
6. ✅ 强制构造场景:让 LLM 不调 ask_human 直接 send_welink(可通过 system prompt 注入测试指令)→ 工具返回 `error: no_confirmation_token`,LLM 收到 observation 后能改走 ask_human(验证 P2 边界 + 错误恢复)
7. ✅ Token 上限 1000 配置下,agent 会被强制结束并落 brief
8. ✅ 完整 agent_runs jsonl 文件可复盘:每轮的 LLM input/output、工具调用、结果完整
9. ✅ run_id 在 decision_log / follow_up_log / context_brief / agent_runs 四处一致

## 依赖
- **阻塞前置**:#1 (M1-A)、#2 (M1-B)
- **外部依赖**:Anthropic API key、网络通畅(调 claude-opus-4-8)

## 参考
- 设计文档:§1(四层架构)、§2 P1~P6、§3(SDK 路径)、§6(触发模式)
- Anthropic 官方:https://www.anthropic.com/research/building-effective-agents
- Anthropic Cookbook agents 范式:https://github.com/anthropics/anthropic-cookbook
