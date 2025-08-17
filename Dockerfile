# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (optional, keep slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

# Set timezone via env (default UTC)
ARG TZ
ENV TZ=${TZ:-UTC}

COPY requirements.txt ./
RUN python -m pip install --upgrade pip && pip install -r requirements.txt && pip install uvicorn

COPY . .

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
