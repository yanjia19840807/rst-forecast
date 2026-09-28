import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from rst_forecast.auth import ApiKeyAuthMiddleware
from rst_forecast.forecast_service import (
    ForecastInputError,
    forecast_daily,
    forecast_monthly,
)
from rst_forecast.schemas import (
    DailyForecastRequest,
    DailyForecastResponse,
    HealthResponse,
    MonthlyForecastRequest,
    MonthlyForecastResponse,
)
from rst_forecast.settings import get_settings

LOGGER = logging.getLogger("rst_forecast.http")
MAX_BODY_LOG_CHARS = 8_000


def _preview(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = text.replace("\n", " ").strip()
    if len(text) > MAX_BODY_LOG_CHARS:
        return text[:MAX_BODY_LOG_CHARS] + f"…(+{len(text) - MAX_BODY_LOG_CHARS} chars)"
    return text


class RequestResponseLoggingMiddleware(BaseHTTPMiddleware):
    """Logs HTTP method/path, request body, status, and response body."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        body = await request.body()

        # Re-inject body so downstream (FastAPI parsing) can read it again.
        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)

        LOGGER.info(
            "REQ %s %s request_id=%s body=%s",
            request.method,
            request.url.path,
            request_id,
            _preview(body) or "<empty>",
        )

        response = await call_next(request)
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        LOGGER.info(
            "RES %s %s status=%s request_id=%s body=%s",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            _preview(response_body) or "<empty>",
        )

        headers = dict(response.headers)
        headers["X-Request-ID"] = request_id
        # Content-Length may be stale after we re-buffer the body.
        headers.pop("content-length", None)
        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
            background=response.background,
        )


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Synchronous forecasting service for the Right Sizing Tool.",
    )
    # ApiKey first so logging (added last) remains outermost and records 401s.
    app.add_middleware(ApiKeyAuthMiddleware, api_key=settings.api_key)
    app.add_middleware(RequestResponseLoggingMiddleware)

    @app.exception_handler(ForecastInputError)
    async def forecast_input_error(
        request: Request,
        exception: ForecastInputError,
    ) -> JSONResponse:
        LOGGER.warning(
            "ForecastInputError path=%s detail=%s",
            request.url.path,
            exception,
        )
        return JSONResponse(
            status_code=422,
            content={
                "type": "forecast-input-error",
                "title": "Invalid forecast input",
                "status": 422,
                "detail": str(exception),
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request,
        exception: RequestValidationError,
    ) -> JSONResponse:
        LOGGER.warning(
            "RequestValidationError path=%s errors=%s",
            request.url.path,
            exception.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "type": "request-validation-error",
                "title": "Request validation failed",
                "status": 422,
                "detail": exception.errors(),
                "instance": str(request.url.path),
            },
        )

    @app.get("/health", tags=["Operations"], response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="UP",
            service="rst-forecast",
            version=settings.app_version,
        )

    @app.post(
        "/api/v1/forecasts/monthly",
        tags=["Forecasts"],
        response_model=MonthlyForecastResponse,
    )
    def monthly_forecast(request: MonthlyForecastRequest) -> MonthlyForecastResponse:
        return forecast_monthly(request, settings)

    @app.post(
        "/api/v1/forecasts/daily",
        tags=["Forecasts"],
        response_model=DailyForecastResponse,
    )
    def daily_forecast(request: DailyForecastRequest) -> DailyForecastResponse:
        return forecast_daily(request, settings)

    return app


app = create_app()
