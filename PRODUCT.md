# Product

## Register

product

## Users

PM（项目经理），使用桌面浏览器在每个工作周期查看项目健康大盘。
场景：早晨打开链接，10–30 秒内识别「今天必须处理的 3 件事」，必要时进入每个 risk 的详细页面。
工具栈：PM 已经在 Excel / GitCode / WeLink 三个系统间切换，看板需要与这些既有界面「像出自同一双手」。

## Product Purpose

把 pm_agent 的项目跟催输出升级为可一眼扫读的网页大盘，取代当前 markdown 报告需要滚动阅读的形式。
看板不替代决策，而是把决策所需的信息密度压缩在一个屏幕，让 PM 30 秒内从「健康度→高风险→今日行动」三层信息完成扫描。
成功标准：PM 打开看板后，能在不切换标签页的情况下决定下一步要催谁、催什么。

## Brand Personality

三个词：精准、克制、紧迫。
声音：数据先于形容词，数字先于解释，行动先于叙述。
参考点（具体吸收的细节）：
- **Linear 的 issue 列表**：行密度、单色状态点（绿/黄/红）、左对齐编号列、不做卡片堆叠
- **Vercel 的 status 仪表盘**：深色背景 + 高亮单色 + 数字面板偏左、状态色环极小
- **终端 / htop 风格的紧凑布局**：状态条、ASCII 分隔符、表格先于卡片

明确不做什么（Anti-references）：
- 不要 SaaS 渐变卡片（玻璃拟态、bg-clip text、阴影浮夸）
- 不要「Dashboard starter kit」式的 4 卡片网格（总数 / 活跃 / 风险 / 已闭环）
- 不要每节都加 uppercase eyebrow（OVERVIEW / RISKS / ACTIONS）
- 不要 emoji 图标、不要装饰性插画
- 不要让数字面板成为「hero-metric template」（大数字 + 小标签 + 渐变强调）
- 不要 Lottie / 过度动效

## Design Principles

1. **数字先于叙述**——数字和状态条占主导，文字解释是支撑。
2. **三层信息垂直折叠**——「健康度总览 → 风险明细 → 今日行动」从上至下，不要 tab 切换或侧栏。
3. **不创造新视觉语言**——复用 Linear / Vercel / 终端的紧凑版面，避免发明装饰元素。
4. **深色单一主题**——不做 light/dark 切换，只做深色仪表盘。明暗随系统不必要，因为这是工作工具不是文档。
5. **每行有信息**——不留装饰空白；间距用来分组而不是呼吸。

## Accessibility & Inclusion

- 颜色不是唯一信息载体：状态同时用形状（●/▲/■）+ 文本（已超期/临期/正常）传递。
- 文本对比度 ≥ 4.5:1，关键数字 ≥ 7:1（深色背景下用浅色文字，不靠饱和度）。
- 提供 reduced-motion 媒体查询支持：禁用入场动画。
- 数据通过表格语义标签暴露，可被屏幕阅读器线性朗读。
- 字体使用 system mono + system sans，不依赖网络字体加载。

## Scope Note（本次）

本次新增一个独立工具 `write_html_dashboard`，由 wake/cron/audit 流程可选调用，
输入 `query_rule_suggestions` 输出 + WorkItem 列表，输出单文件 `state/dashboards/{date}_{run_id}.html`。
HTML 自包含（CSS inline、JS inline、无外链），可邮件发送、可浏览器本地打开。