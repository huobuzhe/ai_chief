# services/recognizer/main.py
"""
recognizer 服务（端口 9122）—— 把"用户说了什么 / 拍了什么"变成结构化食材清单

拆出来的理由（拆分依据第二条：故障半径）：
    识别节点要调**多模态大模型**（看图），是所有节点里最慢、最贵、最容易超时的一环。
    它单独成一个服务，好处很实在：
      · 它超时/报错时，只影响"识别"，chat 服务还能用上一轮结果继续跑；
      · 它慢的时候可以单独加实例（比如 2 个 recognizer + 1 个 chat）；
      · 改识别模型不用重启整个应用。

对外只有两个"内部接口"（/internal/ 前缀，约定只给服务间调用）：
    POST /internal/nodes/recognize   文字/图片 → 食材清单
    POST /internal/nodes/nutrition   食材清单 → 营养估算

🔴 为什么要重新包一层 HTTP 接口，而不是直接把 state 整个传过来：
    LangGraph 的 state 里有 messages 字段，里面装的是 LangChain 的
    HumanMessage / AIMessage **对象**，不是 JSON。直接 json.dumps 会报
    "Object of type HumanMessage is not JSON serializable"。
    所以这里定了一套"只传必要字段"的窄接口：进 JSON、出 JSON。
"""
from typing import List, Optional

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app_my.agents.nutritionist import nutrition_node
from app_my.agents.recognizer import recognize_node
from app_my.api import oss
from app_my.core.logging import logger
from services.common.app_factory import create_service_app


# ----------------------------------------------------------------- 接口的数据契约
class RecognizeIn(BaseModel):
    """识别接口的入参。"""
    text: str = Field(default="", description="用户输入的文字（图片模式下可作补充提示）")
    image_url: List[str] = Field(default_factory=list, description="图片 URL 列表，空数组=走文字抽取")


class NutritionIn(BaseModel):
    """营养接口的入参。"""
    ingredients: List[dict] = Field(default_factory=list, description="上一步识别出的食材清单")


def _summary_of(node_output: dict) -> str:
    """
    从节点返回值里抽出那条 AIMessage 的文本，作为 summary 返回。

    节点返回形如 {"nutrition": {...}, "messages": [AIMessage("...")]}；
    messages 是 LangChain 对象不能进 JSON，所以这里提前把它转成纯字符串。
    """
    msgs = node_output.get("messages") or []
    if msgs:
        return getattr(msgs[-1], "content", "") or ""
    return ""


router = APIRouter()


@router.post("/internal/nodes/recognize")
async def http_recognize(body: RecognizeIn):
    """
    把 recognize_node 包成 HTTP 接口。

    做法：造一个"最小可用的 state" → 调原来的节点函数 → 把结果转成纯 JSON。
    这样**一个字的业务逻辑都没重写**，只是加了一层协议转换。
    """
    state = {
        "messages": [HumanMessage(content=body.text)],   # 节点只读最后一条消息的 content
        "image_url": body.image_url or [],
    }
    out = await recognize_node(state)
    logger.info("recognizer.http: 识别完成，%d 种食材", len(out.get("ingredients") or []))
    return {
        "ingredients": out.get("ingredients") or [],
        "summary": _summary_of(out),
    }


@router.post("/internal/nodes/nutrition")
async def http_nutrition(body: NutritionIn):
    """把 nutrition_node 包成 HTTP 接口。"""
    state = {"ingredients": body.ingredients or []}
    out = await nutrition_node(state)
    return {
        "nutrition": out.get("nutrition") or {},
        "summary": _summary_of(out),
    }


app = create_service_app(
    "recognizer",
    routers=[
        (router, "", ["识别内部接口"]),
        (oss.router, "/oss", ["阿里云OSS"]),   # 图片要先上传才能识别，归识别域
    ],
    enable_auth=True,      # 一样要鉴权：Kong 不做鉴权，靠各服务自己守门
    enable_quota=False,
    capture_auth=False,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("services.recognizer.main:app", host="0.0.0.0", port=9122, reload=False)
