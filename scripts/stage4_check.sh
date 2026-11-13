#!/usr/bin/env bash
# scripts/stage4_check.sh
set -euo pipefail
cd /f/pycharm_aiprogram/ai_chief

PY="/f/pycharm_aiprogram/ai_chief/.venv3/Scripts/python.exe"

echo "==> 0. 阶段 4 数据库补丁（幂等，可反复执行）"
docker exec ai_chief_pgvector psql -U ai_sichu -d ai_sichu -c "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_tenant_id INTEGER; CREATE INDEX IF NOT EXISTS ix_users_default_tenant_id ON users(default_tenant_id);"

echo "==> 1. 启动 uvicorn（后台）..."
$PY -m uvicorn main:app --host 0.0.0.0 --port 9002 &
UVI_PID=$!
sleep 5

echo "==> 2. 默认单测套件（应 62 passed）"
$PY -m pytest -q

echo "==> 3. 跑 verify_stage4.py"
$PY scripts/verify_stage4.py

echo "==> 4. 关闭 uvicorn"
kill $UVI_PID 2>/dev/null || true

echo "=== 阶段 4 提测完成 ==="
