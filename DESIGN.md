# MobiusPM HTML Dashboard — Design System

> 输出物：单文件自包含 HTML（CSS inline、JS inline、无外链）
> 受众：PM 桌面浏览器深度决策场景
> 基调：Terminal / Linear / Vercel — 深色、紧凑、单一饱和强调色

---

## Color Strategy

**Restrained → Committed 边缘**：单一深色背景 + 一组冷灰文字阶 + 一组琥珀强调色（语义色：已超期/待催）。不做 light/dark 切换。

| Token | OKLCH | 用途 |
|-------|-------|------|
| `--bg` | `oklch(13% 0.012 250)` | 主背景，深蓝黑 |
| `--bg-elev` | `oklch(17% 0.015 250)` | 表格行 / 卡片抬升面，比 bg 略亮 |
| `--bg-rule` | `oklch(22% 0.018 250)` | 表格分隔线、列分隔 |
| `--ink-1` | `oklch(96% 0.005 250)` | 主要文字，接近白 |
| `--ink-2` | `oklch(78% 0.010 250)` | 次要文字（说明、列标题） |
| `--ink-3` | `oklch(55% 0.012 250)` | 三级文字（meta、时间戳） |
| `--ink-4` | `oklch(38% 0.010 250)` | 占位、disabled |
| `--accent` | `oklch(78% 0.18 75)` | 琥珀主强调（高风险、催办 CTA） |
| `--accent-soft` | `oklch(45% 0.12 75)` | 琥珀弱化（hover、次级强调） |
| `--state-ok` | `oklch(70% 0.16 145)` | 正常/已闭环，绿色 |
| `--state-warn` | `oklch(78% 0.18 75)` | 临期/中风险，琥珀 |
| `--state-crit` | `oklch(64% 0.22 25)` | 超期/高风险，红橙 |
| `--state-mute` | `oklch(50% 0.008 250)` | 静默状态 |

**对比度验证**：
- `--ink-1` on `--bg`：≥ 14:1（远超 AAA 7:1）
- `--ink-2` on `--bg`：≥ 8:1（AAA）
- `--ink-3` on `--bg`：≥ 4.7:1（AA Large）
- `--accent` on `--bg`：≥ 8:1
- 语义色同时用形状 + 文本双通道传递（颜色非唯一信息载体）

---

## Typography

**Font stack（双族）**：

```
--font-mono: ui-monospace, "SF Mono", "JetBrains Mono", "Cascadia Mono",
             "Consolas", "Liberation Mono", Menlo, monospace;
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui,
             "PingFang SC", "Microsoft YaHei", sans-serif;
```

- mono 用于数字、item_id、状态标记、时间戳
- sans 用于正文标题、说明文字、中文段落

**Fixed rem scale（product register 规则，不做 clamp）**：

| Token | Size | Weight | Letter-spacing | Use |
|-------|------|--------|---------------|-----|
| `--text-display` | 2rem | 600 | -0.02em | Header 总数大字 |
| `--text-h1` | 1.25rem | 600 | -0.01em | 章节标题 |
| `--text-h2` | 1rem | 600 | 0 | 子章节、列标题 |
| `--text-body` | 0.875rem | 400 | 0 | 表格内容、说明 |
| `--text-meta` | 0.75rem | 500 | 0.02em | 时间戳、meta 信息 |
| `--text-mono` | 0.8125rem | 400 | 0 | 数字、ID（tabular-nums） |

**调整（深色背景补偿）**：
- line-height 正文 1.55（深色下略松）
- letter-spacing mono +0.005em
- 关键数字加 `font-feature-settings: "tnum"`（等宽数字）

---

## Spacing & Layout

**Base unit：4px scale**：

```
--space-1: 4px
--space-2: 8px
--space-3: 12px
--space-4: 16px
--space-5: 24px
--space-6: 32px
--space-7: 48px
--space-8: 64px
```

**容器**：
- 最大宽度 `1200px`，居中
- 桌面左右内边距 `--space-5`（24px），≤640px 收为 `--space-3`（12px）

**Section 间距**：
- Section 之间 `--space-7`（48px），明确分组
- Section 内部 `--space-4`（16px）

**节奏**：紧凑优先。所有表格行高 32px（数据密度），章节标题上下间距对称。

---

## Components

### 1. Status Pill

**形状 + 文本双通道**：

```
● 超期 12 天     ▲ 临期 3 天     ■ 正常     ✕ 已拒绝     ⏸ 挂起
```

- shape glyph（●▲■✕⏸）用 mono 字体 14px
- 文字部分用 sans 0.8125rem
- 颜色映射：超期 = `--state-crit`、临期 = `--state-warn`、正常 = `--state-ok`、拒绝 = `--ink-3`、挂起 = `--state-mute`
- 形状本身用 mono 字体的 ●/▲/■ Unicode，不是 emoji

### 2. Data Stat（数字面板）

