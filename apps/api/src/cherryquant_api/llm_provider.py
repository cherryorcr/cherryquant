from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any
from uuid import uuid4

from .config import load_llm_config
from .strategy_ir import DraftEnvelope, FactorSpec, StrategyCandidate, StrategyIR, ConditionSpec


class LLMProviderError(RuntimeError):
    """Safe-to-display provider failure without credentials or raw prompts."""


class _ProviderHTTPError(LLMProviderError):
    """Internal HTTP error that keeps the status for compatibility retries."""

    def __init__(self, status_code: int) -> None:
        super().__init__("语言模型服务暂时不可用，请检查地址、模型和密钥配置。")
        self.status_code = status_code


class StrategyProvider(ABC):
    name: str = "unknown"

    @abstractmethod
    def generate(self, prompt: str, context: dict[str, Any] | None = None) -> DraftEnvelope:
        raise NotImplementedError


def prompt_hash(prompt: str, context: dict[str, Any] | None) -> str:
    payload = json.dumps({"prompt": prompt, "context": context or {}}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _factor(
    factor_id: str,
    family: str,
    metric: str,
    params: dict[str, Any],
    explanation: str,
    direction: str = "neutral",
    warmup_period: int = 0,
) -> FactorSpec:
    return FactorSpec(
        id=factor_id,
        family=family,  # type: ignore[arg-type]
        metric=metric,
        params=params,
        direction=direction,  # type: ignore[arg-type]
        warmup_period=warmup_period,
        explanation=explanation,
    )
class MockStrategyProvider(StrategyProvider):
    name = "mock"

    def generate(self, prompt: str, context: dict[str, Any] | None = None) -> DraftEnvelope:
        factors = [
            # The local fixture has five research bars. Keep the mock draft
            # executable against that fixture so a new user can see a full
            # signal -> next-open fill -> exit flow without pretending the
            # tiny demo dataset is production research data.
            _factor("trend_sma_2", "trend", "close_vs_sma", {"period": 2}, "收盘价相对 2 日均线的位置", "positive", 2),
            _factor("trend_sma_3", "trend", "close_vs_sma", {"period": 3}, "收盘价相对 3 日均线的位置", "positive", 3),
            _factor("breakout_sma_2", "trend", "close_vs_sma", {"period": 2}, "短期趋势突破的近似条件", "positive", 2),
        ]
        candidates = [
            StrategyCandidate(
                id="conservative-trend",
                title="保守趋势确认",
                summary="同时要求收盘价站上 2 日和 3 日均线，作为演示用的趋势确认组合。",
                form="condition_set",
                assumptions=["先以单标的日线验证", "均线只使用当日收盘前可获得的数据"],
                data_requirements=["日线 OHLC", "至少 3 个交易日预热"],
                risk_notes=["信号较少，可能错过快速行情", "不代表未来盈利"],
                ir=StrategyIR(
                    objective="验证短期趋势确认后的买入与跌破退出",
                    factors=factors[:2],
                    entry=ConditionSpec(type="all_of", conditions=[ConditionSpec(type="close_above_sma", period=2, factor_id="trend_sma_2"), ConditionSpec(type="close_above_sma", period=3, factor_id="trend_sma_3")]),
                    exit=ConditionSpec(type="close_below_sma", period=2, factor_id="trend_sma_2"),
                ),
            ),
            StrategyCandidate(
                id="balanced-trend",
                title="平衡趋势跟随",
                summary="使用 2 日均线作为趋势过滤，信号数量和确认程度较为平衡。",
                form="condition_set",
                assumptions=["入场在收盘确认后，下一交易日开盘尝试", "使用固定仓位比例"],
                data_requirements=["日线 OHLC", "至少 2 个交易日预热"],
                risk_notes=["横盘市场可能反复进出", "费用和滑点会影响结果"],
                ir=StrategyIR(
                    objective="验证简单趋势跟随规则",
                    factors=factors[:1],
                    entry=ConditionSpec(type="close_above_sma", period=2, factor_id="trend_sma_2"),
                    exit=ConditionSpec(type="close_below_sma", period=2, factor_id="trend_sma_2"),
                ),
            ),
            StrategyCandidate(
                id="loose-breakout-score",
                title="宽松短期评分（待扩展）",
                summary="把短期突破、趋势和量价因子合成为评分，再按阈值筛选。",
                form="weighted_score",
                assumptions=["需要横截面股票池和成交量因子", "当前演示引擎尚未执行加权评分"],
                data_requirements=["日线 OHLCV", "股票池", "横截面排名"],
                risk_notes=["评分权重会显著影响结果", "需要防止反复试参造成过拟合"],
                support="partial",
                ir=StrategyIR(
                    form="weighted_score",
                    objective="探索多因子评分策略",
                    factors=[*factors, _factor("volume_ratio", "volume", "volume_ratio", {"period": 2}, "成交量相对 2 日均量", "positive", 2)],
                    entry=ConditionSpec(type="weighted_score", threshold="0.6"),
                    exit=ConditionSpec(type="close_below_sma", period=2, factor_id="trend_sma_2"),
                ),
            ),
        ]
        return DraftEnvelope(
            request_id=uuid4().hex,
            user_intent=prompt,
            candidates=candidates,
            clarifications=["当前演示先将‘股票池’和‘放量’标记为待扩展因子。"],
            metadata={"provider": self.name, "model": "mock", "schema_version": "strategy-ir.v1", "prompt_hash": prompt_hash(prompt, context)},
        )


class OpenAICompatibleStrategyProvider(StrategyProvider):
    name = "jackbuddy"

    def __init__(self, base_url: str, api_key: str, model: str | None = None, timeout: float = 45.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read(2_000_000).decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise _ProviderHTTPError(exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LLMProviderError("语言模型服务暂时不可用，请检查地址、模型和密钥配置。") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("语言模型服务返回了无法解析的响应。") from exc
        if not isinstance(parsed, dict):
            raise LLMProviderError("语言模型服务返回格式不受支持。")
        return parsed

    def _resolve_model(self) -> str:
        if self.model:
            return self.model
        models = self._request("models")
        items = models.get("data", [])
        if not items or not isinstance(items[0], dict) or not items[0].get("id"):
            raise LLMProviderError("未配置模型名称，且服务端没有返回可用模型。")
        return str(items[0]["id"])

    def generate(self, prompt: str, context: dict[str, Any] | None = None) -> DraftEnvelope:
        model = self._resolve_model()
        system = """你是 CherryQuant 的策略解释器。只输出一个 DraftEnvelope JSON，不输出 Markdown、代码或收益承诺。
顶层字段为 candidates（1-3 个）、clarifications（数组，可为空）和 metadata（对象，可为空）；request_id、user_intent 可以省略。
每个 candidate 必须包含 id、title、summary、form、assumptions、data_requirements、risk_notes、support 和 ir。
ir 必须包含 objective、factors、entry、exit；可选 sizing、execution、evaluation。
每个 factor 至少包含 id、family、kind、metric、params、direction、warmup_period、explanation；均线因子使用 metric=close_vs_sma 和 params.period。
生成最多 3 个候选：conservative、standard、loose；每个候选必须列出 assumptions、data_requirements、risk_notes。
只能使用以下可执行条件：close_above_sma、close_below_sma、close_crosses_above_sma、close_crosses_below_sma、all_of。
条件引用的 factor_id 必须在 factors 中存在，且因子周期与条件周期一致。
可以提出 weighted_score 作为 support=partial 的待扩展候选，但不得把未支持能力伪装成可执行。所有日期时点遵守收盘观察、下一交易日开盘尝试。未知信息写入 clarifications，不要猜测。"""
        user = json.dumps({"request": prompt, "context": context or {}, "required_schema": "strategy-ir.v1"}, ensure_ascii=False)
        payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._request("chat/completions", payload)
        except _ProviderHTTPError as exc:
            # Some OpenAI-compatible gateways reject response_format even
            # though they support chat/completions. Retry only for validation
            # errors; auth, rate-limit and server failures should surface.
            if exc.status_code not in {400, 404, 422}:
                raise
            payload.pop("response_format", None)
            response = self._request("chat/completions", payload)
        try:
            content = response["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
            if not isinstance(content, str):
                raise ValueError("content is not text")
            parsed = _parse_json_content(content)
            if not isinstance(parsed, dict):
                raise ValueError("strategy draft must be a JSON object")
            # The model is asked for the full envelope, but gateways often
            # return only the candidate payload. Fill only transport-owned
            # fields; candidates and IR remain fully schema-validated below.
            parsed.setdefault("request_id", uuid4().hex)
            parsed.setdefault("user_intent", prompt)
            envelope = DraftEnvelope.model_validate(parsed)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError("语言模型返回的策略草稿未通过结构化校验。") from exc
        return envelope.model_copy(
            update={
                "request_id": uuid4().hex,
                "user_intent": prompt,
                "metadata": {"provider": self.name, "model": model, "schema_version": "strategy-ir.v1", "prompt_hash": prompt_hash(prompt, context)},
            }
        )


def _parse_json_content(content: str) -> Any:
    """Parse strict JSON while tolerating common model wrapper text.

    Providers sometimes ignore the JSON response format and return a fenced
    object or a short preamble. We only extract the outermost object and still
    rely on Pydantic for the actual schema and unknown-field checks.
    """
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def get_strategy_provider() -> StrategyProvider:
    config = load_llm_config()
    if config.effective_provider == "mock":
        return MockStrategyProvider()
    return OpenAICompatibleStrategyProvider(
        config.base_url,
        config.api_key,
        config.model,
        timeout=config.timeout_seconds,
    )