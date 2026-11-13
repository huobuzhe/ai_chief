#!/usr/bin/env bash
# 阶段 1-2 提测脚本：自检 + 启动 + 不退化（Bash / Git Bash 版）
# 用法：
#   cd F:/pycharm_aiprogram/ai_sichu
#   bash scripts/stage1-2_check.sh
set -e

# 自动回到项目根目录（兼容 Git Bash 与 macOS/Linux）
cd "$(dirname "$0")/.."

# 守卫：必须已经在项目根目录
if [ ! -f "main.py" ] || [ ! -d "app_my" ]; then
    echo "❌ 请在项目根目录（含 main.py 和 app_my/ 的目录）运行本脚本"
    echo "   当前目录: $(pwd)"
    exit 1
fi

# 守卫：git 仓库检查（阶段 1-2 要求 .env.example 已 add）
if [ ! -d ".git" ]; then
    echo "⚠️ 当前还不是 git 仓库。请先在项目根目录执行：git init"
    echo "   之后再运行本脚本。"
    exit 1
fi

echo "==[1/9]== 目录 + __init__.py"
for d in app_my/core app_my/db app_my/db/models app_my/knowledge app_my/tools app_my/middleware tests tests/unit tests/integration scripts docker; do
    [ -d "$d" ] || { echo "❌ 缺目录 $d"; exit 1; }
done
for f in app_my/core/__init__.py app_my/db/__init__.py app_my/db/models/__init__.py app_my/knowledge/__init__.py app_my/tools/__init__.py app_my/middleware/__init__.py tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py scripts/__init__.py; do
    [ -f "$f" ] || { echo "❌ 缺文件 $f"; exit 1; }
done
echo "✓ 目录与 __init__.py 齐全"

echo "==[2/9]== 没有 __int__.py"
if find app_my tests -name '__int__.py' -type f 2>/dev/null | grep -q .; then
    echo "❌ 仍存在 __int__.py"; exit 1
fi
echo "✓"

echo "==[3/9]== 依赖齐全（重点：oss2）"
uv run python -c "import oss2; print('oss2', oss2.__version__)"
uv run python -c "import fastapi, uvicorn, pydantic_settings; print('OK')"
echo "✓ 依赖 OK"

echo "==[4/9]== config.py"
uv run python -c "from app_my.core.config import settings; assert settings.PORT == 8002, settings.PORT"
echo "✓ PORT=8002"

echo "==[5/9]== 惰性 LLM"
uv run python -c "from app_my.core.models import has_api_key; print('has_api_key=', has_api_key())"
echo "✓"

echo "==[6/9]== JSON 日志"
uv run python -c "from app_my.core.logging import setup_logging, logger; setup_logging(); logger.info('ok')" | grep -q '"level": "INFO"'
echo "✓"

echo "==[7/9]== main 启动 + /health + CORS + presign + /chat/stream"
# 清理可能残留的 main 进程
PID_FILE="main.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ]; then
        kill "$OLD_PID" 2>/dev/null || true
    fi
fi

nohup uv run python main.py > ./main.log 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
cleanup() {
    kill "$PID" 2>/dev/null || true
    rm -f "$PID_FILE"
}
trap cleanup EXIT

# 轮询代替 sleep
READY=0
for i in $(seq 1 30); do
    if curl -fs http://127.0.0.1:8002/health > /dev/null 2>&1; then
        echo "✓ 服务就绪（${i}s）"
        READY=1
        break
    fi
    sleep 1
done
[ "$READY" -eq 1 ] || { echo "❌ 服务 30s 内未就绪"; exit 1; }

# /health
curl -fs http://127.0.0.1:8002/health | tee ./health.json
grep -q '"status":"ok"' ./health.json || { echo "❌ /health 未通过"; exit 1; }

# CORS null
curl -sI -H "Origin: null" -X OPTIONS http://127.0.0.1:8002/oss/presign -H "Access-Control-Request-Method: GET" | grep -qi "access-control-allow-origin: null" || { echo "❌ CORS null 未通过"; exit 1; }
echo "✓ CORS null 通过"

# presign
curl -fs "http://127.0.0.1:8002/oss/presign?filename=test.jpg" | grep -q '"uploadUrl"' || { echo "❌ /oss/presign 未通过"; exit 1; }
echo "✓ /oss/presign 通过"

# 流式对话（120 秒超时，防止模型慢）
uv run python - <<'PY' || { echo "❌ /chat/stream 未通过"; exit 1; }
import requests
r = requests.post('http://127.0.0.1:8002/chat/stream',
    json={'message':'用一句话推荐一道鸡蛋和西红柿的菜','image_url':[],'thread_id':'stage1-2-test'},
    stream=True, timeout=120)
assert r.status_code == 200, r.status_code
chunks = []
for line in r.iter_lines():
    if line:
        chunks.append(line.decode('utf-8', 'ignore'))
        if len(chunks) >= 3:
            break
assert chunks, "没有返回任何 chunk"
print('✓ /chat/stream 通过，返回 chunk 数:', len(chunks))
PY

echo "✓ 全部不退化验证通过"

echo "==[8/9]== .env.example 已跟踪"
git ls-files .env.example | grep -q . && echo "✓" || { echo "❌ .env.example 未跟踪"; exit 1; }

echo "==[9/9]== .env 不在 git tracked"
git ls-files .env | grep -q . && { echo "❌ .env 被错误跟踪"; exit 1; } || echo "✓"

echo "🎉 阶段 1-2 全部通过"
