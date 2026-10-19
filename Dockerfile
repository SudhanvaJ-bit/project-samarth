# ─────────────────────────────────────────────────────────────────────────
# SAMARTH online demo — website + API in one container.
#
#   docker build -t samarth-demo .
#   docker run -p 8000:8000 samarth-demo        → http://localhost:8000
#
# Runs in DEMO mode: replays the recordings in demo/ and never calls Gemini,
# so the image contains no API key and needs none.
# ─────────────────────────────────────────────────────────────────────────

# ── Stage 1: build the website ───────────────────────────────────────────
FROM node:22-slim AS website
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# "/" = call the API on the same address the page was loaded from
ENV VITE_API_URL=/
RUN npm run build

# ── Stage 2: the API server ──────────────────────────────────────────────
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements-deploy.txt .
RUN pip install -r requirements-deploy.txt

COPY agents/        ./agents/
COPY app/           ./app/
COPY models/        ./models/
COPY pdf_generator/ ./pdf_generator/
COPY rag/           ./rag/
COPY demo/          ./demo/
COPY --from=website /build/dist ./website/

ENV SAMARTH_LLM_MODE=demo \
    SAMARTH_FRONTEND_DIST=/app/website \
    ANONYMIZED_TELEMETRY=False

# Run as an unprivileged user
RUN useradd --create-home samarth && chown -R samarth /app
USER samarth

EXPOSE 8000
# Render supplies $PORT; locally it defaults to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
