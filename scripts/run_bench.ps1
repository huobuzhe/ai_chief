# =============================================================================
# scripts/run_bench.ps1 —— 阶段 10 压测编排脚本（Windows PowerShell 5.1 版）
# =============================================================================
# 和 scripts/run_bench.sh 是同一件事的两种终端写法，参数、输出、判定口径完全一致。
# 为什么必须写两遍：
#     PowerShell 5.1 和 bash 的语法差异很大——bash 里的 && / grep / head / nohup
#     在 5.1 里要么不存在、要么语义完全不同。给一份"两边都能用"的命令是不存在的，
#     只能各写一份。如果你用的是 PowerShell，就用这个文件，别去改 sh 那个。
#
# 用法（在项目根目录 F:\pycharm_aiprogram\ai_chief 下执行）：
#   .\scripts\run_bench.ps1
#   .\scripts\run_bench.ps1 -Target gateway
#   .\scripts\run_bench.ps1 -Target all -UsersList "10,20,40,60" -Duration 45
#
# 🔴 如果提示"无法加载文件，因为在此系统上禁止运行脚本"，先执行一次：
#       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#    （-Scope Process 只对当前窗口生效，关闭就恢复，不会污染系统设置）
# =============================================================================
[CmdletBinding()]
param(
    # all = 单体 + 网关都压；monolith = 只压单体；gateway = 只压网关
    [string]$Target = 'all',
    # 逗号分隔的并发档位列表
    [string]$UsersList = '20',
    # 每档跑多少秒
    [int]$Duration = 60
)
# ---------- 路径与解释器 ----------
# 切到脚本所在目录的上一级 = 项目根目录（不管从哪调都能跑）
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
# 解释器允许覆盖：$env:BENCH_PY='D:\path\python.exe'; .\scripts\run_bench.ps1
$PY = if ($env:BENCH_PY) { $env:BENCH_PY } else { Join-Path $Root '.venv3\Scripts\python.exe' }
# 🔴 这段检查不能省。少了它，"解释器路径不存在"会被后面的错误处理吞掉，
#    屏幕上只看到"目标=monolith 并发=5"然后什么都没有、reports 目录空着，
#    人会以为是自己命令敲错了（阶段 10 第一版就踩过这个坑）。
if (-not (Test-Path $PY)) {
    Write-Host "[中止] 找不到虚拟环境解释器: $PY" -ForegroundColor Red
    Write-Host "       · 确认你在项目根目录（含 .venv3 的那个）执行"
    Write-Host "       · 或显式指定：`$env:BENCH_PY='D:\abs\path\python.exe'"
    exit 1
}
$LocustFile = Join-Path $Root 'benchmarks\locustfile.py'
if (-not (Test-Path $LocustFile)) {
    Write-Host "[中止] 找不到压测脚本: $LocustFile（当前目录 $(Get-Location)）" -ForegroundColor Red
    exit 1
}
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$ReportDir = Join-Path $Root "reports\bench_$stamp"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
# ---------- 目标表：名字 → 地址 ----------
$Targets = [ordered]@{
    'monolith' = 'http://127.0.0.1:9002'
    'gateway'  = 'http://127.0.0.1:9100'
}
Write-Host "=============================================================="
Write-Host (" 阶段 10 压测开始  " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host " 输出目录: $ReportDir"
Write-Host "=============================================================="
# ---------- 前置检查 ----------
# 用 try/catch 而不是 -ErrorAction SilentlyContinue：
# 端口不通要能立刻报错退出，不能静默跳过然后压测半天发现全是 ConnectionError
foreach ($p in @(9002, 9121, 9122, 9123, 9124)) {
    $ok = $false
    try {
        $wc = New-Object System.Net.WebClient
        $wc.Timeout = 3000
        $null = $wc.DownloadString("http://127.0.0.1:$p/health")
        $ok = $true
    }
    catch {
        $ok = $false
    }
    if (-not $ok) {
        Write-Host "[中止] 端口 $p 不通。按操作手册先把 5 个服务起好再压测。" -ForegroundColor Red
        exit 1
    }
}
Write-Host "[前置检查] 5 个服务 health 全部通过"
# 清当天配额：free 套餐 chat_daily 上限 50 次，压测几十秒就会打满，
# 之后所有 chat 请求返回 429，报告里就变成"一堆 429"，看不出真实容量。
try {
    $rawKeys = & docker exec ai_chief_redis redis-cli --scan --pattern 'quota:*' 2>&1
    $keys = $rawKeys | Where-Object { $_ -match '^quota:' }
    foreach ($k in $keys) {
        & docker exec ai_chief_redis redis-cli DEL $k | Out-Null
    }
}
catch {
    Write-Host "[警告] Redis配额清理失败，跳过配额清除" -ForegroundColor Yellow
}
Write-Host "[前置检查] 已清空当天租户配额计数"
# ---------- 主循环 ----------
foreach ($name in $Targets.Keys) {
    if ($Target -ne 'all' -and $Target -ne $name) {
        continue
    }
    $hostUrl = $Targets[$name]
    foreach ($usersRaw in ($UsersList -split ',')) {
        $usersRaw = $usersRaw.Trim()
        if (-not $usersRaw) {
            continue
        }
        if (-not [int]::TryParse($usersRaw, [ref]$users)) {
            Write-Host "[警告] 无效并发档位 $usersRaw 跳过" -ForegroundColor Yellow
            continue
        }
        # 爬坡速率：3 秒内把本档用户起完。
        # 一秒全上时头几秒全是冷启动（连接池新建、Milvus/Neo4j 重连），
        # 这些慢请求会把平均值和 P99 整体拉高，测出来的不是稳态容量。
        $spawn = [math]::Max(1, [math]::Floor($users / 3))
        $csv = Join-Path $ReportDir "${name}_u${users}"
        Write-Host ""
        Write-Host "--------------------------------------------------------------"
        Write-Host " 目标=$name  地址=$hostUrl  并发=$users  时长=${Duration}s"
        Write-Host "--------------------------------------------------------------"
        # PS5.1安全参数数组，消除反引号换行解析异常
        $locustArgs = @(
            "-f", $LocustFile,
            "--headless",
            "--host", $hostUrl,
            "--users", $users,
            "--spawn-rate", $spawn,
            "--run-time", "$($Duration)s",
            "--csv", $csv,
            "--csv-full-history",
            "--only-summary"
        )
        & $PY -m locust @locustArgs

        # 判断外部命令的退出码必须用 $LASTEXITCODE，不能用 $?
        # （$? 判断的是 PowerShell 自己的语句成功与否，对外部程序不可靠）
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[警告] 本轮 locust 退出码 $LASTEXITCODE —— 检查上面的错误输出" -ForegroundColor Yellow
        }
    } # 内层 foreach ($usersRaw) 闭合
} # 外层 foreach ($name) 闭合

Write-Host ""
Write-Host "=============================================================="
Write-Host " 压测结束，结果 CSV 在: $ReportDir"
Write-Host " 下一步：用报告脚本把它汇总成一张对比表"
Write-Host "   $PY scripts\locust_report.py --dir `"$ReportDir`""
Write-Host "=============================================================="
