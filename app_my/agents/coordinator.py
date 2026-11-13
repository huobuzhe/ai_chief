# app_my/agents/coordinator.py
"""
协调入口（coordinator）—— 把 5 个节点编成一张有向图，并提供流式对话入口

图的形状（并行 fan-out + fan-in）：
              ┌──────────────► ②营养 ──────────────┐
    START ──► ①识别                               ├──► ④重排 ──► ⑤输出 ──► END
              └──────────────► ③推荐 ──────────────┘
    说明：识别完成后，"营养"和"推荐"互不依赖，并行跑（省一半等待时间）；
         两者都写自己的 state 字段，不会互相覆盖；汇聚到重排时才需要同时拿到两份结果。

三个对外入口：
    build_workflow()        —— 组装图（可测试）
    get_coordinator_agent() —— 惰性单例（进程内只编译一次图，别在模块顶层编译）
    chat_coordinator(...)   —— 接口层调用的流式生成器（真正的"对话"入口）
"""
from __future__ import annotations

from typing import AsyncIterator, List, Optional
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app_my.agents.nutritionist import nutrition_node
from app_my.agents.output import output_node
from app_my.agents.ranker import rank_node
from app_my.agents.recognizer import recognize_node
from app_my.agents.recommender import recommend_node
from app_my.agents.state import ChefState
from app_my.core.logging import logger
from app_my.db.user_profile import get_user_profile

# 只有这个节点产出的内容会直接流给用户（前面的节点输出属于"过程"，进日志/追踪）
FINAL_NODE = "output"


def build_workflow(nodes=None):
    """
    组装并编译工作流。

    add_edge 的两种写法：
        add_edge("recognize", "nutrition")         一次只接一个下游 → 顺序执行
        add_edge(["nutrition", "recommend"], "rank") 多个起点汇聚到同一节点 → 等待全部完成再走

    v3阶段9 新增参数 nodes：
        传 None（默认）→ 用本地节点，行为和阶段 8 之前完全一致（单体模式）。
        传一张"节点名 → 函数"的表 → 用这张表注册节点（微服务模式下换成 HTTP 版节点）。
        这样"图的形状"和"节点怎么实现"就解耦了：拆不拆微服务，连边代码一行都不用改。
    """
    if nodes is None:
        nodes = {
            "recognize": recognize_node,
            "nutrition": nutrition_node,
            "recommend": recommend_node,
            "rank": rank_node,
            "output": output_node,
        }

    workflow = StateGraph(ChefState)

    # ① 注册节点（名字 → 函数）
    for name, fn in nodes.items():
        workflow.add_node(name, fn)

    # ② 连边（数据流向）
    workflow.add_edge(START, "recognize")
    workflow.add_edge("recognize", "nutrition")        # 识别 → 营养（并行分支 1）
    workflow.add_edge("recognize", "recommend")        # 识别 → 推荐（并行分支 2）
    workflow.add_edge(["nutrition", "recommend"], "rank")   # fan-in：两支都完成才重排
    workflow.add_edge("rank", "output")
    workflow.add_edge("output", END)

    return workflow.compile()


# 惰性单例：编译图有开销，但也不能在 import 时就编译（否则单测/无密钥环境会受影响）
_agent = None


def _resolve_nodes():
    """
    按环境变量 SPLIT_MODE 决定节点用本地版还是远程版（v3阶段9 新增）。

        SPLIT_MODE=local（默认）  → 全部节点在本进程内跑（单体行为，拆分前/对照组用）
        SPLIT_MODE=remote        → 识别/营养/推荐/重排改走 HTTP 调各自的服务

    为什么要做成环境变量而不是硬改代码：
    阶段 9 的验收项之一是"用阶段 7 的指标给出拆分前后对比"——
    同一个代码库，改一个环境变量就能在"单体"和"微服务"两种形态间切换，
    压测才有可比性（否则你得维护两套代码）。
    """
    import os
    if os.getenv("SPLIT_MODE", "local").strip().lower() == "remote":
        from services.chat.graph_remote import remote_nodes
        logger.info("coordinator: SPLIT_MODE=remote，识别/营养/推荐/重排改走 HTTP 调用")
        return remote_nodes()
    return None


def get_coordinator_agent():
    """取（必要时创建）编译后的工作流单例"""
    global _agent
    if _agent is None:
        logger.info("coordinator: 首次编译 StateGraph")
        _agent = build_workflow(nodes=_resolve_nodes())
    return _agent


def reset_coordinator_agent() -> None:
    """测试用：丢掉单例，下次重新编译"""
    global _agent
    _agent = None

# def build_workflow():
#     """
#     组装并编译工作流。

#     add_edge 的两种写法：
#         add_edge("recognize", "nutrition")         一次只接一个下游 → 顺序执行
#         add_edge(["nutrition", "recommend"], "rank") 多个起点汇聚到同一节点 → 等待全部完成再走
#     """
#     workflow = StateGraph(ChefState)

