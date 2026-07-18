# syntax=docker/dockerfile:1
# Multi-stage build. BUILD CONTEXT MUST BE THE REPO ROOT so that both web/ and
# agent/ are available:  docker build -f web/Dockerfile -t expense-tracker .

# ---- Stage 1: build the React/Vite frontend ----
FROM node:20-alpine AS frontend
WORKDIR /fe
COPY web/frontend/package.json web/frontend/package-lock.json* ./
RUN npm install
COPY web/frontend/ ./
RUN npm run build

# ---- Stage 2: python runtime serving API + built frontend ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FRONTEND_DIST_DIR=/app/web/frontend/dist
WORKDIR /app

# System libs needed by pdfplumber/Pillow/matplotlib at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo zlib1g libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# Install python deps (agent core + web layer) first for better layer caching.
COPY agent/requirements.txt /app/agent/requirements.txt
COPY web/backend/requirements.txt /app/web/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/agent/requirements.txt \
    && pip install --no-cache-dir -r /app/web/backend/requirements.txt

# App source: shared agent core + web backend.
COPY agent/ /app/agent/
COPY web/backend/ /app/web/backend/

# Built frontend from stage 1.
COPY --from=frontend /fe/dist /app/web/frontend/dist

EXPOSE 8080
WORKDIR /app/web/backend
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
