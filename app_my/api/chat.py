# from fastapi import APIRouter
# from app_my.schemas.chat import ChatRequest
# from starlette.responses import StreamingResponse
# from app_my.agents.coordinator import chat_coordinator      # 🔵 改：多 Agent 入口

# router = APIRouter()


# @router.post("/stream")
# async def chat_endpoint(request: ChatRequest):
#     """流式对话：转发 coordinator 的产出"""
#     return StreamingResponse(
#         chat_coordinator(
#             text=request.message,
#             image_url=request.image_url,
#             thread_id=request.thread_id,
#             user_id=request.user_id,
#         ),
#         media_type="text/event-stream",
#     )

# app_my/api/chat.py
from fastapi import APIRouter, Request
from app_my.schemas.chat import ChatRequest
from starlette.responses import StreamingResponse
from app_my.agents.coordinator import chat_coordinator

router = APIRouter()


@router.post("/stream")
async def chat_endpoint(request: Request, payload: ChatRequest):
    """
    流式对话：转发 coordinator 的产出。
    v3阶段4 起：把 tenant_id 透传给 coordinator（用于记账按租户归集）；
                配额检查由 QuotaMiddleware 完成。
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    return StreamingResponse(
        chat_coordinator(
            text=payload.message,
            image_url=payload.image_url,
            thread_id=payload.thread_id,
            user_id=payload.user_id,
            tenant_id=tenant_id,   # 新增
        ),
        media_type="text/event-stream",
    )