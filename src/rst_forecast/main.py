import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rst_forecast.forecast_service import ForecastInputError, forecast_monthly
from rst_forecast.schemas import (
    HealthResponse,
    MonthlyForecastRequest,
    MonthlyForecastResponse,
)
from rst_forecast.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Synchronous forecasting service for the Right Sizing Tool.",
    )

    @app.middleware("http")
    async def correlation_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(ForecastInputError)
    async def forecast_input_error(
        request: Request,
        exception: ForecastInputError,
    ) -> JSONResponse:
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

    return app


app = create_app()
