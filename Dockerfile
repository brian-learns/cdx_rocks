# ==========================================
# Stage 1: The Build/Dependency stage
# ==========================================
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy 

# Idiomatic astral way to force global system package installation
ENV UV_PROJECT_ENVIRONMENT="/usr/local"

COPY pyproject.toml uv.lock ./

# Standard uv sync commands (no conflicting flags)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# ==========================================
# Stage 2: The lean Production stage
# ==========================================
FROM python:3.13-slim AS runner

WORKDIR /app

RUN groupadd -r fastapi && useradd -r -g fastapi fastapi

# Copy python packages and the native CLI executable cleanly
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin/fastapi /usr/local/bin/fastapi
COPY --from=builder /app/app /app/app

RUN mkdir -p /app/data && chown -R fastapi:fastapi /app

USER fastapi
VOLUME ["/app/data"]
EXPOSE 8000
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "7860"]
