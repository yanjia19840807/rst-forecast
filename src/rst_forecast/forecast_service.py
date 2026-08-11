import logging
from collections.abc import Sequence
from datetime import date, timedelta
from time import perf_counter

import numpy as np
import pandas as pd
import statsmodels.api as sm

from rst_forecast.schemas import (
    DailyActual,
    DailyForecastPoint,
    DailyForecastRequest,
    DailyForecastResponse,
    DailyFuture,
    ForecastPoint,
    ModelMetadata,
    MonthlyActual,
    MonthlyForecastRequest,
    MonthlyForecastResponse,
    MonthlyFuture,
)
from rst_forecast.settings import Settings

LOGGER = logging.getLogger(__name__)

MONTHLY_ORDER = (1, 1, 1)
MONTHLY_SEASONAL_ORDER = (1, 1, 1, 12)
DAILY_ORDER = (1, 1, 1)
DAILY_SEASONAL_ORDER = (1, 1, 1, 7)


class ForecastInputError(ValueError):
    """Raised when forecast input is inconsistent."""


def _periods(rows: Sequence[MonthlyActual | MonthlyFuture]) -> list[pd.Period]:
    return [pd.Period(row.date_month, freq="M") for row in rows]


def _validate_unique(name: str, periods: list[pd.Period]) -> None:
    if len(set(periods)) != len(periods):
        raise ForecastInputError(f"{name} contains duplicate months")


def _validate_contiguous(name: str, periods: list[pd.Period]) -> None:
    _validate_unique(name, periods)
    expected = list(pd.period_range(min(periods), max(periods), freq="M"))
    if sorted(periods) != expected:
        raise ForecastInputError(f"{name} must contain contiguous months")


def _month_end(period: pd.Period) -> date:
    return period.to_timestamp(how="end").normalize().date()


