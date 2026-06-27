"""TOOL_REGISTRY + TOOL_SCHEMAS — 供 M2 直接喂进 Anthropic SDK tools= 参数"""

TOOL_REGISTRY = {
    "read_excel": "pm_agent.tools.excel.read_excel",
    "query_state": "pm_agent.tools.state.query_state",
    "write_decision": "pm_agent.tools.state.write_decision",
    "update_context_brief": "pm_agent.tools.state.update_context_brief",
    "query_rule_suggestions": "pm_agent.tools.rules.query_rule_suggestions",
    "gen_message": "pm_agent.tools.messages.gen_message",
    "send_welink": "pm_agent.tools.notifier.send_welink",
    "ask_human": "pm_agent.tools.human.ask_human",
    "query_history": "pm_agent.tools.state.query_history",
    "write_project_report": "pm_agent.tools.report.write_project_report",
    "write_html_dashboard": "pm_agent.tools.dashboard.write_html_dashboard",
}

TOOL_SCHEMAS = [
    {
        "name": "read_excel",
        "description": (
            "只读读取 Excel 项目台账主表，将每一行标准化为 WorkItem。"
            "返回全部事项列表（JSON-serializable），包含 item_id、状态映射、多责任人拆分结果。"
            "无副作用，主表 mtime 不变。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "excel_path": {"type": "string", "description": "Excel 文件路径"},
                "sheet_name": {"type": "string", "description": "Sheet 名称，默认 630攻关问题清单"},
            },
            "required": ["excel_path"],
        },
    },
    {
        "name": "query_state",
        "description": (
            "查询事项在 SQLite 中的持久化状态：上次被扫到的时间、催办次数、上次催办时间/类型、"
            "是否已失联(vanished)。item_id 为空时返回全部事项摘要。"
            "用于 agent 在决策前了解事项的历史上下文。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "事项 ID（可选，为空查全部）"},
            },
        },
    },
    {
        "name": "write_decision",
        "description": (
            "将 LLM 的每次决策（催/不催/升级/等待）写入 decision_log，附带 rationale。"
            "rationale 非空且 ≥20 字符强制。这是 P4 可审计要求的核心工具。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision_type": {
                    "type": "string",
                    "enum": ["followup", "skip", "escalate", "wait", "risk_alert", "brief"],
                    "description": "决策类型",
                },
                "rationale": {"type": "string", "description": "决策理由，至少 20 字符"},
                "run_id": {"type": "string", "description": "本次运行 ID"},
                "target_item_id": {"type": "string", "description": "目标事项 ID（可空）"},
                "action_taken": {"type": "string", "description": "实际执行的工具调用（可空）"},
            },
            "required": ["decision_type", "rationale", "run_id"],
        },
    },
    {
        "name": "update_context_brief",
        "description": (
            "在每次 agent loop 结束时写一份项目当前状态摘要（300-500 token）。"
            "下次 loop 启动时自动加载，作为长期记忆入口。"
            "brief 长度 ≤1000 字符。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "brief": {"type": "string", "description": "项目状态摘要文本"},
                "run_id": {"type": "string", "description": "本次运行 ID"},
            },
            "required": ["brief", "run_id"],
        },
    },
    {
        "name": "query_rule_suggestions",
        "description": (
            "对 WorkItem 列表执行 DQ 数据质量规则 + R 跟催规则扫描，返回建议列表。"
            "规则覆盖：DQ-001缺责任人 / DQ-002负载过重 / DQ-003缺日期 / "
            "R-001待验收 / R-002完成待关闭 / R-003开发中 / R-004临期 / R-005待排期 / "
            "R-007催办无响应 / R-008状态停滞 / R-009状态回退 / R-010反复催办。"
            "若提供 db_path 则执行历史依赖规则（R-007~R-010），否则仅执行无状态规则。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_items": {
                    "type": "array",
                    "description": "read_excel 返回的 WorkItem 列表",
                    "items": {"type": "object"},
                },
                "db_path": {
                    "type": "string",
                    "description": "SQLite 路径（可选，提供则执行历史依赖规则）",
                },
            },
            "required": ["work_items"],
        },
    },
    {
        "name": "gen_message",
        "description": (
            "根据 reminder_type 选择模板，渲染 WeLink 消息文本。"
            "支持 9 类模板: acceptance_confirm / progress_check / schedule_confirm / "
            "due_date_missing / close_confirm / data_quality / escalation / stagnation_alert / regression_alert。"
            "占位符未填值显示'未填写'，消息超过 max_length 自动截断。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "事项 ID"},
                "reminder_type": {
                    "type": "string",
                    "enum": [
                        "acceptance_confirm", "progress_check", "schedule_confirm",
                        "due_date_missing", "close_confirm", "data_quality",
                        "escalation", "stagnation_alert", "regression_alert",
                    ],
                    "description": "跟催类型",
                },
                "context": {"type": "object", "description": "模板占位符填充数据（title, project, source, priority, handler, due_date, remark, status）"},
            },
            "required": ["item_id", "reminder_type"],
        },
    },
    {
        "name": "send_welink",
        "description": (
            "发送 WeLink 消息给责任人。**内部强制安全检查（P2 原则）**，LLM 绕不过："
            "幂等去重、单责任人当天上限、单次运行上限、白名单校验、confirmation_token 校验。"
            "必须先调 ask_human 获取有效 confirmation_token 才能发送。"
            "副作用：写入 follow_up_log 和 mock_sent.jsonl。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "事项 ID"},
                "owner": {"type": "string", "description": "责任人姓名"},
                "welink_id": {"type": "string", "description": "WeLink ID"},
                "message": {"type": "string", "description": "消息文本"},
                "reminder_type": {"type": "string", "description": "跟催类型"},
                "confirmation_token": {"type": "string", "description": "ask_human 返回的确认 token（必须）"},
                "run_id": {"type": "string", "description": "本次运行 ID"},
            },
            "required": ["item_id", "owner", "welink_id", "message", "reminder_type", "confirmation_token", "run_id"],
        },
    },
    {
        "name": "ask_human",
        "description": (
            "将跟催候选清单展示给 PM，等待人工确认。"
            "返回 confirmation_token，send_welink 必须携带此 token 才能发送。"
            "MVP: 终端 stdin 交互；M2 可替换为更友好的界面。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "candidates": {
                    "type": "array",
                    "description": "待确认的 ReminderCandidate 列表",
                    "items": {"type": "object"},
                },
                "question": {"type": "string", "description": "向 PM 提出的问题"},
                "run_id": {"type": "string", "description": "本次运行 ID"},
            },
            "required": ["candidates", "run_id"],
        },
    },
    {
        "name": "query_history",
        "description": (
            "查询某个事项的完整历史记录：状态变化、催办记录、决策记录。"
            "返回时间序列数据，帮助 agent 在做决策前了解事项的前因后果。"
            "与 query_state 的区别：query_state 返回当前快照，query_history 返回时间序列。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "事项 ID"},
                "max_records": {"type": "integer", "description": "每种类型的最大记录数，默认 10"},
            },
            "required": ["item_id"],
        },
    },
    {
        "name": "write_project_report",
        "description": (
            "在 agent loop 结束时生成结构化项目巡检报告（PRD 要求），写入 state/reports/。"
            "报告应采用 markdown 格式，必须包含以下章节："
            "1) 项目总览（事项总数、活跃数、已闭环数）"
            "2) 状态分布（按 normalized_status 统计）"
            "3) 风险诊断 TOP5（高严重度事项，说明原因）"
            "4) 趋势变化（相比上次报告的新增/闭环风险）"
            "5) 建议行动（具体催办建议，含 item_id）。"
            "同时自动存一份摘要到 context_brief 作为跨周期记忆。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "report_content": {"type": "string", "description": "完整的项目巡检报告（markdown）"},
                "run_id": {"type": "string", "description": "本次运行 ID"},
            },
            "required": ["report_content", "run_id"],
        },
    },
    {
        "name": "write_html_dashboard",
        "description": (
            "生成项目大盘 HTML 看板（DESIGN.md 视觉系统）。"
            "输入 read_excel 返回的 WorkItem 列表，可选 db_path 启用历史依赖规则。"
            "输出单文件自包含 HTML（CSS inline、JS inline、无外链）到 state/dashboards/，"
            "PM 可邮件发送或浏览器本地打开。文件大小通常 < 30KB。"
            "看板分三层：项目总览（4 数字面板）→ 风险明细（高/中风险表格）→ 建议行动（按 reminder_type 分组）。"
            "建议在 write_project_report 之后调用，作为可视化补充。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_items": {
                    "type": "array",
                    "description": "read_excel 返回的 WorkItem 列表",
                    "items": {"type": "object"},
                },
                "run_id": {"type": "string", "description": "本次运行 ID"},
                "db_path": {"type": "string", "description": "SQLite 路径（可选，提供则启用 R-007~R-010）"},
            },
            "required": ["work_items", "run_id"],
        },
    },
]
