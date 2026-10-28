# CherryQuant M2 API

这是 M2 的最小 HTTP 层：它只负责解析规则卡片、加载演示数据、调用 M1 引擎和保存本次运行结果。指标、订单和解释不会在 API 层重新计算。

## 启动

在仓库根目录执行：

```bash
python -m pip install -e packages/engine
python -m pip install -e apps/api
uvicorn cherryquant_api.app:app --reload --port 8000
```

打开 `http://127.0.0.1:8000/docs` 可以查看 OpenAPI 文档。

## M2 端点

- `GET /health`
- `GET /v1/datasets/demo`
- `GET /v1/datasets/demo/bars`
- `POST /v1/strategies/validate`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/traces?date=YYYYMMDD`
- `GET /v1/runs/{run_id}/candles`

当前只提供内存中的 `demo-synthetic` 数据集和运行存储。关闭进程后运行记录会消失；SQLite 保存恢复属于 M3。未接入大模型。

