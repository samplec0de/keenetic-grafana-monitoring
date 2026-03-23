FROM ghcr.io/astral-sh/uv:0.8.22 AS uv

FROM python:3.8-alpine AS dependencies
COPY --from=uv /uv /uvx /bin/

WORKDIR /home
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock /home/
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.8-alpine AS build-image
WORKDIR /home
ENV PATH="/home/.venv/bin:$PATH"

COPY --from=dependencies /home/.venv /home/.venv
COPY value_normalizer.py keentic_influxdb_exporter.py influxdb_writter.py keenetic_api.py /home/
COPY config/metrics.json /home/config/metrics.json

CMD [ "python", "-u", "/home/keentic_influxdb_exporter.py" ]
