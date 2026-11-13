# docker/api.Dockerfile - AI 私厨后端镜像（阶段 6）
FROM python:3.13-slim

WORKDIR /app

# 国内镜像源装依赖（和本机 pip 用清华源同理）
ENV PYTHONUTF8=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 先装依赖（利用 Docker 层缓存：代码改了不用重装依赖）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 再拷代码
COPY app_my ./app_my
COPY main.py ./

EXPOSE 8002

CMD ["python", "main.py"]