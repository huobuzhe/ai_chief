# 阶段 2 提测脚本（终端版）
# 用法：在项目根目录执行  .\scripts\stage2_check.ps1
# 注意：请直接运行脚本文件，不要把内容粘贴到终端执行（会丢引号）

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path pyproject.toml)) {
    throw "请在项目根目录运行：.\scripts\stage2_check.ps1"
}

Write-Host "=== 阶段 2 提测：9 项检查 ==="
& uv run python scripts/verify_stage2.py all
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "阶段 2 提测全部通过"
} else {
    Write-Host ""
    Write-Host "阶段 2 提测存在未通过项，请按 [FAIL] 提示修复"
    exit 1
}
