from datetime import date
from math import isfinite, sin

import pandas as pd
import pytest

from rst_forecast.forecast_service import (
    ForecastInputError,
    forecast_daily,
    forecast_monthly,
)
from rst_forecast.schemas import (
    DailyActual,
    DailyForecastRequest,
    DailyFuture,
    MonthlyActual,
    MonthlyForecastRequest,
    MonthlyFuture,
)
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


def test_forecast_monthly_allows_history_gaps() -> None:
    """Fit only months with Actual; gaps allowed (Excel demo dropna)."""
    all_periods = list(pd.period_range("2021-01", periods=48, freq="M"))
    history_periods = [period for period in all_periods if period.strftime("%Y-%m") != "2023-06"]
    future_periods = pd.period_range("2025-01", periods=3, freq="M")
    request = MonthlyForecastRequest(
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

    response = forecast_monthly(request, Settings(max_model_iterations=1))

    assert len(response.forecasts) == 3
    assert response.model.observation_count == 47


def _daily_request() -> DailyForecastRequest:
    history_dates = pd.date_range("2026-07-01", periods=31, freq="D")
    future_dates = pd.date_range("2026-08-01", periods=31, freq="D")
    return DailyForecastRequest(
        history=[
            DailyActual(
                date=day.date(),
                actual_volume=80 + index * 0.4 + 10 * sin(index * 2 * 3.14159 / 7),
                is_working_day=day.dayofweek < 5,
                is_holiday=False,
                commercial_ratio=0.05,
            )
            for index, day in enumerate(history_dates)
        ],
        future=[
            DailyFuture(
                date=day.date(),
                is_working_day=day.dayofweek < 5,
                is_holiday=False,
                commercial_ratio=0.05,
            )
            for day in future_dates
        ],
    )


def test_forecast_daily_returns_requested_horizon() -> None:
    response = forecast_daily(_daily_request(), Settings(max_model_iterations=1))

    assert len(response.forecasts) == 31
    assert response.model.seasonal_order == (1, 1, 1, 7)
    assert response.model.observation_count == 31
    assert all(isfinite(point.forecast) for point in response.forecasts)


def test_forecast_daily_allows_history_gaps() -> None:
    request = _daily_request()
    # Drop a mid-window day; last history date stays 2026-07-31 so Aug future is valid.
    request.history = [row for row in request.history if row.date.day != 15]

    response = forecast_daily(request, Settings(max_model_iterations=1))

    assert len(response.forecasts) == 31
    assert response.model.observation_count == 30
