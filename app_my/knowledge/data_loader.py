# app_my/knowledge/data_loader.py
"""
菜谱数据加载与文本化。
- load_recipes()     : 读 recipes.json -> List[dict]
- recipe_to_text()   : 一条菜谱 -> 送入 embedding 的一段文本
- recipe_to_metadata(): 一条菜谱 -> 存进向量库的元数据（供检索结果直接展示/过滤）
"""
import json
from pathlib import Path
from typing import Dict, List

# 数据文件位置：app_my/knowledge/data/recipes.json
DATA_FILE = Path(__file__).resolve().parent / "data" / "recipes.json"


def load_recipes() -> List[Dict]:
    """读取全部种子菜谱"""
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def recipe_to_text(r: Dict) -> str:
    """
    把一条菜谱"压"成一段自然语言文本。
    这段文本会被转成向量 —— 内容越完整，语义检索越准。
    """
    ingredients = "、".join(r.get("ingredients", []))
    tags = "、".join(r.get("tags", []))
    steps = "；".join(r.get("steps", []))
    return (
        f"菜名：{r.get('name')}。菜系：{r.get('cuisine')}。"
        f"难度：{r.get('difficulty')}，用时{r.get('time_minutes')}分钟。"
        f"主要食材：{ingredients}。特点：{tags}。做法：{steps}"
    )


def recipe_to_metadata(r: Dict) -> Dict:
    """
    元数据：跟着向量一起入库的"结构化信息"。
    检索命中后直接取 metadata 展示，不用再解析原文。
    """
    return {
        "recipe_id": r.get("recipe_id"),
        "name": r.get("name"),
        "cuisine": r.get("cuisine"),
        "difficulty": r.get("difficulty"),
        "time_minutes": r.get("time_minutes"),
        "calories": r.get("calories"),
        "protein": r.get("protein"),
        "fat": r.get("fat"),
        "carbs": r.get("carbs"),
        "tags": ",".join(r.get("tags", [])),   # 列表转逗号字符串，便于入库
    }