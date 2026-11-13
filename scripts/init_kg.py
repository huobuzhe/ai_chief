# scripts/init_kg.py
"""
阶段 3（v3.0）：知识图谱构建脚本——把 recipes.json + kg_facts.json 变成 Neo4j 图

构建内容（四类节点 + 四类关系）：
    节点：Ingredient / Recipe / Nutrient / Condition
    关系：IN_RECIPE（食材→菜谱，带用量）
          RICH_IN（食材→营养素，带等级）
          CONTRAINDICATED_FOR（食材→状况，带等级+理由）
          BENEFICIAL_FOR（食材→状况，带理由）

幂等设计：
    全部用 MERGE（存在则复用、不存在则新建），重复执行不产生重复数据；
    --rebuild 参数先清空全图再建（改了 kg_facts.json 后用）。

用法（项目根目录，先起好 Neo4j 容器）：
    python scripts/init_kg.py             # 增量构建
    python scripts/init_kg.py --rebuild   # 清空重建
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))   # scripts/ 下运行需要把项目根加进搜索路径

from neo4j import GraphDatabase

from app_my.core.config import settings

# 数据文件定位（相对项目根，脚本从任何目录跑都能找到）
ROOT = Path(__file__).resolve().parent.parent
RECIPES_FILE = ROOT / "app_my" / "knowledge" / "data" / "recipes.json"
FACTS_FILE = ROOT / "app_my" / "knowledge" / "data" / "kg_facts.json"


def normalize_ingredient(raw: str) -> str:
    """
    "鸡蛋 3个" -> "鸡蛋"：去掉用量部分，只留食材名。

    图谱节点按"干净的名字"建，检索和重排时也用同样的规则切——
    两边规则一致，名字才对得上（图谱最经典的坑就是两边命名不齐）。
    """
    return re.split(r"\s+", raw.strip())[0]


def build(rebuild: bool = False) -> None:
    recipes = json.loads(RECIPES_FILE.read_text(encoding="utf-8"))
    facts = json.loads(FACTS_FILE.read_text(encoding="utf-8"))

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        connection_timeout=5,
    )
    driver.verify_connectivity()          # 连不上直接抛错退出（建图脚本不需要降级）
    print(f"已连接 Neo4j：{settings.NEO4J_URI}")

    with driver.session() as session:
        # ---------- 0) 可选清空 ----------
        if rebuild:
            session.run("MATCH (n) DETACH DELETE n")
            print("已清空全图（--rebuild）")

        # ---------- 1) 菜谱 + 食材 + IN_RECIPE ----------
        # 把 60 条菜谱整成 [{recipe_id, name, ..., items: [{name, amount}]}] 的批量结构
        recipe_rows = []
        for r in recipes:
            items = [
                {"name": normalize_ingredient(ing), "amount": ing}
                for ing in r.get("ingredients") or []
            ]
            recipe_rows.append({
                "recipe_id": r["recipe_id"],
                "name": r["name"],
                "calories": r.get("calories"),
                "time_minutes": r.get("time_minutes"),
                "difficulty": r.get("difficulty"),
                "items": items,
            })
        # UNWIND 批量写（一条 Cypher 写完 60 菜谱 + 全部食材和入菜关系，比逐条快百倍）
        session.run(
            """
            UNWIND $rows AS row
            MERGE (rc:Recipe {recipe_id: row.recipe_id})
              SET rc.name = row.name, rc.calories = row.calories,
                  rc.time_minutes = row.time_minutes, rc.difficulty = row.difficulty
            WITH row, rc
            UNWIND row.items AS item
            MERGE (i:Ingredient {name: item.name})
            MERGE (i)-[rel:IN_RECIPE]->(rc)
              SET rel.amount = item.amount
            """,
            rows=recipe_rows,
        )
        print(f"[1/3] 菜谱 {len(recipe_rows)} 个 + IN_RECIPE 关系已写入")

        # ---------- 2) 营养素 + RICH_IN ----------
        nutrient_rows = []
        for nutrient, info in facts["nutrients"].items():
            for name in info.get("high", []):
                nutrient_rows.append(
                    {"nutrient": nutrient, "ingredient": name, "note": info.get("note", "")}
                )
        session.run(
            """
            UNWIND $rows AS row
            MERGE (n:Nutrient {name: row.nutrient})
              SET n.note = row.note
            MERGE (i:Ingredient {name: row.ingredient})
            MERGE (i)-[:RICH_IN {level: '高'}]->(n)
            """,
            rows=nutrient_rows,
        )
        print(f"[2/3] 营养素节点 + RICH_IN 关系 {len(nutrient_rows)} 条已写入")

        # ---------- 3) 健康状况 + CONTRAINDICATED_FOR / BENEFICIAL_FOR ----------
        condition_rows = []
        prefer_rows = []
        for condition, info in facts["conditions"].items():
            for item in info.get("avoid", []):
                condition_rows.append({
                    "condition": condition,
                    "ingredient": item["name"],
                    "level": item["level"],
                    "reason": item["reason"],
                })
            for item in info.get("prefer", []):
                prefer_rows.append({
                    "condition": condition,
                    "ingredient": item["name"],
                    "reason": item["reason"],
                })

        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Condition {name: row.condition})
            MERGE (i:Ingredient {name: row.ingredient})
            MERGE (i)-[r:CONTRAINDICATED_FOR]->(c)
              SET r.level = row.level, r.reason = row.reason
            """,
            rows=condition_rows,
        )
        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Condition {name: row.condition})
            MERGE (i:Ingredient {name: row.ingredient})
            MERGE (i)-[b:BENEFICIAL_FOR]->(c)
              SET b.reason = row.reason
            """,
            rows=prefer_rows,
        )
        # 状况的别名（"高血糖"也要能查到"糖尿病"）
        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:Condition {name: row.name})
              SET c.aka = row.aka
            """,
            rows=[
                {"name": name, "aka": info.get("aka", [])}
                for name, info in facts["conditions"].items()
            ],
        )
        print(f"[3/3] 状况节点 6 个 + 禁忌 {len(condition_rows)} 条 / 推荐 {len(prefer_rows)} 条已写入")

        # ---------- 4) 构建结果统计 ----------
        stats = session.run(
            """
            MATCH (n) WITH labels(n)[0] AS label, count(*) AS cnt
            RETURN label, cnt ORDER BY cnt DESC
            """
        )
        print("\n===== 图谱规模 =====")
        total_nodes = 0
        for record in stats:
            print(f"  {record['label']:<12} {record['cnt']} 个")
            total_nodes += record["cnt"]
        rel_stats = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC"
        )
        total_rels = 0
        for record in rel_stats:
            print(f"  关系 {record['t']:<20} {record['c']} 条")
            total_rels += record["c"]
        print(f"合计：{total_nodes} 节点 / {total_rels} 关系")

    driver.close()
    print("\n构建完成。可用 python -c \"from app_my.core.kg import ask; print(ask('土豆','糖尿病'))\" 验证推理")


if __name__ == "__main__":
    build(rebuild="--rebuild" in sys.argv)