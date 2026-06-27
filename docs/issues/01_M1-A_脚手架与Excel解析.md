# [M1-A] 项目脚手架 + Excel 读取与 WorkItem 规范化

## 目标
建立 Python 项目脚手架,完成对源 Excel 的只读读取,把每一行规范化为 `WorkItem`,作为后续规则引擎的输入。本 issue 完成后,项目能跑出"179 条 WorkItem 的 JSON",供肉眼/diff 验证解析正确性。

## 范围
- Python 项目初始化(`pm_agent/` 包、`requirements.txt`、`README.md`)
- 配置加载(`config/pm-agent.yaml`、`config/contacts.yaml`)
- CLI 骨架(`pm-agent` 入口,先开 `scan` 子命令的解析部分)
- Excel 读取(只读,绝不写)
- WorkItem 数据类 + 规范化逻辑
- 状态映射(PRD §8 全表)
- 优先级映射 P0/P1/P2/Ignore
- 责任人多人拆分(`/ 、 , ,` 多种分隔符)
- 稳定 itemId 生成(内容指纹)

## 设计要点(已定决策)
1. **主表只读**:全程不写源 Excel。理由:xlsx 内嵌 12 张图 + 4 个 drawing,openpyxl 回写会破坏。
2. **稳定 itemId**:`sha1(来源 + "::" + normalize(用户问题原文))[:12]`。`normalize` 仅做空白压缩 + Unicode NFKC + 中文标点统一,不改原文语义。"序号"不参与 ID,因为它会随增删行漂移。
3. **日期字段**:openpyxl 直接读出 `datetime`,**不需要**做 Excel 序列号转换。空值保留为空。
4. **状态映射**:按 PRD §8 映射表实现(问题状态 × 支持情况 → 标准状态),边界状态如 `Close + 待验收` 也要覆盖。
5. **责任人脏数据**:`00853484`(工号)、`李坤(gitcode)`(同人不同写法)等保留原文进 `ownerRaw`,拆分结果进 `ownerList`,**不在此 issue 做联系人映射**(那是 M2-B 的事)。
6. **WorkItem 字段**:与 PRD §15.1 保持一致(字段名照搬,类型用 Python dataclass)。

## 输入 / 输出
**输入:** `source/项目630流水线排期计划.xlsx`,`config/pm-agent.yaml`
**输出:** `pm-agent scan --debug-dump workitems.json` 命令产出 179 条 WorkItem 的 JSON

## 验收标准
1. ✅ 解析 179 条事项(允许 ±2 偏差,因 Excel 持续更新)
2. ✅ 主表 mtime 在工具运行前后**不变**(只读验证)
3. ✅ `问题状态 × 支持情况` 9 种已知组合全部能映射出标准状态,无 `未知`
4. ✅ 优先级 4 种全部能映射为 P0/P1/P2/Ignore
5. ✅ 32 条多责任人行,`ownerList` 长度 >= 2
6. ✅ 同一 Excel 跑两次,所有 `itemId` 完全一致
7. ✅ `--debug-dump` 输出的 JSON 字段对齐 PRD §15.1

## 依赖
- 无外部依赖
- 无前置 issue

## 参考
- 收敛设计文档:`docs/MobiusPM_设计文档.md` §6(稳定 itemId)、§8(目录)、§10(配置)
- 原 PRD:`docs/Excel自动跟催Agent_PRD.md` §2(现状)、§8(状态映射)、§15.1(WorkItem)
