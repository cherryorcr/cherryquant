from __future__ import annotations

from fastapi.testclient import TestClient

from cherryquant_api.app import app


client = TestClient(app)


def strategy_payload(*, confirmed: bool = True) -> dict[str, object]:
    return {
        "version_id": "api-v1",
        "entry_condition": {"type": "close_above_sma", "period": 2},
        "exit_condition": {"type": "close_below_sma", "period": 2},
        "position_fraction": 0.5,
        "lot_size": 100,
        "confirmed": confirmed,
    }


def test_health_and_demo_dataset() -> None:
    health = client.get("/health")
    dataset = client.get("/v1/datasets/demo")
    assert health.status_code == 200
    assert health.json()["engine"] == "m1.0"
    assert dataset.status_code == 200
    assert dataset.json()["dataset_id"] == "demo-synthetic"
    assert dataset.json()["bar_count"] == 5
    assert dataset.json()["holdout_locked"] is True


def test_validate_strategy_returns_readable_card() -> None:
    response = client.post("/v1/strategies/validate", json=strategy_payload(confirmed=False))
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["confirmation_required"] is True
    assert body["readable"]["execute"] == "下一交易日开盘尝试成交"


def test_run_then_read_result_traces_and_candles() -> None:
    response = client.post("/v1/runs", json={"dataset_id": "demo-synthetic", "strategy": strategy_payload()})
    assert response.status_code == 200
    body = response.json()
    run_id = body["run_id"]
    assert body["result"]["summary"]["trade_count"] == 1

    stored = client.get(f"/v1/runs/{run_id}")
    traces = client.get(f"/v1/runs/{run_id}/traces", params={"date": "20260107"})
    candles = client.get(f"/v1/runs/{run_id}/candles")
    assert stored.status_code == 200
    assert traces.status_code == 200
    assert len(traces.json()["traces"]) == 1
    assert traces.json()["traces"][0]["order_attempt"]["status"] == "FILLED"
    assert candles.status_code == 200
    assert len(candles.json()["bars"]) == 5


def test_unconfirmed_strategy_cannot_run() -> None:
    response = client.post("/v1/runs", json={"strategy": strategy_payload(confirmed=False)})
    assert response.status_code == 409
    assert "confirmed" in response.json()["detail"]


def test_invalid_condition_period_is_rejected() -> None:
    payload = strategy_payload()
    payload["entry_condition"] = {"type": "close_above_sma", "period": 0}
    response = client.post("/v1/strategies/validate", json=payload)
    assert response.status_code == 422


def test_unknown_run_is_not_recomputed() -> None:
    response = client.get("/v1/runs/does-not-exist")
    assert response.status_code == 404

