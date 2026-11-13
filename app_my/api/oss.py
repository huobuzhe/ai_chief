from fastapi import APIRouter, Response
import os
import oss2
from urllib.parse import quote_plus
from fastapi.concurrency import run_in_threadpool

router = APIRouter()

@router.options("/presign")
async def presign_options():
    return {}

def _gen_presign(filename: str):
    bucket_name = os.getenv("OSS_BUCKET")
    endpoint = os.getenv("OSS_ENDPOINT")
    # ===== 修正A：键名匹配 .env 的 ALIBABA_CLOUD_*（手册 3.1 改名后，oss.py 必须同步改）=====
    access_key = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")        # 原: OSS_ACCESS_KEY_ID
    secret_key = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")    # 原: OSS_ACCESS_KEY_SECRET
    print(f"读取到变量：bucket={bucket_name}, endpoint={endpoint}, ak={access_key[:6] if access_key else 'None'}...")
    auth = oss2.Auth(access_key, secret_key)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    object_key = filename
    content_type = "image/jpeg"
    if filename.lower().endswith(".png"):
        content_type = "image/png"
    upload_url = bucket.sign_url(
        method='PUT',
        key=object_key,
        expires=600,
        headers={'Content-Type': content_type}
    )
    access_url = f"https://{bucket_name}.{endpoint}/{quote_plus(object_key)}"
    return {
        "uploadUrl": upload_url,
        "accessUrl": access_url,
        "contentType": content_type
    }

@router.get("/presign")
async def get_oss_presign(filename: str, response: Response):
    print("=== presign 接口开始执行 ===")
    result = await run_in_threadpool(_gen_presign, filename)
    print("签名url生成完成")
    # 关键：返回后断开TCP连接，解决浏览器pending
    response.headers["Connection"] = "close"
    return result
