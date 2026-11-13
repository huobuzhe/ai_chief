#!/usr/bin/env bash
# =============================================================================
# scripts/ci_local.sh —— 阶段 10：在本地把 CI 流水线的每一步跑一遍（Git Bash 版）
# =============================================================================
# 为什么要这个脚本：
#   云端 CI（Gitee Go）的 YAML 你在本机**跑不了**——它只在 Gitee 服务器上生效。
#   如果直接把 .gitee/workflows/pipeline.yml 提交上去才发现命令写错，
#   一来一回要好几分钟，而且错误藏在云端日志里不好查。
#   这个脚本把流水线里每一条命令按顺序在你本机跑一遍：
#   能过 = 这些命令本身是通的，push 之后失败的风险就只剩"云端环境差异"这一项。
#
# 和流水线唯一的区别：
#   流水线里是 `pip install -r requirements.txt`（每次全新环境都要装，慢）；
#   这里改成"检查关键依赖在不在"，缺哪个提示哪个——本机早就装好了，
#   没必要每次跑都重装一遍（本项目依赖装一次要 5~6 分钟）。
#
# 用法（项目根目录执行）：
#   bash scripts/ci_local.sh
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."

# 解释器允许覆盖：PY=/path/to/python.exe bash scripts/ci_local.sh
PY="${PY:-./.venv3/Scripts/python.exe}"
if [ ! -f "$PY" ]; then
  echo "[中止] 找不到虚拟环境解释器: $PY"
  echo "       请在项目根目录执行，或显式指定：PY=<绝对路径> bash scripts/ci_local.sh"
  exit 1
fi

FAILED=0
# 小工具：跑一条命令，成功打 PASS、失败打 FAIL 并记一笔（不中断，跑完全部再看）
run_step() {
  local title="$1"; shift
  echo ""
  echo "--------------------------------------------------------------"
  echo " 步骤: $title"
  echo "--------------------------------------------------------------"
  if "$@"; then
    echo "[PASS] $title"
  else
    echo "[FAIL] $title"
    FAILED=$((FAILED + 1))
  fi
}

echo "=============================================================="
echo " 阶段 10 · CI 本地等价验证  $(date '+%Y-%m-%d %H:%M:%S')"
echo " 对应 .gitee/workflows/pipeline.yml 的每个 step"
echo "=============================================================="

# ---------- 阶段一：单元测试（对应 CI 的 test-stage） ----------
run_step "Python 版本（CI 用的是 3.13）" "$PY" -V

# CI 里是 pip install -r requirements.txt；本地改成"检查关键依赖能 import"
run_step "检查关键依赖是否已安装" "$PY" -c "
import importlib.util, sys
need = ['fastapi', 'uvicorn', 'sqlalchemy', 'redis', 'pytest', 'httpx', 'yaml', 'pydantic_settings']
missing = [m for m in need if importlib.util.find_spec(m) is None]
if missing:
    print('缺失依赖:', missing)
    print('请执行: $PY -m pip install -r requirements.txt')
    sys.exit(1)
print('关键依赖齐全:', len(need), '个')
"

# 只跑 tests/unit：这一批不依赖任何外部服务，是 CI 里唯一能稳定跑通的部分
run_step "跑单元测试（tests/unit，不依赖外部服务）" \
  "$PY" -m pytest tests/unit -q --no-header -p no:cacheprovider

# ---------- 阶段二：配置与脚本校验（对应 CI 的 build-stage 第一个 step） ----------
run_step "校验生产编排 docker-compose.prod.yml 可被解析" "$PY" -c "
import yaml
d = yaml.safe_load(open('docker/docker-compose.prod.yml', encoding='utf-8'))
assert 'services' in d, 'compose 文件里没有 services'
print('生产编排解析通过，共', len(d['services']), '个服务:', list(d['services']))
"

run_step "校验压测脚本语法" "$PY" -m py_compile benchmarks/locustfile.py scripts/locust_report.py

run_step "冒烟：核心模块能被导入" "$PY" -c "
import app_my.core.config, app_my.core.model_router, app_my.core.mock_llm
print('核心模块 import OK（含阶段10新增的 mock_llm）')
"

# ---------- 镜像构建（本机也能做，但很慢，默认跳过） ----------
echo ""
echo "--------------------------------------------------------------"
echo " 镜像构建（CI 的最后一个 step）——默认跳过"
echo " 想在本机真跑一遍就执行："
echo "   docker build -f docker/Dockerfile.svc -t ai-chief-svc:prod ."
echo "--------------------------------------------------------------"

echo ""
echo "=============================================================="
if [ "$FAILED" -eq 0 ]; then
  echo " 全部通过 ✅ —— 流水线的命令在本机都跑得通，可以 push 了"
else
  echo " 有 $FAILED 个步骤失败 ❌ —— 修完再 push，否则云端一定会红"
fi
echo "=============================================================="
exit "$FAILED"