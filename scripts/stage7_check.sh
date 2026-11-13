#!/bin/bash
# Phase 7 提测脚本（Git Bash）
set -e
cd /f/pycharm_aiprogram/ai_chief
echo "=== 容器状态 ==="
docker compose -f docker/docker-compose.v3.yml ps prometheus grafana alertmanager loki promtail
echo ""
echo "=== 验证脚本 ==="
.venv3/Scripts/python.exe scripts/verify_stage7.py all
echo ""
echo "=== 全量 pytest ==="
.venv3/Scripts/python.exe -m pytest -q