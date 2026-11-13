# app_my/db/user_profile.py
"""
用户画像读取（M1 修复点）

问题背景：
    修订版之前，整条工作流里没有任何地方读"用户是谁、有什么忌口、目标是什么"，
    推荐出来的菜对所有人完全一样，"个性化"是假的。

本阶段做法：
    用一个小 JSON 文件当"画像库"（阶段 4 接入 JWT 鉴权后，换成真正的数据库表，
    函数签名不变，调用方不用改）——先跑通链路，再换存储。

对外只暴露一个函数：get_user_profile(user_id)
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app_my.core.logging import logger

# 画像文件：app_my/db/data/user_profiles.json
PROFILE_FILE = Path(__file__).resolve().parent / "data" / "user_profiles.json"

# 查不到用户时用的兜底画像：目标"普通"、无忌口
DEFAULT_PROFILE = {
    "user_id": "guest",
    "nickname": "访客",
    "goal": "普通",          # 减脂 / 增肌 / 控糖 / 普通
    "forbidden": [],         # 忌口食材（含就大幅降分）
    "allergies": [],         # 过敏食材（含就直接剔除）
    "dislikes": [],          # 不爱吃（轻微降分）
    "prefer_tags": [],       # 偏好标签，如 ["家常", "快手"]
    "daily_calorie_target": 1800,
}


@lru_cache(maxsize=1)
def _load_profiles() -> dict:
    """读画像文件（只读一次，缓存在进程里）。文件缺失或损坏时返回空字典，不影响主流程。"""
    if not PROFILE_FILE.exists():
        logger.warning(f"user_profile: 画像文件不存在 {PROFILE_FILE}，全部走默认画像")
        return {}
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        logger.info(f"user_profile: 已加载 {len(data)} 个用户画像")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"user_profile: 画像文件解析失败 {e}，全部走默认画像")
        return {}


def get_user_profile(user_id: str | None) -> dict:
    """
    按 user_id 取画像；取不到就返回默认画像。

    返回的字典一定是"字段齐全"的：即以 DEFAULT_PROFILE 为底，
    再用该用户配置里的字段覆盖——这样下游节点永远不用写 if key in profile。
    """
    profiles = _load_profiles()
    profile = dict(DEFAULT_PROFILE)
    if user_id and user_id in profiles:
        profile.update(profiles[user_id])
        profile["user_id"] = user_id
    elif user_id:
        profile["user_id"] = user_id     # 新用户：先给默认画像，阶段 4 再做注册
    return profile