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
            "这是'建议'而非指令——LLM 可采纳、补充或拒绝，但拒绝时必须在 decision_log 中记录理由。"
            "每条建议含 rule_id、reminder_type、severity、rationale_hint。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_items": {
                    "type": "array",
                    "description": "read_excel 返回的 WorkItem 列表",
                    "items": {"type": "object"},
                },
            },
            "required": ["work_items"],
        },
    },
    {
        "name": "gen_message",
        "description": (
            "根据 reminder_type 选择模板，渲染 WeLink 消息文本。"
            "支持 4 类模板: acceptance_confirm / progress_check / schedule_confirm / due_date_missing / close_confirm。"
            "占位符未填值显示'未填写'，消息超过 max_length 自动截断。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "事项 ID"},
                "reminder_type": {
                    "type": "string",
                    "enum": ["acceptance_confirm", "progress_check", "schedule_confirm", "due_date_missing", "close_confirm"],
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
]
