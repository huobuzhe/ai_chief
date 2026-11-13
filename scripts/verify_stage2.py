# scripts/verify_stage2.py
"""
阶段 2 分步验证脚本（手册每章"验证"步骤统一用它，避免 PowerShell 粘贴引号被吃）。

用法（项目根目录执行）：
    uv run python scripts/verify_stage2.py <子命令>

子命令：
    deps     依赖是否齐全（jieba / rank_bm25 / langchain_community / langchain_postgres）
    docker   PGVector 容器运行中 + pgvector 扩展已启用
    config   DATABASE_URL 已切到 PostgreSQL
    data     种子数据文件可读且条数达标（>=50）
    embed    embedding 接口连通，返回 1024 维向量（走网络，稍慢）
    dbcount  数据库里向量条数 == 种子数据条数
    search   hybrid_search 混合检索可用
    loader   data_loader 模块可用（读数据 + 文本化）
    health   后端 /health 不退化
    all      以上全部（提测用）
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RESULTS: list = []


def report(name: str, ok: bool, detail: str = "") -> bool:
    tag = "[OK]  " if ok else "[FAIL]"
    msg = f"{tag} {name}" + (f"  ->  {detail}" if detail else "")
    print(msg)
    RESULTS.append(ok)
    return ok


def check_deps() -> None:
    try:
        import jieba  # noqa: F401
        import rank_bm25  # noqa: F401
        from langchain_community.retrievers import BM25Retriever  # noqa: F401
        from langchain_postgres import PGVector  # noqa: F401
        from langchain_openai import OpenAIEmbeddings  # noqa: F401
        report("依赖齐全（jieba/rank_bm25/langchain_community/langchain_postgres）", True)
    except Exception as e:
        report("依赖缺失", False, str(e))


def check_docker() -> None:
    r = subprocess.run(
        ["docker", "exec", "ai_sichu_pgvector", "pg_isready", "-U", "ai_sichu", "-d", "ai_sichu"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        report("容器 ai_sichu_pgvector 就绪", False, "先执行 docker compose -f docker/docker-compose.yml up -d")
        return
    report("容器 ai_sichu_pgvector 运行中", True)
    r2 = subprocess.run(
        ["docker", "exec", "ai_sichu_pgvector", "psql", "-U", "ai_sichu", "-d", "ai_sichu",
         "-t", "-c", "SELECT count(*) FROM pg_extension WHERE extname='vector';"],
        capture_output=True, text=True,
    )
    ok = "1" in (r2.stdout or "")
    report("pgvector 扩展已启用", ok, "" if ok else "执行手册 3.4 步的 CREATE EXTENSION 语句")


def check_config() -> None:
    from app_my.core.config import settings
    ok = settings.DATABASE_URL.startswith("postgresql")
    report("DATABASE_URL 已指向 PostgreSQL", ok, settings.DATABASE_URL if ok else "当前是 " + settings.DATABASE_URL)


def check_data() -> None:
    # 直接读 JSON（不依赖 data_loader.py：第四章验证时该模块可能还未创建）
    data_file = Path(__file__).resolve().parents[1] / "app_my" / "knowledge" / "data" / "recipes.json"
    try:
        recipes = json.loads(data_file.read_text(encoding="utf-8"))
        report(f"种子数据可读，共 {len(recipes)} 条（要求 >= 50）", len(recipes) >= 50)
    except Exception as e:
        report("种子数据读取失败", False, str(e))


def check_embed() -> None:
    try:
        from app_my.knowledge.embedding import embed_query
        vec = embed_query("西红柿炒鸡蛋")
        report(f"embedding 接口连通，维度 = {len(vec)}（要求 1024）", len(vec) == 1024)
    except Exception as e:
        report("embedding 调用失败", False, str(e))


def check_dbcount() -> None:
    try:
        from sqlalchemy import create_engine, text
        from app_my.core.config import settings
        from app_my.knowledge.data_loader import load_recipes
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            n = conn.execute(text(
                "SELECT count(*) FROM langchain_pg_embedding e "
                "JOIN langchain_pg_collection c ON e.collection_id = c.uuid "
                "WHERE c.name = 'recipes';"
            )).scalar()
        total = len(load_recipes())
        report(f"库内向量 {n} 条 == 种子数据 {total} 条", n == total)
    except Exception as e:
        report("向量条数校验失败（先跑导入脚本）", False, str(e))


def check_search() -> None:
    try:
        from app_my.knowledge.retriever import hybrid_search
        hits = hybrid_search("鸡胸肉 减脂", k=3)
        names = [h["metadata"].get("name") for h in hits]
        report("hybrid_search('鸡胸肉 减脂') 返回结果", len(hits) > 0, " / ".join(str(x) for x in names))
    except Exception as e:
        report("混合检索失败", False, str(e))


def check_health() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8002/health", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            report("/health 不退化", '"ok"' in body, body)
    except Exception as e:
        report("后端 /health 未通过", False, "请先启动 main.py：" + str(e))


def check_loader() -> None:
    try:
        from app_my.knowledge.data_loader import load_recipes, recipe_to_metadata, recipe_to_text
        recipes = load_recipes()
        text = recipe_to_text(recipes[0])
        meta = recipe_to_metadata(recipes[0])
        ok = text.startswith("菜名：") and meta.get("name") == recipes[0]["name"]
        report(f"data_loader 可用，首条菜谱文本化正常（{text[:30]}...）", ok)
    except Exception as e:
        report("data_loader 模块异常", False, str(e))


CHECKS = {
    "deps": check_deps, "docker": check_docker, "config": check_config,
    "data": check_data, "embed": check_embed, "dbcount": check_dbcount,
    "search": check_search, "loader": check_loader, "health": check_health,
}


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        order = ["deps", "docker", "config", "data", "loader", "embed", "dbcount", "search", "health"]
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