非 hero-metric 模板。规则：
- 数字本身是重点，不要 gradient 强调、不要大图标
- 数字与 label 等宽对齐在水平网格中

```
总数          活跃          闭环         高风险
179           175           4            5
━━━━━━━━━    ━━━━━━━━━    ━━━━━━━━━    ━━━━━━━━━
all items     open          closed       high-risk
```

- 数字：`--text-display` 2rem mono, `font-feature-settings: "tnum"`
- label：上方 `--text-meta` 0.75rem uppercase letter-spacing 0.05em
- 下方 1px 分隔线 `--bg-rule`
- 4 列水平 grid，每列等宽，无卡片包裹

### 3. Risk Table

**非卡片堆叠，纯表格语义**：

| 状态 | ID | 标题 | 风险类型 | 责任人 | 建议 |
|------|----|----|---------|-------|------|
| ● 超期 | `8dc88...` | 流水线自定义Action：公仓跨仓引用 | 超期+待验收 | 曹禹/叶红达 | 催验收 |

- 行高 36px
- 列宽：状态 80px / ID 100px mono / 标题 flex / 风险类型 140px / 责任人 120px / 建议 flex
- 状态列使用 Status Pill 组件
- ID 列 mono + 等宽数字 + 截断（`text-overflow: ellipsis`）保留前 8 字符
- 行 hover：背景从 `--bg-elev` 微提亮到 `oklch(20% 0.015 250)`
- 行间分隔线 1px `--bg-rule`

### 4. Action Group

**按 reminder_type 分组的清单**：

```
── ACCEPTANCE_CONFIRM · 4 项 ───────────────────────────

  [1] 8dc88...  流水线自定义Action：公仓跨仓引用
       ▸ 曹禹/叶红达 · 超期 12 天 · 待验收

  [2] b8141...  yml文件删除后workflow列表移除
       ▸ 刘少强/涂键 · 超期 9 天
```

- 标题行：mono 字体 + 大写 + letter-spacing 0.05em + 分隔线延展至右边距
- 每个 action 项：标题（sans 0.875rem）+ meta 行（mono 0.75rem `--ink-3`）
- 项之间 `--space-3` 间距

### 5. Section Header

无 eyebrow、无 01/02/03 编号。

```
── 项目总览 ──────────────────────────────────────
```

- 一根 1px 横线，左侧为标题文字
- 标题用 `--text-h1` mono（不用 sans，不加 padding-left 装饰）
- 横线延展至右边距

---

## Interaction & Motion

**默认无 motion**。仪表盘是静态数据视图，不需要入场动画。

**例外**：仅状态色变化（如 hover 表格行）允许 80ms ease-out 颜色过渡。

```css
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
```

---

## Responsive

| Breakpoint | 行为 |
|-----------|------|
| ≥ 1024px | 默认桌面，4 列 stat grid、完整 risk table |
| 640–1023px | Stat grid 改为 2 列，risk table 隐藏「责任人」「建议」列 |
| < 640px | Stat grid 单列堆叠，risk table 改为卡片列表（保留状态+标题+建议），action group 标题截断 |

---

## Accessibility

- 颜色 + 形状 + 文本三通道传递状态（WCAG 1.4.1）
- 所有文字对比度 ≥ AA（关键数字 AAA）
- 表格用 `<table><thead><tbody>` 语义，状态用 `<span>` 配 `aria-label`
- 数字使用 `<td>` 不依赖纯视觉
- 标题层级 `<h1>` 一次（Header），`<h2>` 章节，`<h3>` 子项
- 字体使用 `rem`，尊重浏览器缩放
- 触摸目标 ≥ 44px（如果有交互）

---

## Anti-pattern Self-Check

- ✗ 4 卡片 hero metric 网格 — ✓ 改为水平 4 列等宽数字条
- ✗ Side-stripe `border-left` — ✓ 改用全宽分隔线
- ✗ Eyebrow uppercase 上方 — ✓ section header 改为水平线 + 标题
- ✗ Gradient text — ✓ 全单色
- ✗ Glassmorphism 模糊 — ✓ 无模糊
- ✗ Identical card grid — ✓ 表格 + 列表混排，无重复卡片
- ✗ Numbered section markers (01/02/03) — ✓ 仅按语义命名（"项目总览"）
- ✗ Emoji 图标 — ✓ 使用 mono Unicode shape（●▲■✕⏸）

---

## File Structure

输出 HTML 自包含：

```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>MobiusPM · 630 攻坚大盘 · {date}</title>
  <style>/* inline CSS, ~200 lines */</style>
</head>
<body>
  <main class="dashboard">
    <header class="dash-header">…</header>
    <section class="dash-overview">…</section>
    <section class="dash-risks">…</section>
    <section class="dash-actions">…</section>
    <footer class="dash-footer">…</footer>
  </main>
</body>
</html>
```

无外链、无 JS（除最小交互时按需添加）。文件大小目标 < 30KB。