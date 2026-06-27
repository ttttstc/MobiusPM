"""pytest fixtures — 自包含，不依赖生产 Excel。"""
from pathlib import Path

import openpyxl
import pytest

HEADERS = [
    "序号", "用户问题原文", "问题状态", "来源", "issue",
    "优先级", "当前处理方(依次依赖)", "责任人", "支持情况",
    "计划时间", "说明",
]


@pytest.fixture
def fixture_xlsx(tmp_path: Path) -> Path:
    """
    最小可复现 xlsx，覆盖全部 9 种已知状态组合 + 多责任人 + 边界情况。

    共 11 行数据，行数固定，测试可直接 assert 等值。
    """
    rows = [
        # (序号, 原文, 问题状态, 来源, issue, 优先级, 处理方, 责任人, 支持情况, 计划时间, 说明)
        (1, "事项A-待验收", "Open", "CANN", None, "必备(630前)", "Pipeline", "张三", "待验收", None, "备注A"),
        (2, "事项B-已完成已关闭", "Close", "计算", None, "增强(争取630)", "GitCode", "李四", "已完成", None, None),
        (3, "事项C-挂起", "Open", "GitCode", None, "长期演进(630后)", "Pipeline,GitCode", "王五", "挂起(630后分析)", None, None),
        (4, "事项D-待排期", "Open", "CANN", None, "必备(630前)", "Repo", "赵六", "待排期", None, None),
        (5, "事项E-完成待关闭", "Open", "计算", None, "必备(630前)", "Pipeline", "钱七", "已完成", None, None),
        (6, "事项F-开发中", "Open", "GitCode", None, "必备(630前)", "Pipeline,Repo", "孙八", "开发中", None, "开发中备注"),
        (7, "事项G-待验收待关闭", "Close", "CANN", None, "必备(630前)", "Repo,Pipeline", "周九", "待验收", None, None),
        (8, "事项H-重复单", "Open", "计算", None, "拒绝(不处理)", "Pipeline", "吴十", "重复单", None, None),
        (9, "事项I-拒绝", "Open", "CANN", None, "拒绝(不处理)", "GitCode", "郑十一", "拒绝", None, None),
        (10, "事项J-多责任人", "Open", "CANN", None, "必备(630前)", "Pipeline", "张三/李四", "待验收", None, None),
        (11, "事项K-双状态拒绝", "Close", "计算", None, "拒绝(不处理)", "Pipeline", "王十二", "拒绝", None, None),
    ]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "630攻关问题清单"
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)

    path = tmp_path / "fixture.xlsx"
    wb.save(str(path))
    wb.close()
    return path
