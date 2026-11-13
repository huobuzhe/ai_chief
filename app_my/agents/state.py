# app_my/agents/state.py
"""
多 Agent 工作流的"共享状态"（ChefState）

一句话理解：LangGraph 的每个节点都是一个函数，函数之间不直接互相调用，
而是统一读写这一份 state —— 像一张在工作流里传来传去的表单，
每个节点负责填写自己那几栏，下一个节点读别人填好的栏位。

字段来源分三类：
  1. messages      —— 由基类 MessagesState 提供（消息列表 + add_messages 累加规则）
  2. 业务字段      —— 本文件新增（ingredients / nutrition / recipes / ...）
  3. 阶段 3 的修复 —— user_profile（M1：把用户画像注入流程）、final_answer（H1：最终回复）
"""
from typing import List

from langgraph.graph import MessagesState


class ChefState(MessagesState):
    """
    继承 MessagesState 的好处：
    - 自动拥有 messages: Annotated[list, add_messages] 字段
      add_messages 是一个"累加"规则：节点返回新消息时，LangGraph 会把它们
      追加到已有列表，而不是把整份列表覆盖掉。
      所以节点里只写 【本次新增的消息】，千万不要把历史消息再抄一遍返回。

    - 其它字段是普通字段，遵循"后写覆盖"：节点返回 {"nutrition": {...}}
      就整体替换掉旧值。并行分支各写各的字段，互不冲突。
    """

    # ===== ① 识别节点的产出 =====
    # [{"name": "西兰花", "freshness": 9, "amount": "约300g", "usable": True}, ...]
    ingredients: List[dict]

    # ===== ② 营养节点的产出 =====
    # {"total_per_100g": {...}, "total_estimated": {...}, "items": [...], "unmatched": [...]}
    nutrition: dict

    # ===== ③ 推荐节点的产出（RAG + 联网检索到的候选菜谱）=====
    recipes: List[dict]

    # ===== ④ 重排节点的产出（按用户画像排序后的菜谱）=====
    ranked_recipes: List[dict]

    # ===== M1 修复：用户画像 =====
    # 由协调入口在启动工作流之前查库得到并注入；
    # 重排节点靠它做"减脂/增肌/忌口"排序，输出节点靠它写个性化建议。
    user_profile: dict

    # ===== 图片地址（而不是从 messages[-1] 里反推）=====
    # 多模态消息的 content 是 list，反推很容易出错，所以显式存一份。
    image_url: List[str]

    # ===== H1 修复：最终回复正文 =====
    # output 节点把各节点结论整合成 Markdown 存到这里，
    # 接口层即使流式拿不到内容，也能从这里兜底返回。
    final_answer: str