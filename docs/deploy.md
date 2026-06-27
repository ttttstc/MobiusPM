# MobiusPM 部署指南

## 环境要求

- Python 3.10+
- Windows 10/11 或 Linux（计划任务方式不同）
- Anthropic API Key（Claude API）

## 快速开始

### 1. 安装依赖

```powershell
pip install -r requirements.txt
```

### 2. 配置

复制并编辑配置文件：

```powershell
cp config/contacts.example.yaml config/contacts.yaml
# 编辑 config/contacts.yaml 填入团队联系人信息
```

在 `config/pm-agent.yaml` 中确认 Excel 路径：

```yaml
excel:
  path: "source/项目630流水线排期计划.xlsx"
  sheet: "630攻关问题清单"
```

### 3. 设置 API Key

```powershell
setx ANTHROPIC_API_KEY "your-key-here"
# 重启终端生效
```

或者直接在 `config/pm-agent.yaml` 中配置：

```yaml
anthropic:
  api_key: "your-key-here"
```

### 4. 验证安装

```powershell
# 干跑模式（不调 LLM，验证工具链全流程）
python -m pm_agent wake --dry-run

# 完整唤醒（需 PM 在场确认）
python -m pm_agent wake
```

## 三种运行模式

### wake 模式（PM 在场）

人工确认后再发送消息：

```powershell
python -m pm_agent wake
```

Agent 读取 Excel → 分析规则 → 展示候选清单 → 等待 PM 确认 → mock 发送。

### cron 模式（无人值守）

只做决策分析，不发送消息，结果留给下次 wake：

```powershell
python -m pm_agent cron
```

### retrospect 模式（回顾）

查看近期决策历史，不调 LLM：

```powershell
python -m pm_agent retrospect --days 7
```

## Windows 定时任务

### 自动注册

```powershell
powershell -ExecutionPolicy Bypass -File deploy/register_schedule.ps1
```

默认每天 09:00 运行 cron 模式。

### 自定义参数

```powershell
powershell -ExecutionPolicy Bypass -File deploy/register_schedule.ps1 `
    -TaskName "MobiusPM-Hourly" `
    -Schedule "hourly" `
    -IntervalMinutes 30
```

### 手动管理

```powershell
# 查看任务
schtasks /Query /TN MobiusPM-Cron

# 手动触发
schtasks /Run /TN MobiusPM-Cron

# 删除任务
schtasks /Delete /TN MobiusPM-Cron
```

## Linux cron

```bash
# 每天 9:00 运行
crontab -e
# 添加：
0 9 * * * cd /path/to/MobiusPM && python -m pm_agent cron >> state/logs/cron.log 2>&1
```

## 目录结构

```
state/
├── pm-agent.db          # SQLite 状态库
├── mock_sent.jsonl      # Mock 发送记录
├── agent_runs/          # Agent 运行日志 (jsonl)
├── archive/briefs/      # 归档的上下文字段
└── logs/                # cron 运行日志

config/
├── pm-agent.yaml        # 主配置
├── contacts.yaml        # 联系人（从 example 复制）
└── contacts.example.yaml

source/
└── 项目630流水线排期计划.xlsx  # Excel 台账
```

## 故障排查

### API Key 未设置

```
错误: 未设置 ANTHROPIC_API_KEY
```
→ 设置环境变量或在 config/pm-agent.yaml 中配置 api_key。

### Excel 文件不存在

```
FileNotFoundError: source/项目630流水线排期计划.xlsx
```
→ 确认 Excel 文件路径，或修改 config/pm-agent.yaml 中的 excel.path。

### 联系人未配置

send_welink 返回 `not_whitelisted` → 确认 config/contacts.yaml 中有对应联系人且 `enabled: true`。
