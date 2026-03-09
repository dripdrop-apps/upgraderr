FROM ghcr.io/astral-sh/uv:python3.11-alpine

RUN apk add --no-cache bash

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x /app/upgraderr && ln -s /app/upgraderr /usr/local/bin/upgraderr

RUN mkdir /logs

CMD [ "run" ]

ENTRYPOINT [ "upgraderr" ]
