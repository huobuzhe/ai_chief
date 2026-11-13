# app_my/core/models.py
"""
惰性 LLM 单例
- 模块顶层不实例化，import 时不连 DashScope
- 单元测试/CI 在没有 API key 时不会因 import 失败
- 阶段 3 多节点工作流统一从这里取模型
"""
from functools import lru_cache
from langchain.chat_models import init_chat_model
from app_my.core.config import settings


@lru_cache()
def get_chat_model():
    """
    获取对话/多模态模型实例（全局单例）

    注意：默认走 OpenAI 兼容协议对接 DashScope，所以 model_provider='openai'
    """
    return init_chat_model(
        model=settings.CHAT_MODEL,
        model_provider="openai",
        base_url=settings.DASHSCOPE_BASE_URL,
        api_key=settings.DASHSCOPE_API_KEY,
    )

@lru_cache()
def get_vision_model():
    """
    获取多模态（看图）模型实例（全局单例）——阶段 3 新增。

    识别节点要"看图认食材"，用的模型和日常对话不同（qwen-omni 系列）。
    和 get_chat_model 一样是惰性单例：没配 API key 时 import 也不会挂。
    """
    return init_chat_model(
        model=settings.VISION_MODEL,
        model_provider="openai",
        base_url=settings.DASHSCOPE_BASE_URL,
        api_key=settings.DASHSCOPE_API_KEY,
    )

# ============================================================
# 阶段 2（v3.0）新增：分档模型工厂——智能路由的"弹药库"
# lite 档 = qwen3.7-flash（便宜 10 倍，抽食材等简单任务）
# standard 档 = qwen3.7-plus（质量好，报告等复杂任务）
# ============================================================

@lru_cache()
def get_lite_model():
    """
    轻量档模型单例（简单任务用，成本优先）。

    extra_body 关闭思考模式：qwen3.7 系列默认开启"深度思考"，
    对"抽取食材"这类指令型任务纯属浪费——思考 token 按输出价计费（实测一单多花 65%），
    还把响应拖慢好几秒。关掉后：更快、更便宜、结果一样准。
    """
    return init_chat_model(
        model=settings.MODEL_LITE,
        model_provider="openai",
        base_url=settings.DASHSCOPE_BASE_URL,
        api_key=settings.DASHSCOPE_API_KEY,
        extra_body={"enable_thinking": False},   # 关闭思考模式（v3阶段2 实测修复）
    )


@lru_cache()
def get_standard_model():
    """
    标准档模型单例（复杂任务用，质量优先）。

    同样关闭思考模式：实测开启时生成一份报告要 58 秒（思考占了大头），
    关闭后 2 秒内出结果，报告质量没有可感知差异——对延迟和成本都是硬收益。
    """
    return init_chat_model(
        model=settings.MODEL_STANDARD,
        model_provider="openai",
        base_url=settings.DASHSCOPE_BASE_URL,
        api_key=settings.DASHSCOPE_API_KEY,
        extra_body={"enable_thinking": False},   # 关闭思考模式（v3阶段2 实测修复）
    )


def get_model_for_tier(tier: str):
    """
    档位名 -> 模型实例（model_router 调这里，不直接碰具体模型名）。
    传入未知档位直接抛错：路由层漏配要在第一时间暴露，不能静默降级。
    """
    factories = {
        "lite": get_lite_model,
        "standard": get_standard_model,
        "vision": get_vision_model,
    }
    if tier not in factories:
        raise ValueError(f"未知模型档位: {tier}（可选: {list(factories)}）")
    return factories[tier]()

def reset_model_cache():
    """测试用：清空单例缓存"""
    get_chat_model.cache_clear()
    get_vision_model.cache_clear()
    get_lite_model.cache_clear()          # 阶段 2：新档位一并清理
    get_standard_model.cache_clear()

def has_api_key() -> bool:
    """供调用方做降级：缺失 API key 时返回友好文案而非 500"""
    return bool(settings.DASHSCOPE_API_KEY)