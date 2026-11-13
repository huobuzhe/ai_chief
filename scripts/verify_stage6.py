# scripts/verify_stage6.py
"""
v3 阶段 6 分步验证脚本（Milvus + 三路混合检索）。
（本文件覆盖了 v2.0 时代的同名脚本——内容是 trace 验证，git 历史里可找回。）

用法（项目根目录执行）：
    uv run python scripts/verify_stage6.py <子命令>

子命令：
    deps     容器状态（milvus/etcd/minio + 老三样）
    conn     pymilvus 连接 + 集合存在 + 行数
    search   一句真实查询跑 Milvus 向量检索
    kg       图谱路：食材命中 -> 菜谱
    hybrid   hybrid_search_v2 三路融合出结果
    flag     hybrid_v2 flag 状态
    all      以上全部（提测用）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS: list = []


def report(name, ok, detail=""):
    print(("[OK]  " if ok else "[FAIL]") + f" {name}" + (f"  ->  {detail}" if detail else ""))
    RESULTS.append(ok)
    return ok


def check_deps():
    import subprocess
    out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                         capture_output=True, text=True).stdout.splitlines()
    for c in ("ai_chief_pgvector", "ai_chief_redis", "ai_chief_pgbouncer",
              "ai_chief_neo4j", "ai_chief_etcd", "ai_chief_minio", "ai_chief_milvus"):
        report(f"容器 {c} 运行中", c in out, "" if c in out else "docker compose -f docker/docker-compose.v3.yml up -d")


def check_conn():
    try:
        from app_my.knowledge.milvus_store import (
            collection_row_count, ensure_collection, milvus_available,
        )
        if not report("Milvus 可连接", milvus_available()):
            return
        ensure_collection()
        n = collection_row_count()
        report("集合 recipes_v2 有数据", n > 0, f"行数 {n}（0 = 先跑 import_recipes_milvus.py）")
    except Exception as e:
        report("Milvus 连接检查失败", False, f"{type(e).__name__}: {e}")


def check_search():
    try:
        from app_my.knowledge.embedding import embed_query
        from app_my.knowledge.milvus_store import vector_search
        hits = vector_search(embed_query("鸡胸肉 减脂"), k=3)
        report("Milvus 向量检索返回结果", len(hits) > 0,
               "; ".join(h["metadata"].get("name", "?") for h in hits[:3]))
    except Exception as e:
        report("Milvus 检索失败", False, f"{type(e).__name__}: {e}")


def check_kg():
    try:
        from app_my.core.kg import match_recipes_from_query
        ids = match_recipes_from_query("鸡胸肉 西兰花")
        report("图谱路命中菜谱", len(ids) > 0, str(ids[:5]))
        empty = match_recipes_from_query("完全无关的查询词组")
        report("无关查询返回空（缺席即降级）", empty == [])
    except Exception as e:
        report("图谱路检查失败", False, f"{type(e).__name__}: {e}")


def check_hybrid():
    try:
        from app_my.knowledge.retriever import hybrid_search_v2
        hits = hybrid_search_v2("鸡胸肉 西兰花 减脂", k=3)
        ok = len(hits) > 0 and all("recipe_id" in h for h in hits)
        report("三路混合检索出结果", ok,
               "; ".join(f"{h['recipe_id']}({h['metadata'].get('name')})" for h in hits))
    except Exception as e:
        report("混合检索失败", False, f"{type(e).__name__}: {e}")


def check_flag():
    try:
        from app_my.core.feature_flag import is_feature_enabled
        from app_my.core.tenant import current_tenant_id
        from app_my.db.session import SessionLocal

        db = SessionLocal()                      # 第 1 个参数：数据库会话
        try:
            tid = current_tenant_id.get()        # 第 3 个参数：当前租户 id（默认 1）
            v = is_feature_enabled(db, "hybrid_v2", tid)   # 第 2 个参数：flag 名
        finally:
            db.close()                           # 必须关，否则连接池会被耗光
        report("hybrid_v2 flag 可读取", True,
               f"tenant={tid} 当前={'开（v2三路）' if v else '关（v1两路）'}")
    except Exception as e:
        report("feature_flag 模块不可用", False, f"{type(e).__name__}: {e}（阶段 4 做完了吗？）")

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    checks = {"deps": check_deps, "conn": check_conn, "search": check_search,
              "kg": check_kg, "hybrid": check_hybrid, "flag": check_flag}
    if cmd == "all":
        for fn in checks.values():
            fn()
    else:
        checks[cmd]()
    print()
    print(f"结果：{sum(RESULTS)} 通过 / {len(RESULTS) - sum(RESULTS)} 失败")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())