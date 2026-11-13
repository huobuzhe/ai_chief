# tests/unit/test_kg_reasoning.py
"""
阶段 3 单元测试：图谱推理的纯逻辑部分（不需要 Neo4j、不需要后端）

覆盖三块：
    1. 状况推导      derive_conditions：画像 goal/health_conditions -> 图谱状况名
    2. 知识数据自检  kg_facts.json 的食材名与 recipes.json 对齐（名字连不上图就白建了）
    3. 重排打分      图谱忌口/推荐映射注入后的加减分与理由（monkeypatch 掉真实查询）
"""
import json
from pathlib import Path

import pytest

from app_my.agents import ranker
from app_my.core import kg as kg_module

DATA_DIR = Path(__file__).resolve().parents[2] / "app_my" / "knowledge" / "data"


# ============================================================
# 1) 状况推导
# ============================================================

class TestDeriveConditions:
    def test_sugar_goal_maps_to_diabetes(self):
        # 画像目标"控糖" -> 图谱状况"糖尿病"（重排时按糖尿病饮食原则压制高GI食材）
        assert kg_module.derive_conditions({"goal": "控糖"}) == ["糖尿病"]

    def test_normal_goal_no_condition(self):
        # 普通/减脂/增肌目标没有对应禁忌状况 -> 空列表（不查图谱）
        assert kg_module.derive_conditions({"goal": "减脂"}) == []
        assert kg_module.derive_conditions({}) == []

    def test_health_conditions_passthrough(self):
        profile = {"goal": "普通", "health_conditions": ["痛风", "高血压"]}
        assert kg_module.derive_conditions(profile) == ["痛风", "高血压"]

    def test_dedup_when_goal_and_condition_overlap(self):
        # goal=控糖 + health_conditions 里又写了糖尿病 -> 只留一个
        profile = {"goal": "控糖", "health_conditions": ["糖尿病"]}
        assert kg_module.derive_conditions(profile) == ["糖尿病"]


# ============================================================
# 2) 知识数据自检（图谱数据质量）
# ============================================================

class TestKgFactsAlignment:
    def _load(self):
        recipes = json.loads((DATA_DIR / "recipes.json").read_text(encoding="utf-8"))
        facts = json.loads((DATA_DIR / "kg_facts.json").read_text(encoding="utf-8"))
        return recipes, facts

    def test_facts_file_structure(self):
        _, facts = self._load()
        assert "conditions" in facts and "nutrients" in facts
        for name, info in facts["conditions"].items():
            assert "aka" in info, f"{name} 缺 aka 字段"
            for item in info.get("avoid", []):
                assert set(item) >= {"name", "level", "reason"}, f"{name}.avoid 条目字段不全"
            for item in info.get("prefer", []):
                assert set(item) >= {"name", "reason"}, f"{name}.prefer 条目字段不全"

    def test_avoid_levels_are_valid(self):
        # level 必须是 kg.py 里定义过扣分权重的三档之一，写错等级等于静默不扣分
        _, facts = self._load()
        valid = set(kg_module.LEVEL_WEIGHT)
        for name, info in facts["conditions"].items():
            for item in info.get("avoid", []):
                assert item["level"] in valid, f"{name}->{item['name']} 的 level={item['level']} 不在 {valid}"

    def test_fact_ingredients_align_with_recipes(self):
        # 图谱知识里的食材名必须能在 recipes.json 里找到（除少量明确"预留"的）
        # 名字对不上的边永远查不到——这是图谱项目最经典的坑
        recipes, facts = self._load()
        recipe_names = set()
        for r in recipes:
            for ing in r.get("ingredients", []):
                recipe_names.add(ing.split()[0])

        known_missing = {"香蕉", "浓茶"}     # kg_facts 里标注"本库未用到，预留"的
        referenced = set()
        for info in facts["conditions"].values():
            for item in info.get("avoid", []) + info.get("prefer", []):
                referenced.add(item["name"])
        for info in facts["nutrients"].values():
            referenced.update(info.get("high", []))

        orphan = referenced - recipe_names - known_missing
        assert not orphan, f"以下食材在图谱知识里写了，但 recipes.json 里不存在：{sorted(orphan)}"


# ============================================================
# 3) 重排打分（图谱映射注入后的行为）
# ============================================================

