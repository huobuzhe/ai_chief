# app_my/api/user.py
"""
阶段 4 用户接口：/users/me。

身份不重复解析：AuthMiddleware 已经把 user_id 放进 request.state，
这里只负责"拿 id 查最新资料"——token 里没有用户名/邮箱，改资料后这里能立刻反映。
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app_my.db.models.user import User
from app_my.db.session import get_db
from app_my.schemas.auth import UserOut

router = APIRouter()


@router.get("/me", response_model=UserOut)
def read_me(request: Request, db: Session = Depends(get_db)):
    """当前登录用户的信息（需要 Authorization: Bearer <access_token>）"""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:  # 正常到不了（AuthMiddleware 先拦），防御式兜底
        raise HTTPException(status_code=401, detail="未认证")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user