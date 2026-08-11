from datetime import date

from pydantic import BaseModel, Field


class MonthlyActual(BaseModel):
    date_month: date
    actual_volume: float = Field(ge=0)
    work_days: int = Field(ge=0, le=31)
    weekend_days: int = Field(ge=0, le=31)
    commercial_ratio: float = Field(default=0, ge=-1, le=10)


class MonthlyFuture(BaseModel):
    date_month: date
    work_days: int = Field(ge=0, le=31)
    weekend_days: int = Field(ge=0, le=31)
    commercial_ratio: float = Field(default=0, ge=-1, le=10)


class MonthlyForecastRequest(BaseModel):
    """History months with Actual Volume only (gaps allowed), like Excel demo dropna fit."""

    history: list[MonthlyActual] = Field(min_length=1)
    future: list[MonthlyFuture] = Field(min_length=1, max_length=36)
    confidence_level: float = Field(default=0.95, gt=0, lt=1)


class DailyActual(BaseModel):
    date: date
    actual_volume: float = Field(ge=0)
    is_working_day: bool
    is_holiday: bool = False
    commercial_ratio: float = Field(default=0, ge=-1, le=10)


class DailyFuture(BaseModel):
    date: date
    is_working_day: bool
    is_holiday: bool = False
    commercial_ratio: float = Field(default=0, ge=-1, le=10)


class DailyForecastRequest(BaseModel):
    """History days with Actual Volume only (gaps allowed). Future must be contiguous calendar days."""

    history: list[DailyActual] = Field(min_length=1)
    future: list[DailyFuture] = Field(min_length=1, max_length=62)
    confidence_level: float = Field(default=0.95, gt=0, lt=1)


class ForecastPoint(BaseModel):
    date_month: date
    forecast: float
    lower: float
    upper: float


class DailyForecastPoint(BaseModel):
    date: date
    forecast: float
    lower: float
    upper: float


class ModelMetadata(BaseModel):
    name: str
    version: str
    order: tuple[int, int, int]
    seasonal_order: tuple[int, int, int, int]
    training_start: date
    training_end: date
    observation_count: int


class MonthlyForecastResponse(BaseModel):
    forecasts: list[ForecastPoint]
    model: ModelMetadata
    confidence_level: float
    duration_ms: int


class DailyForecastResponse(BaseModel):
    forecasts: list[DailyForecastPoint]
    model: ModelMetadata
    confidence_level: float
    duration_ms: int


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
