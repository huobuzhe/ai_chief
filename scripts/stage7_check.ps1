# Phase 7 提测脚本（PowerShell 5.1）
$ErrorActionPreference = "Stop"
Set-Location F:\pycharm_aiprogram\ai_chief
Write-Host "=== 容器状态 ==="
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
Write-Host ""
Write-Host "=== 验证脚本 ==="
& ".venv3\Scripts\python.exe" scripts\verify_stage7.py all
Write-Host ""
Write-Host "=== 全量 pytest ==="
& ".venv3\Scripts\python.exe" -m pytest -q