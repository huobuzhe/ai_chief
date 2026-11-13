# v3 阶段 6 提测脚本（PowerShell 5.1 用，UTF-8 BOM）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\stage6_check.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$Py = ".venv\Scripts\python.exe"

Write-Host "=== 阶段 6 提测开始 ===" -ForegroundColor Cyan

Write-Host "--- 1/4 单元测试 ---"
& $Py -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] 单测未全绿" -ForegroundColor Red; exit 1 }

Write-Host "--- 2/4 容器状态 ---"
foreach ($c in @("ai_chief_pgvector", "ai_chief_redis", "ai_chief_pgbouncer",
                 "ai_chief_neo4j", "ai_chief_etcd", "ai_chief_minio", "ai_chief_milvus")) {
    $running = docker ps --format '{{.Names}}' | Select-String -SimpleMatch $c
    if ($running) {
        Write-Host "[OK]   容器 $c 运行中" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] 容器 $c 未运行" -ForegroundColor Red
        exit 1
    }
}

Write-Host "--- 3/4 全量验证 ---"
& $Py scripts\verify_stage6.py deps
& $Py scripts\verify_stage6.py conn
& $Py scripts\verify_stage6.py search
& $Py scripts\verify_stage6.py kg
& $Py scripts\verify_stage6.py hybrid
& $Py scripts\verify_stage6.py flag

Write-Host "--- 4/4 对比实验 ---"
& $Py scripts\retrieval_compare.py

Write-Host ""
Write-Host "阶段 6 提测全部通过" -ForegroundColor Green