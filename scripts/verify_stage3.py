# scripts/verify_stage3.py
"""
阶段 3 分步验证脚本（手册每章"验证"步骤统一用它，避免 PowerShell 粘贴引号被吃）。

用法（项目根目录执行）：
    uv run python scripts/verify_stage3.py <子命令>

子命令：
    deps     依赖是否齐全（langgraph / langchain-tavily / langchain-core / pydantic）
    data     营养库与用户画像数据文件可读、条目数达标
    config   配置项齐全（CHAT_MODEL / VISION_MODEL）
    profile  用户画像模块可用（查得到、字段齐全、未知用户走默认）
    state    ChefState 状态定义完整（8 个业务字段）
    tools    两个工具可用：calculate_nutrition / search_local_recipes
    nodes    5 个节点函数都能导入（拼装图的前置条件）
    graph    StateGraph 能编译，且拓扑是"并行 + fan-in"
    rag      本地菜谱检索能返回"补全后的完整菜谱"（依赖阶段 2 的库）
    rank     重排打分可用（过敏剔除 + 不同画像不同排序）
    e2e      端到端真实跑一遍 5 节点工作流（会调用大模型，约 10~30 秒）
    health   后端 /health 不退化
    all      以上全部（提测用）
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    tag = "[OK]  " if ok else "[FAIL]"
    msg = f"{tag} {name}" + (f"  ->  {detail}" if detail else "")
    print(msg)
    RESULTS.append(ok)
    return ok


# ---------------------------------------------------------------- 依赖 / 数据 / 配置
def check_deps() -> None:
    try:
        import langgraph  # noqa: F401
        from langgraph.graph import StateGraph, START, END, MessagesState  # noqa: F401
        from langgraph.graph.message import add_messages  # noqa: F401
        from langchain_tavily import TavilySearch  # noqa: F401
        from langchain_core.tools import tool  # noqa: F401
        report("依赖齐全（langgraph / langchain-tavily / langchain-core）", True)
    except Exception as e:
        report("依赖缺失", False, f"{type(e).__name__}: {e}")


def check_data() -> None:
    files = {
        "营养库": ROOT / "app_my" / "tools" / "data" / "ingredients_nutrition.json",
        "用户画像": ROOT / "app_my" / "db" / "data" / "user_profiles.json",
    }
    for label, path in files.items():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            n = len(data.get("items", data))
            report(f"{label}可读：{path.name}（{n} 条）", n >= 3)
        except Exception as e:
            report(f"{label}读取失败：{path.name}", False, str(e))


def check_config() -> None:
    try:
        from app_my.core.config import settings
        has_chat = bool(getattr(settings, "CHAT_MODEL", ""))
        has_vision = bool(getattr(settings, "VISION_MODEL", ""))
        report("CHAT_MODEL 已配置", has_chat, getattr(settings, "CHAT_MODEL", ""))
        report("VISION_MODEL 已配置（手册 4.2 步新增）", has_vision,
               getattr(settings, "VISION_MODEL", "未定义：请按手册给 config.py 加 VISION_MODEL 字段"))
    except Exception as e:
        report("配置读取失败", False, str(e))


def check_profile() -> None:
    try:
        from app_my.db.user_profile import DEFAULT_PROFILE, get_user_profile
        known = get_user_profile("U001")
        unknown = get_user_profile("不存在的用户")
        guest = get_user_profile(None)
        keys_ok = all(k in known for k in DEFAULT_PROFILE)
        report("已知用户画像字段齐全", keys_ok, f"U001 goal={known.get('goal')} 忌口={known.get('forbidden')}")
        report("未知用户走默认画像", unknown.get("goal") == "普通" and unknown.get("user_id") == "不存在的用户")
        report("匿名访问走 guest 画像", guest.get("user_id") == "guest")
    except Exception as e:
        report("用户画像模块异常", False, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- 状态 / 工具 / 节点
def check_state() -> None:
    try:
        from app_my.agents.state import ChefState
        need = ["ingredients", "nutrition", "recipes", "ranked_recipes", "user_profile", "image_url", "final_answer"]
        hints = getattr(ChefState, "__annotations__", {})
        missing = [k for k in need if k not in hints]
        report(f"ChefState 定义完整（含 messages + {len(need)} 个业务字段）", not missing, f"缺：{missing}" if missing else "")
    except Exception as e:
        report("ChefState 导入失败", False, f"{type(e).__name__}: {e}")


def check_tools() -> None:
    try:
        from app_my.tools.nutrition_tool import calculate_nutrition
        res = calculate_nutrition.invoke({"ingredients": ["鸡蛋 2个", "西红柿 2个", "盐 1克"]})
        ok = res["coverage"] == 1.0 and res["total_estimated"]["calories"] > 0
        report(f"calculate_nutrition 可用（估算 {res['total_estimated']['calories']} 千卡，"
               f"调味料 {len(res['seasonings'])} 项不计入）", ok)
    except Exception as e:
        report("calculate_nutrition 不可用", False, f"{type(e).__name__}: {e}")
    try:
        from app_my.tools.recipe_rag_tool import search_local_recipes
        hits = search_local_recipes.invoke({"query": "鸡胸肉 减脂", "k": 2})
        ok = bool(hits) and all(h.get("ingredients") and h.get("steps") for h in hits)
        report(f"search_local_recipes 可用（命中 {len(hits)} 条并补全食材/步骤）", ok)
    except Exception as e:
        report("search_local_recipes 不可用", False, f"{type(e).__name__}: {e}")


def check_nodes() -> None:
    mods = {
        "recognizer": ("app_my.agents.recognizer", "recognize_node"),
        "nutritionist": ("app_my.agents.nutritionist", "nutrition_node"),
        "recommender": ("app_my.agents.recommender", "recommend_node"),
        "ranker": ("app_my.agents.ranker", "rank_node"),
        "output": ("app_my.agents.output", "output_node"),
    }
    bad = []
    for label, (mod, fn) in mods.items():
        try:
            m = __import__(mod, fromlist=[fn])
            getattr(m, fn)
        except Exception as e:
            bad.append(f"{label}({type(e).__name__})")
    report("5 个节点函数均可导入", not bad, f"异常：{bad}" if bad else "recognize/nutrition/recommend/rank/output")


def check_graph() -> None:
    try:
        from app_my.agents.coordinator import build_workflow
        graph = build_workflow().get_graph()
        nodes = {n for n in graph.nodes}
        edges = {(e.source, e.target) for e in graph.edges}
        expect_nodes = {"recognize", "nutrition", "recommend", "rank", "output"}
        expect_edges = {
            ("recognize", "nutrition"), ("recognize", "recommend"),
            ("nutrition", "rank"), ("recommend", "rank"),
            ("rank", "output"),
        }
        missing_nodes = expect_nodes - nodes
        missing_edges = expect_edges - edges
        ok = not missing_nodes and not missing_edges and "__start__" in nodes
        report("Graph 编译成功，5 节点齐全且是并行 fan-in 拓扑", ok,
               f"缺节点{missing_nodes} 缺边{missing_edges}" if not ok else "START→recognize→(nutrition‖recommend)→rank→output→END")
    except Exception as e:
        report("Graph 编译失败", False, f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- 检索 / 重排 / 端到端
def check_rag() -> None:
    try:
        from app_my.tools.recipe_rag_tool import local_recipe_search
        hits = local_recipe_search("鸡胸肉 西兰花 减脂", k=3)
        names = [h["name"] for h in hits]
        ok = bool(hits) and all(isinstance(h["tags"], list) and isinstance(h["difficulty_level"], int) for h in hits)
        report("本地菜谱检索返回补全后的完整菜谱", ok, " / ".join(names))
    except Exception as e:
        report("本地菜谱检索失败", False, f"{type(e).__name__}: {e}")


def check_rank() -> None:
    try:
        from app_my.agents.ranker import rank_recipes
        from app_my.db.user_profile import get_user_profile
        from app_my.tools.recipe_rag_tool import local_recipe_search
        pool = local_recipe_search("虾仁 西兰花 减脂", k=8)
        soft = rank_recipes(pool, get_user_profile("U001"))   # 过敏虾仁
        hard = rank_recipes(pool, get_user_profile("U002"))   # 增肌
        allergy_ok = all("虾仁" not in " ".join(r["ingredients"]) for r in soft)
        reason_ok = bool(soft) and bool(soft[0].get("rank_reasons"))
        report("过敏食材被剔除", allergy_ok)
        report("不同画像给出不同排序", (not soft or not hard or soft[0]["name"] != hard[0]["name"]),
               f"U001 首选 {soft[0]['name'] if soft else '-'} / U002 首选 {hard[0]['name'] if hard else '-'}")
        report("推荐理由已生成", reason_ok, "；".join(soft[0]["rank_reasons"]) if reason_ok else "")
    except Exception as e:
        report("重排打分失败", False, f"{type(e).__name__}: {e}")


def check_e2e() -> None:
    import asyncio

    async def run() -> tuple:
        from app_my.agents.coordinator import chat_coordinator
        pieces = []
        async for piece in chat_coordinator(
            text="我有鸡蛋3个、两个西红柿、一把西兰花，想做个减脂的晚饭",
            image_url=[], user_id="U001",
        ):
            pieces.append(piece)
        return "".join(pieces)

    try:
        final = asyncio.run(run())
        ok = (len(final) > 200 and "```json" not in final and "[识别]" not in final
              and any(k in final for k in ("鸡蛋", "西红柿", "西兰花")))
        report(f"端到端 5 节点跑通，最终回复 {len(final)} 字（干净 Markdown）", ok,
               "" if ok else final[:120])
    except Exception as e:
        report("端到端失败", False, f"{type(e).__name__}: {e}")


def check_health() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8002/health", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            report("/health 不退化", '"ok"' in body, body)
    except Exception as e:
        report("后端 /health 未通过", False, "请先启动 main.py：" + str(e))


CHECKS = {
    "deps": check_deps, "data": check_data, "config": check_config, "profile": check_profile,
    "state": check_state, "tools": check_tools, "nodes": check_nodes, "graph": check_graph,
    "rag": check_rag, "rank": check_rank, "e2e": check_e2e, "health": check_health,
}


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        order = ["deps", "data", "config", "profile", "state", "tools", "nodes",
                 "graph", "rag", "rank", "e2e", "health"]
        for name in order:
            print(f"--- {name} ---")
            CHECKS[name]()
    elif cmd in CHECKS:
        CHECKS[cmd]()
    else:
        print("未知子命令:", cmd)
        print("可用:", " / ".join(list(CHECKS) + ["all"]))
        sys.exit(2)
    if RESULTS and all(RESULTS):
        print("== 本轮全部通过 ==")
        sys.exit(0)
    if RESULTS and not all(RESULTS):
        print("== 存在未通过项，看上面 [FAIL] 行 ==")
        sys.exit(1)


if __name__ == "__main__":
    main()
