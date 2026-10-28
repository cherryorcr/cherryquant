# M1 完成记录

日期：2026-10-29

## 已完成

- 标准库实现的 `Bar`、`DataSnapshot`、`StrategySpec`、`ExperimentConfig`、`RunResult` 等核心模型。
- 日期、代码、OHLC、成交量、区间和内容指纹校验。
- `CloseAboveSMA`、`CloseBelowSMA`、交叉条件和 `AllOf` 条件组合。
- 日线收盘观察、下一交易日开盘尝试成交。
- 单标的、只做多、手数、现金、佣金、最低佣金、卖出印花税。
- 停牌、缺开盘价、涨停买入、跌停卖出、现金不足、手数不足、无下一交易日等未成交原因。
- `condition_evaluation → signal → order_attempt → fill/not_filled` 的逐日 `DecisionTrace`。
- 已实现收益、期末持仓浮盈、无交易、失败和完成状态的区分。
- 从 `quant` 日线字段形状改写出的轻量 `normalize_bar_record` 适配器。
- 14 个 pytest 测试，覆盖确定性、预热不足、下一日成交、无交易、末日信号、涨停阻断、同日不重入和迁移字段。
- `scripts/run_m1_demo.py` 可在不启动 UI 的情况下运行一条完整实验并打印摘要与关键轨迹。

## 验证结果

```text
python -m pytest
14 passed
```

合成黄金样例可复现同一份摘要、交易和逐日解释。它只证明引擎实现和事件记录，不证明任何真实策略有效。

## 尚未完成

- M2 前端、K 线图和解释面板。
- HTTP/API 层、保存恢复和 SQLite 索引。
- 真实行情 provider、授权和数据质量报告。
- 更完整的 A 股公司行为、复权和历史交易限制数据。
- 研究/保留区间的接口级泄露防护和 `ExposureLog`。

