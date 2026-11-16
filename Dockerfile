FROM python:3.12-slim-bookworm AS native-build

WORKDIR /build
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml setup.py README.md LICENSE ./
COPY src ./src
RUN MEMORY_BOOK_BUILD_NATIVE=1 python -m pip wheel --no-cache-dir --wheel-dir /wheels '.[mcp,clients]'

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEMORY_BOOK_HOME=/data \
    MEMORY_BOOK_DB=/data/memory.db

WORKDIR /app
COPY --from=native-build /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels 'ai-memory-book[mcp,clients]' \
    && python -c "from memory_book._text_backend import BACKEND_NAME; assert BACKEND_NAME == 'native'" \
    && rm -rf /wheels \
    && groupadd --gid 10001 memorybook \
    && useradd --uid 10001 --gid 10001 --create-home memorybook \
    && mkdir -p /data \
    && chown 10001:10001 /data

USER 10001:10001
VOLUME ["/data"]
ENTRYPOINT ["memory-book"]
CMD ["mcp"]