def _recipe(name="测试菜", ingredients=None, **kw):
    return {
        "name": name,
        "ingredients": ingredients or ["鸡蛋 2个", "小葱 1根"],
        "tags": kw.get("tags", []),
        "time_minutes": kw.get("time_minutes", 15),
        "difficulty_level": kw.get("difficulty_level", 2),
        "calories": kw.get("calories", 200),
        **{k: v for k, v in kw.items() if k not in ("tags", "time_minutes", "difficulty_level", "calories")},
    }


AVOID_POTATO = {"土豆": {"condition": "糖尿病", "level": "限量", "reason": "GI值较高，升血糖快", "weight": 4}}
PREFER_BROCCOLI = {"西兰花": {"condition": "糖尿病", "reason": "低GI且富含膳食纤维"}}


class TestRankerWithKg:
    def test_avoid_hit_penalizes_with_graph_reason(self):
        # 同一道菜：无图谱扣分 vs 图谱说土豆"限量"（-4），且理由带"图谱提示"
        base = _recipe("土豆炖牛腩", ["土豆 2个", "牛腩 300克"])
        score_plain, reasons_plain = ranker._score_recipe(base, {"goal": "普通"})
        score_kg, reasons_kg = ranker._score_recipe(base, {"goal": "普通"}, kg_avoid=AVOID_POTATO)

        assert score_kg == pytest.approx(score_plain - 4)
        assert any("图谱提示" in r and "土豆" in r for r in reasons_kg)

    def test_avoid_hard_level_penalizes_more(self):
        # level=避免 扣 8 分（比"限量"的 4 分更重——安全等级不同力度不同）
        avoid_hard = {"火腿": {"condition": "高血压", "level": "避免", "reason": "钠含量极高", "weight": 8}}
        r = _recipe("火腿炒饭", ["火腿 50克", "米饭 1碗"])
        s_plain, _ = ranker._score_recipe(r, {"goal": "普通"})
        s_hard, _ = ranker._score_recipe(r, {"goal": "普通"}, kg_avoid=avoid_hard)
        assert s_plain - s_hard == 8

    def test_worst_hit_wins_no_double_penalty(self):
        # 土豆+大米都命中（各 -4）：一道菜只按最重的扣一次（-4），不是 -8
        avoid_two = {
            "土豆": {"condition": "糖尿病", "level": "限量", "reason": "GI高", "weight": 4},
            "大米": {"condition": "糖尿病", "level": "限量", "reason": "精制碳水", "weight": 4},
        }
        r = _recipe("土豆焖饭", ["土豆 1个", "大米 100克"])
        s_plain, _ = ranker._score_recipe(r, {"goal": "普通"})
        s_kg, _ = ranker._score_recipe(r, {"goal": "普通"}, kg_avoid=avoid_two)
        assert s_plain - s_kg == 4

    def test_prefer_hit_adds_score(self):
        r = _recipe("清炒西兰花", ["西兰花 300克", "蒜 2瓣"])
        s_plain, _ = ranker._score_recipe(r, {"goal": "普通"})
        s_kg, reasons_kg = ranker._score_recipe(r, {"goal": "普通"}, kg_prefer=PREFER_BROCCOLI)
        assert s_kg == pytest.approx(s_plain + 2)
        assert any("图谱推荐" in r2 for r2 in reasons_kg)

    def test_rank_recipes_without_conditions_skips_kg(self, monkeypatch):
        # 没有健康状况时一次图谱都不该查（monkeypatch 成炸弹，被调用就炸）
        def _boom(*a, **kw):
            raise AssertionError("无健康状况时不应查询图谱")

        monkeypatch.setattr(kg_module, "get_condition_guidance", _boom)
        result = ranker.rank_recipes([_recipe()], {"goal": "普通"})
        assert len(result) == 1

    def test_rank_recipes_reorders_by_kg(self, monkeypatch):
        # 端到端排序行为：含土豆的菜 vs 不含的菜，控糖画像下土豆菜被压下去
        monkeypatch.setattr(kg_module, "get_condition_guidance", lambda c: (dict(AVOID_POTATO), {}))
        recipes = [
            _recipe("土豆炖牛腩", ["土豆 2个", "牛腩 300克"]),
            _recipe("清炒油麦菜", ["油麦菜 300克", "蒜 2瓣"]),
        ]
        ranked = ranker.rank_recipes(recipes, {"goal": "控糖"})
        assert ranked[0]["name"] == "清炒油麦菜"      # 无禁忌的排前面
        assert any("图谱提示" in r for r in ranked[1]["rank_reasons"])