#     # ① 注册节点（名字 → 函数）
#     workflow.add_node("recognize", recognize_node)
#     workflow.add_node("nutrition", nutrition_node)
#     workflow.add_node("recommend", recommend_node)
#     workflow.add_node("rank", rank_node)
#     workflow.add_node("output", output_node)          # H1 修复：没有它用户会收到空回复

#     # ② 连边（数据流向）
#     workflow.add_edge(START, "recognize")
#     workflow.add_edge("recognize", "nutrition")        # 识别 → 营养（并行分支 1）
#     workflow.add_edge("recognize", "recommend")        # 识别 → 推荐（并行分支 2）
#     workflow.add_edge(["nutrition", "recommend"], "rank")   # fan-in：两支都完成才重排
#     workflow.add_edge("rank", "output")
#     workflow.add_edge("output", END)

#     return workflow.compile()


# # 惰性单例：编译图有开销，但也不能在 import 时就编译（否则单测/无密钥环境会受影响）
# _agent = None


# def get_coordinator_agent():
#     """取（必要时创建）编译后的工作流单例"""
#     global _agent
#     if _agent is None:
#         logger.info("coordinator: 首次编译 StateGraph")
#         _agent = build_workflow()
#     return _agent



def reset_coordinator_agent() -> None:
    """测试用：丢掉单例，下次重新编译"""
    global _agent
    _agent = None


async def chat_coordinator(
    text: str,
    image_url: Optional[List[str]] = None,
    thread_id: str = "",
    user_id: Optional[str] = None,
    include_progress: bool = False,

    tenant_id: Optional[int] = None,      #  v3阶段6 新增：接收 /chat/stream 透传的租户
) -> AsyncIterator[str]:
    """
    多 Agent 流式对话入口（供 /chat/stream 使用）

    参数：
        text            用户输入的文字
        image_url       图片 URL 列表（可为空 → 走文字抽取食材分支）
        thread_id       会话标识（本阶段不落库，仅用于日志/追踪；为空则自动生成）
        user_id         用户 ID → 用来查画像并注入状态（M1 修复）
        include_progress 是否把中间节点（识别/营养/推荐/重排）的过程也流给用户，
                         默认 False：只流最终报告，过程进日志。调试时可打开看每步结论。

    产出：一段段文本（接口层直接转发给前端，前端拼接即可）
    """
    # ---------- 1) 组装本次输入 ----------
    profile = get_user_profile(user_id)          # M1：按用户查画像
    if not thread_id:
        # 后端生成 thread_id，避免前端随便传导致同一个人被当成多个会话
        thread_id = f"{user_id or 'anonymous'}:{uuid4().hex[:8]}"

    state_in = {
        "messages": [HumanMessage(content=text)],
        "image_url": image_url or [],
        "user_profile": profile,
        "ingredients": [],
        "nutrition": {},
        "recipes": [],
        "ranked_recipes": [],
        "final_answer": "",
    }
        #  v3阶段6：把租户 id 写进上下文变量，供检索工具读取（工具拿不到 request）
    from app_my.core.tenant import current_tenant_id as _tenant_ctx
    _tenant_ctx.set(tenant_id if tenant_id is not None else 1)

    config = {"configurable": {"thread_id": thread_id}}
    agent = get_coordinator_agent()

    logger.info(f"coordinator: user={profile.get('user_id')} thread={thread_id} | 输入：{text[:50]}")

    # ---------- 2) 流式执行 ----------
    yielded = False          # 是否已经给用户吐过内容
    final_state: dict = {}   # 记录最后一次完整状态（兜底用）

    # stream_mode 传列表 → 每个事件是 (模式名, 载荷) 二元组
    #   "messages"：模型/节点新产生的消息（可逐字流式）
    #   "values"  ：每一步之后的完整状态快照（拿 final_answer 兜底）
    async for mode, payload in agent.astream(state_in, config, stream_mode=["messages", "values"]):
        if mode == "values":
            final_state = payload
            continue

        chunk, meta = payload
        content = getattr(chunk, "content", chunk)
        # 多模态模型流式时 content 可能是 list（[{type:text,...}]），统一抽成字符串
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(block.get("text", "") if block.get("type") == "text" else str(block.get("text", "")))
                elif isinstance(block, str):
                    parts.append(block)
            content = "".join([p for p in parts if p])

        if not isinstance(content, str) or not content:
            continue

        node = meta.get("langgraph_node")
        if include_progress or node == FINAL_NODE:
            yielded = True
            yield content
        else:
            logger.debug(f"coordinator: [{node}] {content[:60]}")

    # ---------- 3) 兜底：一个字都没吐出来，就把最终状态里的报告补发 ----------
    if not yielded:
        fallback = (final_state or {}).get("final_answer") or ""
        if not fallback:
            fallback = "抱歉，本次没有生成有效回复。可以试试把食材说得更具体一些（例如「鸡胸肉 200克、西兰花一颗」）。"
        logger.warning("coordinator: 流式未产出内容，使用 final_answer 兜底返回")
        yield fallback