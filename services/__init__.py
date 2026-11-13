# services/__init__.py
"""
services —— AI 私厨 v3.0 阶段 9「微服务拆分」的服务目录

四个独立进程（共享 app_my 代码内核，各自监听不同端口）：
    user        9121  认证 / 用户 / 租户 / 管理端 / 成本统计
    recognizer  9122  食材识别 + 营养估算（原 LangGraph 的 ①② 号节点）
    recommender 9123  菜谱推荐 + 个性化重排 + 知识图谱（原 ③ 号节点 + /kg）
    chat        9124  对话编排 + WebSocket 推送 + 异步任务提交

统一入口是 Kong（9100），外部只该访问 9100。
"""
