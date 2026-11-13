# app_my/tools/nutrition_tool.py
"""
【工具】calculate_nutrition —— 食材营养估算

它是干什么的：
    输入一串食材（如 ["鸡胸肉 200克", "西兰花 1颗", "盐 2克"]），
    输出热量、蛋白质、脂肪、碳水化合物的估算值。

它和"大模型聊天"的区别（为什么要写成工具）：
    大模型算数是弱项，让它心算营养值经常胡说；
    写成普通 Python 函数查表 + 四则运算，结果稳定可复现，
    大模型只负责"决定要不要调用它、怎么把结果讲给用户听"。

数据来源：
    app_my/tools/data/ingredients_nutrition.json（每 100 克可食部近似值）

两个口径（看代码里 total_per_100g 与 total_estimated 的区别）：
    total_per_100g —— 把匹配到的食材各按 100 克相加，用于横向对比"这套食材每 100g 多顶饱"；
    total_estimated —— 尽量从"200克""3个"里解析出用量，再按实际用量估算总量，
                       更接近"这一顿大概吃进去多少"，解析不出用量的按 100 克计（并标记）。
    调味料（category=调味，如盐、生抽、花椒）不计入合计——否则一勺酱油就能把热量算歪。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app_my.core.logging import logger

# 营养库位置：app_my/tools/data/ingredients_nutrition.json
DATA_FILE = Path(__file__).resolve().parent / "data" / "ingredients_nutrition.json"

# 匹配时要剥掉的"形态后缀"：蒜末→蒜、土豆丝→土豆、五花肉丁→五花肉
_TAIL_CHARS = "丝末片丁块粒碎条段颗根瓣叶皮馅"

# 别名表：菜谱/口语里的叫法 → 营养库里的标准名（库中没有同义词时才需要写）
_ALIASES = {
    "生姜": "姜片",
    "鸡蛋黄": "蛋黄",
    "蛋白": "蛋清",
    "番茄": "西红柿",
    "土豆丝": "土豆",
}

# 数量单位 → 克（用于 total_estimated 的用量换算；个/只/根这类按常见大小估）
_UNIT_TO_GRAM = {
    "克": 1.0, "g": 1.0, "G": 1.0, "毫升": 1.0, "ml": 1.0, "ML": 1.0,
    "千克": 1000.0, "kg": 1000.0, "升": 1000.0, "l": 1000.0,
    "斤": 500.0, "两": 50.0,
    "个": 50.0, "只": 60.0, "根": 30.0, "片": 10.0, "颗": 8.0, "段": 20.0,
    "勺": 15.0, "汤匙": 15.0, "茶匙": 5.0, "杯": 240.0,
    "把": 50.0, "块": 30.0, "条": 100.0, "瓣": 5.0,
}

# 一条食材里的"数量+单位"，例如 "200克" "3个"
_AMOUNT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(千克|kg|毫升|ML|ml|克|g|G|升|l|斤|两|个|只|根|片|颗|段|勺|汤匙|茶匙|杯|把|块|条|瓣)"
)

# 调料分类的标记：该分类不计入营养合计
SEASONING_CATEGORY = "调味"


class NutritionInput(BaseModel):
    """
    工具的入参结构（给大模型看的"说明书"）
    —— 字段说明会作为工具描述的一部分提供给模型，模型据此决定怎么填参数。
    """

    ingredients: List[str] = Field(
        ...,
        description='食材清单，元素是"名称 + 可选用量"的字符串，例如 ["鸡胸肉 200克", "西兰花 1颗"]',
    )


# ---------------------------------------------------------------- 数据加载
def _load_table() -> Dict[str, dict]:
    """读取营养库，返回 {食材名: {calories, protein, fat, carbs, category}}"""
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return payload.get("items", {})


# 模块级缓存：整个进程只读一次文件（营养库是静态数据，不需要每次调用都读盘）
_TABLE: Dict[str, dict] | None = None


def _table() -> Dict[str, dict]:
    """带缓存的取表函数（第一次调用读盘，之后走内存）"""
    global _TABLE
    if _TABLE is None:
        _TABLE = _load_table()
        logger.info(f"nutrition_tool: 营养库加载完成，共 {len(_TABLE)} 条")
    return _TABLE


# ---------------------------------------------------------------- 名称匹配
def _split_name(ingredient: str) -> str:
    """
    从"鸡胸肉 200克"里取出名称部分"鸡胸肉"

    规则：先去掉首尾空格，再从第一个空格/中文括号处截断。
    """
    return re.split(r"[\s（(]", ingredient.strip())[0]


def _match(name: str) -> str | None:
    """
    在营养库里找 name 对应的标准名，找不到返回 None。

    匹配顺序（从严格到宽松，命中即返回）：
        ① 完全相同          —— "鸡蛋" 直接命中
        ② 别名表            —— "番茄" → "西红柿"
        ③ 剥掉形态后缀       —— "蒜末" → "蒜"、"五花肉丁" → "五花肉"
        ④ 包含关系（取最长） —— "生抽老抽" 里含 "生抽"，取更长的那个避免歧义
    """
    table = _table()
    if not name:
        return None

    # ① 完全相同
    if name in table:
        return name

    # ② 别名
    if name in _ALIASES and _ALIASES[name] in table:
        return _ALIASES[name]

    # ③ 剥后缀（反复剥，直到没有可剥的字符："土豆丝末" → "土豆"）
    stripped = name.rstrip(_TAIL_CHARS)
    if stripped and stripped in table:
        return stripped
    if stripped in _ALIASES and _ALIASES[stripped] in table:
        return _ALIASES[stripped]

    # ④ 包含关系：在库里找"被 name 包含"的条目，取最长的（最具体）
    candidates = [k for k in table if len(k) >= 2 and k in name]
    if candidates:
        return max(candidates, key=len)
    return None


def _parse_grams(ingredient: str) -> float | None:
    """
    解析一条食材的用量并换算成克，解析不出返回 None。

    例："鸡胸肉 200克" → 200.0 ；"鸡蛋 3个" → 150.0（按一个 50 克估）
    """
    m = _AMOUNT_RE.search(ingredient)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2)
    factor = _UNIT_TO_GRAM.get(unit)
    return None if factor is None else round(value * factor, 1)


def _empty_totals() -> Dict[str, float]:
    """四项指标的零值容器"""
    return {"calories": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}


# ---------------------------------------------------------------- 核心逻辑
def estimate_nutrition(ingredients: List[str]) -> dict:
    """
    营养估算主逻辑（纯函数，方便单测；工具函数 calculate_nutrition 只是它的壳）

    返回结构：
    {
      "total_per_100g": {"calories":..., "protein":..., "fat":..., "carbs":...},
      "total_estimated": {...同结构，按用量估算...},
      "items":     [{"input":..., "matched":匹配到的库名, "grams":用量克数,
                     "counted":是否计入合计, "per_100g": {...}, "estimated": {...}}],
      "unmatched": ["没在营养库里找到的食材名"],
      "seasonings": ["按调味料处理、不计入合计的食材名"],
      "coverage":  0.0~1.0 匹配率,
      "note":      口径说明
    }
    """
    table = _table()
    per_100g = _empty_totals()      # 口径 1：按每 100 克累加
    estimated = _empty_totals()     # 口径 2：按用量估算总量
    items: List[dict] = []
    unmatched: List[str] = []
    seasonings: List[str] = []

    for raw in ingredients or []:
        name = _split_name(str(raw))
        matched = _match(name)
        grams = _parse_grams(str(raw))

        if not matched:
            # 库里没有：如实记录，不猜（宁缺毋滥，避免给出假数据）
            unmatched.append(name)
            items.append({"input": raw, "matched": None, "grams": grams,
                          "counted": False, "per_100g": None, "estimated": None})
            continue

        row = table[matched]
        values = {"calories": float(row["calories"]), "protein": float(row["protein"]),
                  "fat": float(row["fat"]), "carbs": float(row["carbs"])}

        # 调味料：记录但不算钱（不计入合计），否则"一勺生抽 8 克碳水"会污染结果
        if row.get("category") == SEASONING_CATEGORY:
            seasonings.append(matched)
            items.append({"input": raw, "matched": matched, "grams": grams,
                          "counted": False, "per_100g": values, "estimated": None})
            continue

        # 口径 1：每 100 克累加
        for key in per_100g:
            per_100g[key] += values[key]

        # 口径 2：按用量估算（解析不出用量时按 100 克算，并在 note 里说明）
        eff_grams = grams if grams else 100.0
        item_est = {key: round(values[key] * eff_grams / 100.0, 1) for key in values}
        for key in estimated:
            estimated[key] += item_est[key]

        items.append({"input": raw, "matched": matched, "grams": grams,
                      "counted": True, "per_100g": values, "estimated": item_est})

    for key in per_100g:
        per_100g[key] = round(per_100g[key], 1)
        estimated[key] = round(estimated[key], 1)

    total = len([i for i in items if i["input"]])  # 输入条数
    result = {
        "total_per_100g": per_100g,
        "total_estimated": estimated,
        "items": items,
        "unmatched": unmatched,
        "seasonings": seasonings,
        "coverage": round((total - len(unmatched)) / total, 2) if total else 0.0,
        "note": (
            "total_per_100g = 各食材按每100克累加（便于横向对比）；"
            "total_estimated = 按用量估算的本餐总量；调味料不计入合计；"
            "未解析出用量的食材按100克计。数值为近似估算，不构成营养建议。"
        ),
    }
    logger.info(
        f"nutrition_tool: 匹配 {total - len(unmatched)}/{total} 条，"
        f"估算总热量 {estimated['calories']} 千卡，未匹配 {unmatched}"
    )
    return result


# ---------------------------------------------------------------- 工具封装
@tool("calculate_nutrition", args_schema=NutritionInput)
def calculate_nutrition(ingredients: List[str]) -> dict:
    """
    估算一组食材的热量与营养素（蛋白/脂肪/碳水）。

    什么时候用：拿到食材清单、需要告诉用户"这顿饭大概多少热量"时调用。
    不要用它做菜谱推荐（那是 search_local_recipes 的职责）。
    """
    return estimate_nutrition(ingredients)