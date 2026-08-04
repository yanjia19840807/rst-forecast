import logging
from collections.abc import Sequence
from datetime import date
from time import perf_counter

import numpy as np
import pandas as pd
import statsmodels.api as sm

from rst_forecast.schemas import (
    ForecastPoint,
    ModelMetadata,
    MonthlyActual,
    MonthlyForecastRequest,
    MonthlyForecastResponse,
    MonthlyFuture,
)
from rst_forecast.settings import Settings

LOGGER = logging.getLogger(__name__)

ORDER = (1, 1, 1)
SEASONAL_ORDER = (1, 1, 1, 12)


class ForecastInputError(ValueError):
    """Raised when forecast input is inconsistent."""


def _periods(rows: Sequence[MonthlyActual | MonthlyFuture]) -> list[pd.Period]:
    return [pd.Period(row.date_month, freq="M") for row in rows]


def _validate_contiguous(name: str, periods: list[pd.Period]) -> None:
    if len(set(periods)) != len(periods):
        raise ForecastInputError(f"{name} contains duplicate months")

    expected = list(pd.period_range(min(periods), max(periods), freq="M"))
    if sorted(periods) != expected:
        raise ForecastInputError(f"{name} must contain contiguous months")


def _month_end(period: pd.Period) -> date:
    return period.to_timestamp(how="end").normalize().date()


def _exogenous(
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

    _validate_contiguous("history", history_periods)
    _validate_contiguous("future", future_periods)
    if future_periods[0] != history_periods[-1] + 1:
        raise ForecastInputError("future must start in the month after history")

    history_index = pd.date_range(
        start=history_periods[0].to_timestamp(how="end").normalize(),
        periods=len(history_periods),
        freq="ME",
    )
    future_index = pd.date_range(
        start=future_periods[0].to_timestamp(how="end").normalize(),
        periods=len(future_periods),
        freq="ME",
    )
    target = pd.Series(
        [row.actual_volume for row in history],
        index=history_index,
        dtype=float,
        name="actual_volume",
    )

    model = sm.tsa.SARIMAX(
        target,
        exog=_exogenous(history, history_index),
        order=ORDER,
        seasonal_order=SEASONAL_ORDER,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    result = model.fit(disp=False, maxiter=settings.max_model_iterations)
    if not result.mle_retvals.get("converged", False):
        LOGGER.warning("SARIMAX optimization did not converge")

    prediction = result.get_forecast(
        steps=len(future),
        exog=_exogenous(future, future_index),
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
            order=ORDER,
            seasonal_order=SEASONAL_ORDER,
            training_start=_month_end(history_periods[0]),
            training_end=_month_end(history_periods[-1]),
            observation_count=len(history),
        ),
        confidence_level=request.confidence_level,
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
