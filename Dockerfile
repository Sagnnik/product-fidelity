FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_CLERK_PUBLISHABLE_KEY
RUN test -n "$VITE_CLERK_PUBLISHABLE_KEY" && npm run build

FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev
COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist/ ./frontend/dist/

CMD ["sh", "-c", "exec .venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
