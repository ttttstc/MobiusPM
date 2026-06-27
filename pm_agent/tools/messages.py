"""gen_message — 消息模板渲染（PRD §10.3）"""
from __future__ import annotations

_MAX_LENGTH = 1000

_TEMPLATES: dict[str, str] = {
    "acceptance_confirm": (
        "【项目事项验收确认】\n\n"
        "你负责的事项【{title}】当前状态为【待验收】。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "来源：{source}\n"
        "优先级：{priority}\n"
        "当前处理方：{handler}\n"
        "计划时间：{due_date}\n\n"
        "请今天下班前确认：\n"
        "1. 是否已经完成验收；\n"
        "2. 如果未完成，当前阻塞是什么；\n"
        "3. 是否可以关闭该事项。\n\n"
        "如需我更新项目台账，请回复最新进展。"
    ),
    "progress_check": (
        "【项目事项进展跟进】\n\n"
        "你负责的事项【{title}】当前仍在【开发中】。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "优先级：{priority}\n"
        "计划时间：{due_date}\n"
        "当前说明：{remark}\n\n"
        "请补充：\n"
        "1. 当前完成进度；\n"
        "2. 是否存在风险或依赖；\n"
        "3. 预计完成时间。"
    ),
    "schedule_confirm": (
        "【项目事项排期确认】\n\n"
        "你负责的事项【{title}】当前为【待排期】。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "优先级：{priority}\n"
        "当前处理方：{handler}\n\n"
        "请确认：\n"
        "1. 是否纳入 630 前处理；\n"
        "2. 计划完成时间；\n"
        "3. 是否需要其他团队协助。"
    ),
    "due_date_missing": (
        "【项目事项信息补齐】\n\n"
        "你负责的事项【{title}】当前缺少计划完成时间。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "当前状态：{status}\n"
        "优先级：{priority}\n\n"
        "请补充计划完成时间，便于项目经理跟踪 630 风险。"
    ),
    "close_confirm": (
        "【项目事项关闭确认】\n\n"
        "你负责的事项【{title}】已完成或接近闭环。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "来源：{source}\n"
        "优先级：{priority}\n"
        "当前状态：{status}\n\n"
        "请确认该事项是否可以正式关闭，或仍有关键动作待完成。"
    ),
}


def _fmt(val: str | None) -> str:
    return val if val else "未填写"


def gen_message(
    item_id: str,
    reminder_type: str,
    context: dict | None = None,
    max_length: int = _MAX_LENGTH,
) -> dict:
    """
    按模板渲染 WeLink 消息。

    context 可选 dict 用于填充模板占位符（title, project, source, priority, handler, due_date, remark, status）。
    缺少的字段显示"未填写"。

    返回 {"message": str, "truncated": bool}
    """
    ctx = context or {}
    template = _TEMPLATES.get(reminder_type, _TEMPLATES.get("progress_check"))
    if template is None:
        template = _TEMPLATES["progress_check"]

    filled = template.format(
        title=_fmt(ctx.get("title")),
        project=_fmt(ctx.get("project")),
        item_id=item_id,
        source=_fmt(ctx.get("source")),
        priority=_fmt(ctx.get("priority")),
        handler=_fmt(ctx.get("handler")),
        due_date=_fmt(ctx.get("due_date")),
        remark=_fmt(ctx.get("remark")),
        status=_fmt(ctx.get("status")),
    )

    truncated = False
    if len(filled) > max_length:
        filled = filled[: max_length - 3] + "..."
        truncated = True

    return {"message": filled, "truncated": truncated}
