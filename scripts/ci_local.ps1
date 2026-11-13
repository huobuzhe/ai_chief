# =============================================================================
# scripts/ci_local.ps1 —— 阶段 10：本地跑一遍 CI 的每个步骤（PowerShell 5.1 版）
# =============================================================================
# 和 scripts/ci_local.sh 是同一件事的两种终端写法。
# 作用：把 .gitee/workflows/pipeline.yml 里的命令在本机跑一遍——
#       云端流水线你没法在本地跑，但如果这些命令本机都通，push 上去出问题的概率就很低。
#
# 用法（项目根目录执行）：
#   .\scripts\ci_local.ps1
#
# 🔴 如果提示"无法加载文件，因为在此系统上禁止运行脚本"，先执行一次：
#       Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#    （只对当前窗口生效，关掉就恢复）
# =============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$PY = if ($env:BENCH_PY) { $env:BENCH_PY } else { Join-Path $Root '.venv3\Scripts\python.exe' }
if (-not (Test-Path $PY)) {
    Write-Host "[中止] 找不到虚拟环境解释器: $PY" -ForegroundColor Red
    exit 1
}

$Failed = 0

# 跑一条命令并记录成败。
# 用 $LASTEXITCODE 判断外部命令结果（不能用 $?，那是判断 PowerShell 语句自己的）
function Invoke-Step {
    param([string]$Title, [scriptblock]$Action)
    Write-Host ""
    Write-Host "--------------------------------------------------------------"
    Write-Host " 步骤: $Title"
    Write-Host "--------------------------------------------------------------"
    try {
        & $Action
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[FAIL] $Title（退出码 $LASTEXITCODE）" -ForegroundColor Red
            $script:Failed++
        } else {
            Write-Host "[PASS] $Title"
        }
    } catch {
        Write-Host "[FAIL] $Title —— $($_.Exception.Message)" -ForegroundColor Red
        $script:Failed++
    }
}

Write-Host "=============================================================="
Write-Host (" 阶段 10 · CI 本地等价验证  " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host " 对应 .gitee/workflows/pipeline.yml 的每个 step"
Write-Host "=============================================================="

# ---------- 阶段一：单元测试 ----------
Invoke-Step "Python 版本（CI 用的是 3.13）" { & $PY -V }

Invoke-Step "检查关键依赖是否已安装" {
    & $PY -c @"
import importlib.util, sys
need = ['fastapi','uvicorn','sqlalchemy','redis','pytest','httpx','yaml','pydantic_settings']
missing = [m for m in need if importlib.util.find_spec(m) is None]
if missing:
    print('缺失依赖:', missing); sys.exit(1)
print('关键依赖齐全:', len(need), '个')
"@
}

Invoke-Step "跑单元测试（tests/unit，不依赖外部服务）" {
    & $PY -m pytest tests/unit -q --no-header -p no:cacheprovider
}

# ---------- 阶段二：配置与脚本校验 ----------
Invoke-Step "校验生产编排 docker-compose.prod.yml 可被解析" {
    & $PY -c @"
import yaml
d = yaml.safe_load(open('docker/docker-compose.prod.yml', encoding='utf-8'))
assert 'services' in d, 'compose 文件里没有 services'
print('生产编排解析通过，共', len(d['services']), '个服务:', list(d['services']))
"@
}

Invoke-Step "校验压测脚本语法" {
    & $PY -m py_compile benchmarks/locustfile.py scripts/locust_report.py
}

Invoke-Step "冒烟：核心模块能被导入" {
    & $PY -c @"
import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm
print('核心模块 import OK（含阶段10新增的 mock_llm）')
"@
}

Write-Host ""
Write-Host "=============================================================="
if ($Failed -eq 0) {
    Write-Host " 全部通过 —— 流水线的命令在本机都跑得通，可以 push 了" -ForegroundColor Green
} else {
    Write-Host " 有 $Failed 个步骤失败 —— 修完再 push，否则云端一定会红" -ForegroundColor Red
}
Write-Host "=============================================================="
exit $Failed