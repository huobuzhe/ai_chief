"""
阶段 7 验证用：临时 500 触发器
测试完删除整个文件
"""
from fastapi import APIRouter, HTTPException
router = APIRouter()

@router.get("/debug/500")
async def debug_500():
    raise HTTPException(status_code=500, detail="阶段 7 告警测试用，看完删")