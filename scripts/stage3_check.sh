#!/usr/bin/env bash
# 阶段 3 提测脚本（Git Bash 版）
# 用法：在项目根目录执行  bash scripts/stage3_check.sh
# 说明：脚本文件请直接运行，不要粘贴到终端（会丢引号、路径也会错）
set -u

cd "$(dirname "$0")/.." || exit 1

if [ ! -f pyproject.toml ]; then
  echo "[FAIL] 请在项目根目录运行：bash scripts/stage3_check.sh"
  exit 1
fi

echo "=== 阶段 3 提测：12 组检查（含 1 次真实大模型端到端） ==="
uv run python scripts/verify_stage3.py all
code=$?

echo ""
if [ $code -eq 0 ]; then
  echo "阶段 3 提测全部通过"
else
  echo "阶段 3 提测存在未通过项，请按 [FAIL] 提示修复"
fi
exit $code
