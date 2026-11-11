FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEMORY_BOOK_HOME=/data \
    MEMORY_BOOK_DB=/data/memory.db

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir '.[mcp,clients]' \
    && groupadd --gid 10001 memorybook \
    && useradd --uid 10001 --gid 10001 --create-home memorybook \
    && mkdir -p /data \
    && chown 10001:10001 /data

USER 10001:10001
VOLUME ["/data"]
ENTRYPOINT ["memory-book"]
CMD ["mcp"]
