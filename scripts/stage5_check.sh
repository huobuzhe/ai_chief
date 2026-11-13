#!/bin/bash
# 阶段 5 提测脚本（Git Bash 用）
# 前置：① pgvector + redis + pgbouncer 容器已启动  ② main.py 已启动（9002）
set -u
cd "$(dirname "$0")/.."
PY=".venv/Scripts/python.exe"

echo "=== 阶段 5 提测开始 ==="

echo "--- 1/3 单元测试 ---"
"$PY" -m pytest -q
RC=$?
if [ $RC -ne 0 ]; then
  echo "[FAIL] 单测未全绿"
  exit $RC
fi

echo "--- 2/3 容器与服务 ---"
for c in ai_chief_pgvector ai_chief_redis ai_chief_pgbouncer; do
  if docker ps --format '{{.Names}}' | grep -q "^$c$"; then
    echo "[OK]   容器 $c 运行中"
  else
    echo "[FAIL] 容器 $c 未运行：docker compose -f docker/docker-compose.v3.yml up -d"
    exit 1
  fi
done
curl -s http://127.0.0.1:9002/health | grep -q ok || { echo "[FAIL] 9002 无响应"; exit 1; }

echo "--- 3/3 全量验证 ---"
"$PY" scripts/verify_stage5.py deps
"$PY" scripts/verify_stage5.py pgb
"$PY" scripts/verify_stage5.py routing
"$PY" scripts/verify_stage5.py cache

echo ""
echo "阶段 5 提测全部通过"