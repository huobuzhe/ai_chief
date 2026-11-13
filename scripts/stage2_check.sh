#!/usr/bin/env bash
# 阶段 2 提测脚本（Git Bash 版）
# 用法：在项目根目录执行  bash scripts/stage2_check.sh
set -u

cd "$(dirname "$0")/.." || exit 1

if [ ! -f pyproject.toml ]; then
  echo "[FAIL] 请在项目根目录运行：bash scripts/stage2_check.sh"
  exit 1
fi

echo "=== 阶段 2 提测：9 项检查 ==="
uv run python scripts/verify_stage2.py all
code=$?

echo ""
if [ $code -eq 0 ]; then
  echo "阶段 2 提测全部通过"
else
  echo "阶段 2 提测存在未通过项，请按 [FAIL] 提示修复"
fi
exit $code
