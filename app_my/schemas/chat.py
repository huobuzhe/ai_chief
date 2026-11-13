from pydantic import BaseModel
from typing import List, Optional


class ChatRequest(BaseModel):
    message: str
    image_url: Optional[List[str]] = None
    thread_id: str = ""
    user_id: Optional[str] = None      #  阶段3 新增：用于读取用户画像（不传则按访客处理）