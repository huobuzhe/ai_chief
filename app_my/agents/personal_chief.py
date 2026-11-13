from langchain.chat_models import init_chat_model
from langchain_tavily import TavilySearch
from langchain.agents import create_agent
import os

from app_my.common.logger import logger
from langchain_core.messages import HumanMessage, AIMessageChunk

from dotenv import load_dotenv
load_dotenv()

# 搜索工具
web_search = TavilySearch(
    max_results=5,
    topic="general"
)

# 多模态大模型
model = init_chat_model(
    model=os.getenv("DASHSCOPE_MODEL", "qwen3.8-omni-flash"),
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY")
)

system_prompt = """
你是一名私人厨师。收到用户提供的食材照片或清单后，请按以下流程操作：
1.识别和评估食材：若用户提供照片，首先辨识所有可见食材。基于食材的外观状态，评估其新鲜度与可用量，整理出一份"当前可用食材清单"。
2.智能食谱检索：优先调用 web_search 工具，以"可用食材清单"为核心关键词，查找可行菜谱。
3.多维度评估与排序：从营养价值和制作难度两个维度对检索到的候选食谱进行量化打分，并根据得分排序，制作简单且营养丰富的排名靠前。
4.结构化方案输出：把排序后的食谱整理为一份结构清晰的建议报告，要包含食谱信息、得分、推荐理由、食谱的参考图片，帮助用户快速做出决策。

请严格按照流程，优先调用 web_search 工具搜索食谱，搜索不到的情况下才能自己发挥。
"""

# 不传入checkpointer，关闭会话记忆（方案A）
agent = create_agent(
    model=model,
    tools=[web_search],
    system_prompt=system_prompt
)


# 流式对话
async def search_recipes(prompt: str, image: str, thread_id: str):
    """调用agent搜索食谱"""
    print("===== 进入 search_recipes =====")
    print(f"prompt: {prompt}")
    print(f"image: {image}")
    print(f"thread_id: {thread_id}")

    logger.info(f"[用户]: {prompt}, image: {image}, thread_id: {thread_id}")
    try:
        if not image or image.strip() == "":
            message = HumanMessage(content=prompt)
            print("没有图片，纯文本模式")
        else:
            message = HumanMessage(content=[
                {"type": "image_url", "image_url": {"url": image}},
                {"type": "text", "text": prompt}
            ])
            print("有图片，多模态模式")

        print("开始调用 agent.astream...")
        async for chunk, metadata in agent.astream(
                {"messages": [message]},
                {"configurable": {"thread_id": thread_id}},
                stream_mode="messages"
        ):
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                # ===== 修正D：多模态模型 stream 时 chunk.content 可能是 list（content blocks）=====
                # 原代码直接 yield chunk.content —— 如果是 list，前端会拿到 [{...},{...}] 这样的 JSON
                # 统一抽成纯字符串再 yield
                content = chunk.content
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            elif "text" in block:
                                text_parts.append(block["text"])
                        elif isinstance(block, str):
                            text_parts.append(block)
                    content = "".join(text_parts)
                if content:                                  # ===== 修正D 结束 =====
                    print(f"收到chunk: {content[:50]}...")
                    yield content

        print("agent.astream 正常结束")

    except Exception as e:
        print(f"===== 报错了！=====")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        logger.error(f"\n[错误]: {str(e)}")
        yield "信息检索失败，试试看手动输入食物列表？"

