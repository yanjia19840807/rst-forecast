from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from rst_forecast.main import create_app
from rst_forecast.settings import get_settings


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RST_FORECAST_API_KEY", "test-forecast-key")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client
    get_settings.cache_clear()


def test_health_allows_missing_api_key(authed_client: TestClient) -> None:
    response = authed_client.get("/health")

    assert response.status_code == 200


def test_forecast_rejects_missing_api_key(authed_client: TestClient) -> None:
    response = authed_client.post(
        "/api/v1/forecasts/monthly",
        json={"history": [], "future": []},
    )

    assert response.status_code == 401
    assert response.json()["type"] == "unauthorized"


def test_forecast_rejects_wrong_api_key(authed_client: TestClient) -> None:
    response = authed_client.post(
        "/api/v1/forecasts/monthly",
        headers={"X-API-Key": "wrong"},
        json={"history": [], "future": []},
    )

    assert response.status_code == 401


def test_forecast_accepts_valid_api_key(authed_client: TestClient) -> None:
    response = authed_client.post(
        "/api/v1/forecasts/monthly",
        headers={"X-API-Key": "test-forecast-key"},
        json={"history": [], "future": []},
    )

    # Auth passed; empty history is a validation / input error.
    assert response.status_code == 422
