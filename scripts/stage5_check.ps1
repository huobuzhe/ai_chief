# 阶段 5 提测脚本（PowerShell 5.1 用，UTF-8 BOM）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\stage5_check.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$Py = ".venv\Scripts\python.exe"

Write-Host "=== 阶段 5 提测开始 ===" -ForegroundColor Cyan

Write-Host "--- 1/3 单元测试 ---"
& $Py -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 单测未全绿" -ForegroundColor Red; exit 1 }

Write-Host "--- 2/3 容器与服务 ---"
foreach ($c in @("ai_chief_pgvector", "ai_chief_redis", "ai_chief_pgbouncer")) {
    $running = docker ps --format '{{.Names}}' | Select-String -SimpleMatch $c
    if ($running) {
        Write-Host "[OK]   容器 $c 运行中" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] 容器 $c 未运行" -ForegroundColor Red
        exit 1
    }
}
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:9002/health" -TimeoutSec 5
    if ($resp.status -ne "ok") { throw "health 异常" }
} catch {
    Write-Host "[FAIL] 9002 无响应：先启动 main.py" -ForegroundColor Red
    exit 1
}

Write-Host "--- 3/3 全量验证 ---"
& $Py scripts\verify_stage5.py deps
& $Py scripts\verify_stage5.py pgb
& $Py scripts\verify_stage5.py routing
& $Py scripts\verify_stage5.py cache

Write-Host ""
Write-Host "阶段 5 提测全部通过" -ForegroundColor Green