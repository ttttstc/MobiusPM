"""gen_message — 消息模板渲染（覆盖全部状态/场景）"""
from __future__ import annotations

_MAX_LENGTH = 1000

_TEMPLATES: dict[str, str] = {
    # ── 验收确认 ──
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
    # ── 进度检查 ──
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
    # ── 排期确认 ──
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
    # ── 缺截止日期 ──
    "due_date_missing": (
        "【项目事项信息补齐】\n\n"
        "你负责的事项【{title}】当前缺少计划完成时间。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "当前状态：{status}\n"
        "优先级：{priority}\n\n"
        "请补充计划完成时间，便于项目经理跟踪 630 风险。"
    ),
    # ── 关闭确认 ──
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
    # ── 数据质量 ──
    "data_quality": (
        "【项目事项数据完善】\n\n"
        "你负责的事项【{title}】存在数据不完整问题。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "优先级：{priority}\n"
        "当前状态：{status}\n"
        "缺失信息：{remark}\n\n"
        "请补充缺失信息，以便准确跟踪事项进展。\n"
        "如需协助请联系 PM。"
    ),
    # ── 升级提醒 ──
    "escalation": (
        "【项目事项升级提醒】\n\n"
        "你负责的事项【{title}】已被标记为需关注。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "优先级：{priority}\n"
        "当前状态：{status}\n"
        "计划时间：{due_date}\n\n"
        "原因：{remark}\n\n"
        "该事项已催办多次但进展不明确。请在今天内回复：\n"
        "1. 当前实际进展和阻塞点；\n"
        "2. 需要什么资源或协助；\n"
        "3. 是否需要在 PM 层面协调。"
    ),
    # ── 停滞警告 ──
    "stagnation_alert": (
        "【项目事项停滞提醒】\n\n"
        "你负责的事项【{title}】较长时间未更新状态。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "优先级：{priority}\n"
        "当前状态：{status}\n"
        "本次状态持续时间：{remark}\n\n"
        "请确认：\n"
        "1. 该事项当前是否仍在推进；\n"
        "2. 近期是否有计划更新或交付；\n"
        "3. 是否需要调整优先级或重新排期。"
    ),
    # ── 回退警告 ──
    "regression_alert": (
        "【项目事项状态回退提醒】\n\n"
        "你负责的事项【{title}】曾被标记为已关闭，但现在重新出现。\n\n"
        "项目：{project}\n"
        "事项ID：{item_id}\n"
        "优先级：{priority}\n"
        "当前状态：{status}\n"
        "来源：{source}\n\n"
        "请说明：\n"
        "1. 该事项重新打开的原因；\n"
        "2. 是否需要调整处理方案；\n"
        "3. 预计再次关闭的时间。"
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

    reminder_type 支持:
      acceptance_confirm / progress_check / schedule_confirm /
      due_date_missing / close_confirm / data_quality /
      escalation / stagnation_alert / regression_alert

    context 填充: title, project, source, priority, handler, due_date, remark, status

    返回 {"message": str, "truncated": bool}
    """
    ctx = context or {}
    template = _TEMPLATES.get(reminder_type, _TEMPLATES["progress_check"])

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
