# CherryQuant strategy API

这是 CherryQuant 的最小 HTTP 层：它负责自然语言策略草稿、结构化校验、候选确认、调用 M1 确定性引擎，并在进程内保存本次运行结果。指标、订单和解释不会在 API 层重新计算。

## 启动

在仓库根目录执行：

```bash
python -m pip install -e packages/engine
python -m pip install -e apps/api
uvicorn cherryquant_api.app:app --reload --port 8000
```

打开 `http://127.0.0.1:8000/docs` 可以查看 OpenAPI 文档。

## 可选的大模型配置

模型只负责把用户描述转换为待确认的 `strategy-ir.v1` 草稿；它不能直接运行交易规则。完整链路是：

```text
自然语言 → 模型草稿 → Pydantic 结构化校验 → 用户选择/确认 → 确定性 M1 引擎
```

在启动 uvicorn 的同一个终端设置环境变量（不要把真实密钥提交到 Git）：

```powershell
$env:CHERRYQUANT_LLM_PROVIDER = "auto"
$env:JACKBUDDY_BASE_URL = "https://jackbuddy.xin/v1"
$env:JACKBUDDY_API_KEY = "在本机注入，不要写入仓库"
# 可选：$env:JACKBUDDY_MODEL = "服务端模型名"
uvicorn cherryquant_api.app:app --reload --port 8000
```

没有 `JACKBUDDY_API_KEY` 时自动使用本地 mock provider，因此离线开发和测试不需要外网。`GET /health` 只返回 provider、地址、模型和是否配置密钥的布尔值，不返回密钥本身。

## 端点

- `GET /health`
- `GET /v1/datasets/demo`
- `GET /v1/datasets/demo/bars`
- `POST /v1/strategies/validate`
- `POST /v1/strategy-drafts`
- `GET /v1/strategy-drafts/{draft_id}`
- `POST /v1/strategy-drafts/{draft_id}/confirm`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/traces?date=YYYYMMDD`
- `GET /v1/runs/{run_id}/candles`

当前只提供内存中的 `demo-synthetic` 数据集和运行存储。关闭进程后运行记录会消失；SQLite 保存恢复属于 M3。兼容 OpenAI `chat/completions` 的 provider 可通过环境变量启用；模型响应必须通过 `strategy-ir.v1` 校验，当前只执行有限的均线条件组合。真实行情、持久化和实盘仍未接入。

