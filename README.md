# RST Forecast

Python forecasting service for the Right Sizing Tool. The service exposes a
synchronous SARIMAX API and is called by `rst-api`; browsers must not call it
directly.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## Local development

```sh
uv sync
uv run uvicorn rst_forecast.main:app --reload
```

The service listens on `http://localhost:8000`.

- Health: `GET /health`
- OpenAPI UI: `GET /docs`
- Monthly forecast: `POST /api/v1/forecasts/monthly`

The monthly endpoint requires at least 36 contiguous historical observations
and 1–36 contiguous future months. Future calendar and commercial-ratio values
must be supplied by the caller.

## Quality checks

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Upgrade dependencies intentionally and commit the updated lock file:

```sh
uv lock --upgrade
uv sync
```

## Container

```sh
docker build -t rst-forecast .
docker run --rm -p 8000:8000 rst-forecast
```
