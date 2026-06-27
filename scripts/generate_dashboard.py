"""生成当前项目大盘看板（临时脚本）"""
from pathlib import Path

from pm_agent.tools.excel import read_excel
from pm_agent.tools.dashboard import write_html_dashboard

excel_path = Path("source/项目630流水线排期计划.xlsx")
result = read_excel(excel_path)
items = result["items"]
print(f"读入 {len(items)} 条事项")

out = write_html_dashboard(
    items,
    run_id="current_dashboard",
    db_path="state/pm-agent.db",
    output_dir="state/dashboards",
)
print(f"看板路径: {out['path']}")
print(f"文件大小: {out['size_bytes']:,} bytes ({out['size_bytes']/1024:.1f} KB)")
print(f"统计: {out['stats']}")