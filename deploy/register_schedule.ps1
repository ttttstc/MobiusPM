# MobiusPM Windows Task Scheduler 注册脚本
# 用法: powershell -ExecutionPolicy Bypass -File deploy/register_schedule.ps1
# 或右键 "使用 PowerShell 运行"

param(
    [string]$TaskName = "MobiusPM-Cron",
    [string]$PythonPath = "",
    [string]$ProjectRoot = "",
    [string]$Schedule = "daily",  # daily | hourly | custom
    [string]$At = "09:00",
    [int]$IntervalMinutes = 30
)

$ErrorActionPreference = "Stop"

# ── 自动检测 ──
if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
if (-not $PythonPath) {
    $PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PythonPath) {
        $PythonPath = (Get-Command python3 -ErrorAction SilentlyContinue).Source
    }
}

Write-Host "============================================"
Write-Host "MobiusPM · 注册计划任务"
Write-Host "============================================"
Write-Host "任务名称 : $TaskName"
Write-Host "项目目录 : $ProjectRoot"
Write-Host "Python   : $PythonPath"
Write-Host "调度模式 : $Schedule"

if (-not $PythonPath) {
    Write-Error "未找到 Python，请设置 PythonPath 参数或确保 python 在 PATH 中"
    exit 1
}

if (-not (Test-Path $ProjectRoot)) {
    Write-Error "项目目录不存在: $ProjectRoot"
    exit 1
}

Push-Location $ProjectRoot

# ── 检查配置文件 ──
$configFile = Join-Path $ProjectRoot "config/pm-agent.yaml"
if (-not (Test-Path $configFile)) {
    Write-Error "配置文件不存在: $configFile"
    exit 1
}

# ── 确认 API Key ──
$apiKey = $env:ANTHROPIC_API_KEY
if (-not $apiKey) {
    Write-Warning "未设置 ANTHROPIC_API_KEY 环境变量"
    Write-Host "请确保在系统环境变量中设置 ANTHROPIC_API_KEY，或在 config/pm-agent.yaml 中配置 api_key"
}

# ── 确认状态目录 ──
$stateDir = Join-Path $ProjectRoot "state"
if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    Write-Host "已创建 state/ 目录"
}

# ── 确认日志目录 ──
$logDir = Join-Path $ProjectRoot "state/logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# ── 构建任务动作 ──
$actionArgs = "-m pm_agent cron --quiet"
$logFile = Join-Path $logDir "cron_`$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

$action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $actionArgs `
    -WorkingDirectory $ProjectRoot

# ── 构建触发器 ──
switch ($Schedule) {
    "daily" {
        $trigger = New-ScheduledTaskTrigger -Daily -At $At
    }
    "hourly" {
        $trigger = New-ScheduledTaskTrigger -Once -At "00:00" -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)
    }
    "custom" {
        Write-Host "自定义模式：请在任务计划程序中手动配置触发器"
        $trigger = $null
    }
    default {
        Write-Error "未知调度模式: $Schedule (支持 daily | hourly | custom)"
        exit 1
    }
}

# ── 任务设置 ──
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# ── 注册任务 ──
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

try {
    # 先删除旧任务（如果存在）
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $taskParams = @{
        Action      = $action
        Principal   = $principal
        Settings    = $settings
        TaskName    = $TaskName
        Description = "MobiusPM 定时跟催 agent — 扫描 Excel 台账并评估是否需要催办"
    }
    if ($trigger) {
        $taskParams.Trigger = $trigger
    }

    Register-ScheduledTask @taskParams | Out-Null

    Write-Host ""
    Write-Host "✓ 任务 '$TaskName' 注册成功"
    if ($Schedule -eq "daily") {
        Write-Host "  每天 $At 自动运行 python -m pm_agent cron"
    } elseif ($Schedule -eq "hourly") {
        Write-Host "  每 $IntervalMinutes 分钟自动运行 python -m pm_agent cron"
    }
    Write-Host "  日志目录: $logDir"
    Write-Host ""
    Write-Host "管理命令:"
    Write-Host "  taskschd.msc              # 打开任务计划程序"
    Write-Host "  schtasks /Query /TN $TaskName  # 查看任务详情"
    Write-Host "  schtasks /Run /TN $TaskName     # 手动触发运行"
    Write-Host "  schtasks /Delete /TN $TaskName  # 删除任务"
} catch {
    Write-Error "注册失败: $_"
    Pop-Location
    exit 1
}

Pop-Location
