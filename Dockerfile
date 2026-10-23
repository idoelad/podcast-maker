FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    NOTEBOOKLM_HOME=/data/notebooklm

WORKDIR /app
COPY pyproject.toml ./
COPY podcast_maker ./podcast_maker
RUN pip install . && useradd --create-home --uid 1000 app && mkdir -p /data/notebooklm && chown -R app /data

USER app
CMD ["podcast-bot"]
