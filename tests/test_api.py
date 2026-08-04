from fastapi.testclient import TestClient

from rst_forecast.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "UP",
        "service": "rst-forecast",
        "version": "0.1.0",
    }
    assert response.headers["X-Request-ID"] == "test-request"


def test_monthly_forecast_rejects_short_history() -> None:
    response = client.post(
        "/api/v1/forecasts/monthly",
        json={
            "history": [],
            "future": [],
        },
    )

    assert response.status_code == 422
