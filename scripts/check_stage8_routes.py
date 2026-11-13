# scripts/check_stage8_routes.py —— v3 阶段 8：打印路由表里的 5 个阶段 8 端点
# 背景：本项目 FastAPI 0.141 里 include_router() 进来的路由以 _IncludedRouter 形式
#       存放在 app.routes 中，这种对象没有 .path 属性（前缀在 include_context.prefix、
#       真正的路由在 original_router.routes），所以不能再用 r.path 一条命令过滤。
import os
import sys

# 直接以 scripts/check_stage8_routes.py 方式运行时，sys.path 里只有 scripts/，
# 必须手动把项目根目录加进去才能 import main
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import main


def iter_routes(routes, prefix=""):
    # 遍历路由表；遇到 _IncludedRouter 就带上前缀递归进去；普通路由直接吐出 (完整路径, 路由对象)
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            ctx = r.include_context
            yield from iter_routes(ctx.included_router.routes, prefix + (ctx.prefix or ""))
        elif hasattr(r, "path"):
            yield prefix + r.path, r


hits = 0
for path, r in iter_routes(main.app.routes):
    if "/tasks" in path or "/ws" in path:
        methods = getattr(r, "methods", None) or "WEBSOCKET"
        print(path.ljust(34), methods)
        hits += 1

print("matched:", hits)
if hits != 5:
    raise SystemExit("[FAIL] 阶段 8 端点数量不是 5，请对照操作手册 17.4 检查 main.py 是否已保存")
