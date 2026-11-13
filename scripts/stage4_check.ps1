# scripts/stage4_check.ps1
# 阶段 4 一键提测：pytest + verify_stage4
$ErrorActionPreference = "Stop"

$PY = "F:\pycharm_aiprogram\ai_chief\.venv3\Scripts\python.exe"

cd F:\pycharm_aiprogram\ai_chief

Write-Host "==> 0. 阶段 4 数据库补丁（幂等，可反复执行）" -ForegroundColor Cyan
docker exec ai_chief_pgvector psql -U ai_sichu -d ai_sichu -c "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_tenant_id INTEGER; CREATE INDEX IF NOT EXISTS ix_users_default_tenant_id ON users(default_tenant_id);"
if ($LASTEXITCODE -ne 0) { Write-Error "pytest 失败，先排查" }

Write-Host "==> 1. 启动 uvicorn后台..." -ForegroundColor Cyan
$job = Start-Job -ScriptBlock {
    Set-Location F:\pycharm_aiprogram\ai_chief
    & "F:\pycharm_aiprogram\ai_chief\.venv3\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 9002
}
Start-Sleep -Seconds 5

Write-Host "==> 2. 默认单测套件应 62 passed" -ForegroundColor Cyan
& $PY -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Error "pytest 失败，先排查" }

Write-Host "==> 3. 跑 verify_stage4.py" -ForegroundColor Cyan
& $PY scripts/verify_stage4.py

Write-Host "==> 4. 关闭 uvicorn" -ForegroundColor Cyan
Stop-Job $job -ErrorAction SilentlyContinue
Remove-Job $job -ErrorAction SilentlyContinue

Write-Host "=== 阶段 4 提测完成 ===" -ForegroundColor Green
