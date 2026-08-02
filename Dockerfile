FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apm_notifier ./apm_notifier
COPY config ./config

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates chromium curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 notifier \
    && mkdir -p /data \
    && chown -R notifier:notifier /app /data

USER notifier
VOLUME ["/data"]
ENTRYPOINT ["python", "-m", "apm_notifier"]
CMD ["run"]
