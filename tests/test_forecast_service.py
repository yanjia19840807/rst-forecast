from datetime import date
from math import isfinite, sin

import pandas as pd
import pytest

from rst_forecast.forecast_service import ForecastInputError, forecast_monthly
from rst_forecast.schemas import MonthlyActual, MonthlyForecastRequest, MonthlyFuture
from rst_forecast.settings import Settings


def _month_end(period: pd.Period) -> date:
    return period.to_timestamp(how="end").date()


def _request() -> MonthlyForecastRequest:
    history_periods = pd.period_range("2021-01", periods=48, freq="M")
    future_periods = pd.period_range("2025-01", periods=3, freq="M")
    return MonthlyForecastRequest(
        history=[
            MonthlyActual(
                date_month=_month_end(period),
                actual_volume=1_000 + index * 8 + 100 * sin(index * 2 * 3.14159 / 12),
                work_days=22,
                weekend_days=8,
                commercial_ratio=0.05,
            )
            for index, period in enumerate(history_periods)
        ],
        future=[
            MonthlyFuture(
                date_month=_month_end(period),
                work_days=22,
                weekend_days=8,
                commercial_ratio=0.05,
            )
            for period in future_periods
        ],
    )


def test_forecast_monthly_returns_requested_horizon() -> None:
    response = forecast_monthly(_request(), Settings(max_model_iterations=1))

    assert len(response.forecasts) == 3
    assert response.model.name == "SARIMAX"
    assert response.model.observation_count == 48
    assert all(isfinite(point.forecast) for point in response.forecasts)
    assert all(point.lower <= point.upper for point in response.forecasts)


def test_forecast_monthly_rejects_gap_before_future() -> None:
    request = _request()
    request.future[0].date_month = request.future[1].date_month

    with pytest.raises(ForecastInputError, match="duplicate months"):
        forecast_monthly(request, Settings())
