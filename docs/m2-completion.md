# M2 当前完成记录

日期：2026-10-29

## 已完成

- FastAPI M2 API，HTTP 层只负责输入解析、错误映射和内存运行存储。
- `GET /health`、演示数据集元数据和可见 K 线接口。
- `POST /v1/strategies/validate`：规则卡片校验和可读确认信息。
- `POST /v1/runs`：确认规则后调用 M1 确定性引擎。
- `GET /v1/runs/{run_id}`、`traces`、`candles`：读取同一次运行的结果，不重新计算。
- 内存运行存储，关闭进程后记录消失；SQLite 保存恢复留到 M3。
- 研究区间/保留区间隔离：M2 演示接口只暴露研究区间，保留区间明确标为锁定。
- 无构建依赖的规则卡片页面，能够提交规则、显示摘要、SVG 收盘线和逐日 DecisionTrace。
- CORS 仅允许本地演示页面来源；未接入大模型。

## 验证

```text
ruff: All checks passed
pytest: 21 passed
```

当前 API 测试使用 FastAPI `TestClient`，环境会显示一条 Starlette 关于未来 `httpx2` 的弃用提示，但不影响测试结果。

## 尚未完成

- React/Vite 正式前端和最终视觉设计。
- SQLite 持久化、策略/运行版本管理和重启恢复。
- 真实行情数据 provider、授权和数据质量报告。
- M3 的 ExposureLog、受控比较和导出。
- 大模型自然语言草稿辅助；如果加入，只能生成待确认的结构化规则。

