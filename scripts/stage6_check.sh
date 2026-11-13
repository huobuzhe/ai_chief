#!/bin/bash
# v3 阶段 6 提测脚本（Git Bash 用）
# 前置：① 全部容器已启动（含 milvus 全家桶）  ② main.py 已启动（9002）  ③ Milvus 已导入数据
set -u
cd "$(dirname "$0")/.."
PY=".venv/Scripts/python.exe"

echo "=== 阶段 6 提测开始 ==="

echo "--- 1/4 单元测试 ---"
"$PY" -m pytest -q
RC=$?
if [ $RC -ne 0 ]; then echo "[FAIL] 单测未全绿"; exit $RC; fi

echo "--- 2/4 容器状态 ---"
for c in ai_chief_pgvector ai_chief_redis ai_chief_pgbouncer ai_chief_neo4j ai_chief_etcd ai_chief_minio ai_chief_milvus; do
  if docker ps --format '{{.Names}}' | grep -q "^$c$"; then
    echo "[OK]   容器 $c 运行中"
  else
    echo "[FAIL] 容器 $c 未运行：docker compose -f docker/docker-compose.v3.yml up -d"
    exit 1
  fi
done

echo "--- 3/4 全量验证 ---"
"$PY" scripts/verify_stage6.py deps
"$PY" scripts/verify_stage6.py conn
"$PY" scripts/verify_stage6.py search
"$PY" scripts/verify_stage6.py kg
"$PY" scripts/verify_stage6.py hybrid
"$PY" scripts/verify_stage6.py flag

echo "--- 4/4 对比实验 ---"
"$PY" scripts/retrieval_compare.py

echo ""
echo "阶段 6 提测全部通过（对比数字已输出，记进收官文档）"