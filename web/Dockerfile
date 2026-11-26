# 生产镜像：Python 3.12 + Uvicorn，非 root 运行，数据目录挂卷
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FIT_HOST=0.0.0.0 \
    FIT_PORT=8000 \
    FIT_DB_PATH=/app/data/fitness.db \
    FIT_TIMEZONE=Asia/Shanghai

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 持久化数据（计划/账号/会话）都在这里，容器重建不丢
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# 单进程：SQLite 单文件写入，1 个 worker 最稳；--proxy-headers 让 Nginx 反代后能取到真实协议/来源
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
