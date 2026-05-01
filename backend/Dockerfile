FROM python:3.12-slim AS base
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && (apt-get install -y --no-install-recommends libaio1t64 || apt-get install -y --no-install-recommends libaio1 || true) \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/uploads

# 非 root ユーザーを作成し /app の所有権を移譲する
# (コンテナ内権限昇格時の被害範囲縮小のため)
RUN useradd -r -u 1000 -m appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