def _month_end_index(periods: list[pd.Period]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(
        [period.to_timestamp(how="end").normalize() for period in periods]
    )


def _monthly_exogenous(
    rows: Sequence[MonthlyActual | MonthlyFuture],
    index: pd.DatetimeIndex,
) -> pd.DataFrame:
    months = index.month.to_numpy(dtype=float)
    return pd.DataFrame(
        {
            "workdays": [row.work_days for row in rows],
            "weekenddays": [row.weekend_days for row in rows],
            "commercial": [row.commercial_ratio for row in rows],
            "month_sin": np.sin(2 * np.pi * months / 12),
            "month_cos": np.cos(2 * np.pi * months / 12),
        },
        index=index,
        dtype=float,
    )


def forecast_monthly(
    request: MonthlyForecastRequest,
    settings: Settings,
) -> MonthlyForecastResponse:
    started_at = perf_counter()
    history = sorted(request.history, key=lambda row: row.date_month)
    future = sorted(request.future, key=lambda row: row.date_month)
    history_periods = _periods(history)
    future_periods = _periods(future)

    # Like Excel demo: fit only months with Actual (gaps allowed via dropna).
    _validate_unique("history", history_periods)
    _validate_contiguous("future", future_periods)
    if future_periods[0] != history_periods[-1] + 1:
        raise ForecastInputError("future must start in the month after history")

    history_index = _month_end_index(history_periods)
    future_index = _month_end_index(future_periods)
    target = pd.Series(
        [row.actual_volume for row in history],
        index=history_index,
        dtype=float,
        name="actual_volume",
    )

    model = sm.tsa.SARIMAX(
        target,
        exog=_monthly_exogenous(history, history_index),
        order=MONTHLY_ORDER,
        seasonal_order=MONTHLY_SEASONAL_ORDER,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    result = model.fit(disp=False, maxiter=settings.max_model_iterations)
    if not result.mle_retvals.get("converged", False):
        LOGGER.warning("SARIMAX monthly optimization did not converge")

    prediction = result.get_forecast(
        steps=len(future),
        exog=_monthly_exogenous(future, future_index),
    )
    confidence_interval = prediction.conf_int(alpha=1 - request.confidence_level)
    mean = prediction.predicted_mean.to_numpy(dtype=float)
    lower = confidence_interval.iloc[:, 0].to_numpy(dtype=float)
    upper = confidence_interval.iloc[:, 1].to_numpy(dtype=float)

    return MonthlyForecastResponse(
        forecasts=[
            ForecastPoint(
                date_month=_month_end(period),
                forecast=float(mean[index]),
                lower=float(lower[index]),
                upper=float(upper[index]),
            )
            for index, period in enumerate(future_periods)
        ],
        model=ModelMetadata(
            name="SARIMAX",
            version=settings.model_version,
            order=MONTHLY_ORDER,
            seasonal_order=MONTHLY_SEASONAL_ORDER,
            training_start=_month_end(history_periods[0]),
            training_end=_month_end(history_periods[-1]),
            observation_count=len(history),
        ),
        confidence_level=request.confidence_level,
        duration_ms=round((perf_counter() - started_at) * 1000),
    )


def _validate_unique_dates(name: str, dates: list[date]) -> None:
    if len(set(dates)) != len(dates):
        raise ForecastInputError(f"{name} contains duplicate dates")


def _validate_contiguous_dates(name: str, dates: list[date]) -> None:
    _validate_unique_dates(name, dates)
    ordered = sorted(dates)
    expected = [
        ordered[0] + timedelta(days=offset) for offset in range(len(ordered))
    ]
    if ordered != expected:
        raise ForecastInputError(f"{name} must contain contiguous calendar days")


def _daily_exogenous(
    rows: Sequence[DailyActual | DailyFuture],
    index: pd.DatetimeIndex,
) -> pd.DataFrame:
    day_of_week = index.dayofweek.to_numpy(dtype=float)
    return pd.DataFrame(
        {
            "is_working_day": [1.0 if row.is_working_day else 0.0 for row in rows],
            "is_holiday": [1.0 if row.is_holiday else 0.0 for row in rows],
            "commercial": [row.commercial_ratio for row in rows],
            "dow_sin": np.sin(2 * np.pi * day_of_week / 7),
            "dow_cos": np.cos(2 * np.pi * day_of_week / 7),
        },
        index=index,
        dtype=float,
    )


def forecast_daily(
    request: DailyForecastRequest,
    settings: Settings,
) -> DailyForecastResponse:
    started_at = perf_counter()
    history = sorted(request.history, key=lambda row: row.date)
    future = sorted(request.future, key=lambda row: row.date)
    history_dates = [row.date for row in history]
    future_dates = [row.date for row in future]

    _validate_unique_dates("history", history_dates)
    _validate_contiguous_dates("future", future_dates)
    if future_dates[0] != history_dates[-1] + timedelta(days=1):
        raise ForecastInputError("future must start on the day after the last history date")

    history_index = pd.DatetimeIndex(pd.to_datetime(history_dates))
    future_index = pd.DatetimeIndex(pd.to_datetime(future_dates))
    target = pd.Series(
        [row.actual_volume for row in history],
        index=history_index,
        dtype=float,
        name="actual_volume",
    )

    model = sm.tsa.SARIMAX(
        target,
        exog=_daily_exogenous(history, history_index),
        order=DAILY_ORDER,
        seasonal_order=DAILY_SEASONAL_ORDER,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    result = model.fit(disp=False, maxiter=settings.max_model_iterations)
    if not result.mle_retvals.get("converged", False):
        LOGGER.warning("SARIMAX daily optimization did not converge")

    prediction = result.get_forecast(
        steps=len(future),
        exog=_daily_exogenous(future, future_index),
    )
    confidence_interval = prediction.conf_int(alpha=1 - request.confidence_level)
    mean = prediction.predicted_mean.to_numpy(dtype=float)
    lower = confidence_interval.iloc[:, 0].to_numpy(dtype=float)
    upper = confidence_interval.iloc[:, 1].to_numpy(dtype=float)

    return DailyForecastResponse(
        forecasts=[
            DailyForecastPoint(
                date=day,
                forecast=float(mean[index]),
                lower=float(lower[index]),
                upper=float(upper[index]),
            )
            for index, day in enumerate(future_dates)
        ],
        model=ModelMetadata(
            name="SARIMAX",
            version=settings.model_version,
            order=DAILY_ORDER,
            seasonal_order=DAILY_SEASONAL_ORDER,
            training_start=history_dates[0],
            training_end=history_dates[-1],
            observation_count=len(history),
        ),
        confidence_level=request.confidence_level,
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
