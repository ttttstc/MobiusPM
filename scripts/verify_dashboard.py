"""验证 dashboard HTML 结构"""
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
            if tag in self.tags:
                self.errors.append(f"Unclosed before </{tag}>: stack={self.tags[-10:]}")
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
    print(f"HTML size: {len(html):,} bytes")
    print(f"Errors: {len(v.errors)}")
    for e in v.errors:
        print(f"  {e}")


if __name__ == "__main__":
    main()