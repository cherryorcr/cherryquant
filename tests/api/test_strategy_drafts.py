from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import ValidationError

from cherryquant_api.app import create_app
from cherryquant_api.llm_provider import OpenAICompatibleStrategyProvider, _ProviderHTTPError, _parse_json_content
from cherryquant_api.strategy_ir import ConditionSpec, FactorSpec, StrategyCandidate, StrategyIR


client = TestClient(create_app())


def test_generate_strategy_draft_returns_multiple_candidates() -> None:
    response = client.post(
        "/v1/strategy-drafts",
        json={"prompt": "找出趋势向上的股票，突破均线后买入，跌破均线卖出。"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "mock"
    assert len(body["draft"]["candidates"]) == 3
    assert body["draft"]["metadata"]["prompt_hash"]
    assert body["draft"]["candidates"][0]["form"] == "condition_set"
    assert body["draft"]["candidates"][2]["support"] == "partial"


def test_confirm_supported_candidate_runs_engine() -> None:
    draft = client.post("/v1/strategy-drafts", json={"prompt": "用均线趋势做一个简单策略"}).json()
    draft_id = draft["draft_id"]
    response = client.post(
        f"/v1/strategy-drafts/{draft_id}/confirm",
        json={"candidate_id": "balanced-trend"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["compiled_strategy"]["confirmed"] is True
    assert body["run_id"]
    assert body["result"]["summary"]["status"] in {"COMPLETED", "NO_TRADES"}


def test_confirm_partial_candidate_is_rejected() -> None:
    draft = client.post("/v1/strategy-drafts", json={"prompt": "用量价和趋势做多因子评分"}).json()
    response = client.post(
        f"/v1/strategy-drafts/{draft['draft_id']}/confirm",
        json={"candidate_id": "loose-breakout-score"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]


def test_short_prompt_is_rejected() -> None:
    response = client.post("/v1/strategy-drafts", json={"prompt": "买入"})
    assert response.status_code == 422


def test_demo_draft_rejects_symbol_outside_fixed_fixture() -> None:
    response = client.post(
        "/v1/strategy-drafts",
        json={"prompt": "验证一条均线趋势规则", "symbol": "000001.SZ"},
    )
    assert response.status_code == 422


def _minimal_ir(**overrides: object) -> StrategyIR:
    values: dict[str, object] = {
        "objective": "test",
        "factors": [
            FactorSpec(
                id="sma",
                family="trend",
                metric="close_vs_sma",
                params={"period": 20},
                explanation="test factor",
            )
        ],
        "entry": ConditionSpec(type="close_above_sma", period=20, factor_id="sma"),
        "exit": ConditionSpec(type="close_below_sma", period=20, factor_id="sma"),
    }
    values.update(overrides)
    return StrategyIR(**values)


def test_ir_rejects_unknown_factor_reference() -> None:
    try:
        _minimal_ir(entry=ConditionSpec(type="close_above_sma", period=20, factor_id="missing"))
    except ValidationError as exc:
        assert "unknown factor" in str(exc)
    else:  # pragma: no cover - defensive assertion for a validation contract
        raise AssertionError("unknown factor reference should be rejected")


def test_ir_rejects_duplicate_factor_ids() -> None:
    factor = FactorSpec(
        id="sma",
        family="trend",
        metric="close_vs_sma",
        params={"period": 20},
        explanation="test factor",
    )
    try:
        _minimal_ir(factors=[factor, factor])
    except ValidationError as exc:
        assert "unique ids" in str(exc)
    else:  # pragma: no cover - defensive assertion for a validation contract
        raise AssertionError("duplicate factor ids should be rejected")


def test_candidate_rejects_form_mismatch() -> None:
    try:
        StrategyCandidate(
            id="mismatch",
            title="Mismatch",
            summary="test",
            form="weighted_score",
            ir=_minimal_ir(),
        )
    except ValidationError as exc:
        assert "form must match" in str(exc)
    else:  # pragma: no cover - defensive assertion for a validation contract
        raise AssertionError("candidate/IR form mismatch should be rejected")


def test_provider_json_parser_accepts_fenced_or_prefixed_json() -> None:
    payload = '{"request_id":"r","user_intent":"test","candidates":[]}'
    assert _parse_json_content(f"Here is the draft:\n```json\n{payload}\n```") == {
        "request_id": "r",
        "user_intent": "test",
        "candidates": [],
    }


def test_provider_retries_without_response_format_when_gateway_rejects_it(monkeypatch) -> None:
    provider = OpenAICompatibleStrategyProvider("https://example.test/v1", "test-key", model="test-model")
    calls: list[dict[str, object]] = []
    response = {
        "choices": [
            {
                "message": {
                    "content": """{
                        \"candidates\": [{
                            \"id\": \"candidate\",
                            \"title\": \"Test\",
                            \"summary\": \"Test candidate\",
                            \"form\": \"condition_set\",
                            \"ir\": {
                                \"objective\": \"test\",
                                \"factors\": [{
                                    \"id\": \"sma\", \"family\": \"trend\", \"metric\": \"close_vs_sma\",
                                    \"params\": {\"period\": 20}, \"explanation\": \"test\"
                                }],
                                \"entry\": {\"type\": \"close_above_sma\", \"period\": 20, \"factor_id\": \"sma\"},
                                \"exit\": {\"type\": \"close_below_sma\", \"period\": 20, \"factor_id\": \"sma\"}
                            }
                        }]
                    }"""
                }
            }
        ]
    }

    def fake_request(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        assert path == "chat/completions"
        assert payload is not None
        calls.append(payload.copy())
        if len(calls) == 1:
            raise _ProviderHTTPError(400)
        return response

    monkeypatch.setattr(provider, "_request", fake_request)
    envelope = provider.generate("validate trend with a 20 day SMA")
    assert envelope.candidates[0].id == "candidate"
    assert envelope.request_id
    assert envelope.user_intent == "validate trend with a 20 day SMA"
    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]
