"""验证 dashboard HTML 结构完整性"""
import sys
from html.parser import HTMLParser
from pathlib import Path


class StructureValidator(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_endtag(self, tag):
        if self.tags and self.tags[-1] == tag:
            self.tags.pop()
        else:
            # find unclosed
            if tag in self.tags:
                self.errors.append(f"Unclosed before </{tag}>: {self.tags[-5:]}")
                while self.tags and self.tags[-1] != tag:
                    self.tags.pop()
                if self.tags:
                    self.tags.pop()
            else:
                self.errors.append(f"Stray </{tag}>")


def main():
    html = Path("state/dashboards/2026-06-27_current_dashboard.html").read_text(encoding="utf-8")
    v = StructureValidator()
    v.feed(html)

    print(f"HTML size: {len(html):,} bytes ({len(html)/1024:.1f} KB)")
    print(f"Remaining unclosed tags: {len(v.tags)} {v.tags[:10] if v.tags else ''}")
    print(f"Structural errors: {len(v.errors)}")

    # 关键存在性检查
    must_have = [
        ("<h1>MobiusPM", "标题"),
        ("项目总览", "总览 section"),
        ("风险明细", "风险 section"),
        ("建议行动", "行动 section"),
        ("stat-value", "数字面板"),
        ("table class=\"risks\"", "风险表格"),
        ("action-group", "行动分组"),
        ("oklch(", "OKLCH 颜色"),
        ("@media (max-width: 1023px)", "平板响应"),
        ("@media (max-width: 639px)", "手机响应"),
        ("prefers-reduced-motion", "reduced-motion"),
        ("aria-label=", "a11y aria-label"),
        ('role="main"', "main role"),
    ]
    print("\n[关键元素]")
    for needle, label in must_have:
        present = needle in html
        mark = "✓" if present else "✗"
        print(f"  {mark} {label}: {needle}")

    # 反模式检查
    anti_patterns = [
        ("<link rel=\"stylesheet\"", "外链样式表"),
        ("@import", "@import 资源"),
        ("https://fonts", "外链字体"),
        ("linear-gradient", "渐变文字/背景"),
        ("backdrop-filter", "玻璃拟态"),
        ("<svg", "SVG 装饰图标"),
    ]
    print("\n[反模式检查]")
    for needle, label in anti_patterns:
        present = needle in html
        mark = "✓" if not present else "✗"
        print(f"  {mark} {label}: {needle}")

    sys.exit(0 if not v.errors else 1)


if __name__ == "__main__":
    main()