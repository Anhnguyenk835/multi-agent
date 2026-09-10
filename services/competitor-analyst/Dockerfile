FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md .python-version ./
COPY services ./services
COPY packages ./packages

RUN uv sync --frozen --no-dev --package competitor-analyst

# Call the venv directly instead of "uv run": uv sync already built it above,
# and "uv run" re-checks the lock/sync state on every cold start, which costs
# 60-90s recompiling bytecode on Cloud Run's ephemeral filesystem every time
# an instance scales up from zero.
CMD ["/app/.venv/bin/opentelemetry-instrument", "/app/.venv/bin/python", "-m", "competitor_analyst.server"]
