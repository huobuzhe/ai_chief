# 阶段 3 提测脚本（PowerShell 版）
# 用法：在项目根目录执行  .\scripts\stage3_check.ps1
# 注意：请直接运行脚本文件，不要把内容粘贴到终端执行（会丢引号）

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path pyproject.toml)) {
    throw "请在项目根目录运行：.\scripts\stage3_check.ps1"
}

Write-Host "=== 阶段 3 提测：12 组检查（含 1 次真实大模型端到端） ==="
& uv run python scripts/verify_stage3.py all
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "阶段 3 提测全部通过"
} else {
    Write-Host ""
    Write-Host "阶段 3 提测存在未通过项，请按 [FAIL] 提示修复"
    exit 1
}
