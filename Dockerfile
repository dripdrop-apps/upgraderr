FROM ghcr.io/astral-sh/uv:python3.11-alpine

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT [ "/app/entrypoint.sh" ]
