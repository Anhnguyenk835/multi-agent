FROM python:3.12-slim

ARG LITELLM_VERSION=1.98.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir "litellm[proxy]==${LITELLM_VERSION}"

RUN useradd --create-home --shell /usr/sbin/nologin litellm

WORKDIR /app
COPY --chown=litellm:litellm config.yaml /app/config.yaml

USER litellm

EXPOSE 4000

ENTRYPOINT ["litellm"]
CMD ["--config", "/app/config.yaml", "--host", "0.0.0.0", "--port", "4000", "--telemetry", "False", "--use_v2_migration_resolver"]
