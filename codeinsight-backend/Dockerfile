FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    gcc \
    g++ \
    cmake \
    make \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY uv.lock* .

RUN pip install --no-cache-dir uv

RUN uv sync --extra dev

COPY packages/shared/src ./packages/shared/src
COPY codeinsight-backend .

RUN uv run datamodel-codegen \
    --input ./packages/shared/src/index.ts \
    --output ./codeinsight/schemas/shared.py

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "codeinsight.main:app", "--host", "0.0.0.0", "--port", "8000"]