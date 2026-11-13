# tests/integration/test_tenant_api.py
"""租户 API 集成测试（需起本地服务，默认 pytest skip）"""
import pytest

pytestmark = pytest.mark.tenant


def test_register_creates_personal_tenant():
    # 启动 uvicorn 后用 httpx 调 /auth/register 然后 GET /tenants 断言有 1 个 personal
    pytest.skip("需手动验证：scripts/verify_stage4.py 已覆盖")