# 0003：从 quant 项目迁移 K 线能力的边界

日期：2026-10-29

## 审计结论

`D:\Aprojects\quant\limitup_ai` 是一个面向 A 股涨停池研究的较大型项目，包含多数据源、Parquet、特征、模型和多标的回测逻辑。它不是 CherryQuant M1 的可直接基线。

## 采用的内容

- 借鉴其日线字段归一化思路：代码、日期、开高低收、前收和成交量。
- 借鉴 `sh.600000`、`600000.SH` 等代码格式统一为 `600000.SH`。
- 借鉴其质量优先原则：日期规范、OHLC 校验、原始数据不可静默覆盖、外部数据通过适配层进入。
- 将一个极小的 Baostock 形状样例保存为 `fixtures/quant_daily_bar_sample.json`，仅用于适配器测试，不作为行情数据集或收益证据。

## 不迁移的内容

- `limitup_ai` 的完整 provider、特征、模型和多标的 backtest。
- 旧项目的策略和成交语义；CherryQuant 必须遵守自己的单标的、日线、只做多、下一交易日开盘语义。
- `data/raw`、`data/processed` 下的 Parquet。旧项目根目录没有明确许可证，不能假定原始数据可以复制和再分发。
- Tushare/AkShare/BaoStock 网络调用和任何凭证。

## 后续接入规则

真实数据接入时，先实现只读 `DataProvider`/Parquet adapter，再把数据转成 CherryQuant `Bar` 和 `DataSnapshot`，记录来源、价格口径、内容指纹和授权说明；不要让 UI 或引擎直接调用外部数据源。

