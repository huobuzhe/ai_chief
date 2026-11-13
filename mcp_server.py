# AI私厨 MCP Server（新增独立文件，纯增量，不改动任何现有代码）
#
# 目的：把 AI私厨 已有的两个真实能力，以标准 MCP（Model Context Protocol）原语暴露出去，
#       让任意 MCP 客户端（Claude Desktop / IDE / 别的 Agent）能"发现并调用"它们，
#       而不必改写 /chat/stream、/kg/ask 等原有接口。
#
# 暴露的能力（Tools）：
#   - ask_knowledge_graph(ingredient, condition) -> app_my.core.kg.ask
#   - chat_chief(message, thread_id)             -> app_my.agents.coordinator.chat_coordinator
#
# 非侵入性：本文件不被任何现有代码 import；只在显式 python mcp_server.py 时运行。
#           原有 /chat/stream、/kg/ask、FastAPI 应用、评测/压测脚本一律不受影响。
#
# 运行（需 Python 3.10+ 且已装 mcp<2；FastMCP 在 mcp 2.x 已更名为 MCPServer，本文件用 1.x API）：
#   cd F:/pycharm_aiprogram/ai_chief
#   python mcp_server.py                                         # stdio（本地 Host：Claude Desktop 等）
#   python mcp_server.py --transport streamable-http --port 8003  # 远程 Host
#   环境变量照常从 .env 读取（Neo4j / DASHSCOPE / MOCK_LLM 等），与启动主应用一致。
#
# 降级行为沿用现有实现：图谱不可用（Neo4j 未连）时 ask 返回"图谱不可用"而非报错；
#   无 LLM key 时 chat_chief 捕获异常返回可读错误（建议 MOCK_LLM=true 调试）。

import argparse
import json
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-chef-mcp")


@mcp.tool()
def ask_knowledge_graph(ingredient: str, condition: str = "") -> str:
    """基于知识图谱做「{condition}患者能不能吃 {ingredient}」的多跳推理问答。

    返回可溯源结论：结论(避免/限量/推荐/未发现禁忌关联)、理由、营养证据、受影响菜谱。
    图谱不可用（Neo4j 未连接）时返回"图谱不可用"，不报错。
    """
    from app_my.core.kg import ask as kg_ask

    try:
        return json.dumps(kg_ask(ingredient, condition), ensure_ascii=False, indent=2)
    except Exception as exc:
        return json.dumps(
            {"error": str(exc), "note": "调用 kg.ask 失败，请确认 Neo4j 与依赖已就绪"},
            ensure_ascii=False,
        )


@mcp.tool()
async def chat_chief(message: str, thread_id: str = "mcp") -> str:
    """调用 AI私厨 多智能体 coordinator（营养师/推荐/识别/排序等）生成回答。

    底层即 /chat/stream 背后的 LangGraph StateGraph 编排；这里把它作为一个 MCP 工具暴露。
    需要可用的 LLM（设置 DASHSCOPE_API_KEY，或 MOCK_LLM=true 调试）。
    """
    from app_my.agents.coordinator import chat_coordinator

    try:
        parts = []
        async for chunk in chat_coordinator(
            text=message, thread_id=thread_id, user_id=None, image_url=None
        ):
            parts.append(chunk if isinstance(chunk, str) else str(chunk))
        return "".join(parts)
    except Exception as exc:
        return json.dumps(
            {
                "error": str(exc),
                "note": "调用 chat_coordinator 失败；请确认 LLM 已配置（或 MOCK_LLM=true）",
            },
            ensure_ascii=False,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="AI私厨 MCP Server（独立增量文件）")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="stdio（本地 Host）或 streamable-http（远程 Host）；默认 stdio",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8003")))
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # mcp 1.x 的 FastMCP.run() 不接受 host/port 关键字，需写到 settings
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
