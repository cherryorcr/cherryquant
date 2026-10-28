# M3 自然语言策略纵向切片

日期：2026-10-29

## 已完成

- `POST /v1/strategy-drafts` 接收中文交易想法，调用可替换 provider。
- 默认 mock provider 可离线生成三个候选；配置环境变量后可调用 OpenAI-compatible `chat/completions` provider。
- 模型响应必须通过 Pydantic `strategy-ir.v1` 校验，候选包含假设、数据需求、风险和支持状态。
- 编译器只允许白名单条件映射到 M1；部分支持的加权评分会展示但不能运行。
- 用户选择候选并勾选“收盘观察、下一交易日开盘尝试成交”后，才调用确定性引擎。
- 无构建依赖的网页工作台已覆盖描述、候选评审、确认、运行、摘要、K 线和逐日 DecisionTrace。
- API key 仅从服务端环境读取；前端、策略 metadata 和 health 响应不包含原始 key。

## 验证

```text
36 passed
ruff check: All checks passed
node --check apps/web/app.js: passed
```

端到端 mock 验证：生成候选 → 确认 `balanced-trend` → 在合成研究区间产生 1 笔交易，摘要和逐日 trace 均由同一次运行返回。

## 明确未完成

- 真实行情 provider、授权与数据质量报告。
- SQLite 持久化、策略/运行版本管理、重启恢复和受控比较。
- 多标的股票池、完整多因子评分和任意代码生成。
- 登录、用户隔离、资源限制、实盘或自动下单。

因此本切片可用于验证“自然语言 → 可核对候选 → 用户确认 → 确定性实验”的产品方向，但不能宣传为完整量化工作站或真实策略收益系统。
