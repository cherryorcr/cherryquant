# CherryQuant

CherryQuant 面向有交易经验但不会编程的普通 A 股投资者，帮助用户把自己的交易规则表达出来，用可复现的历史实验检查规则，查看每个决策为什么发生，再创建版本并进行受控比较。

## 当前状态

仓库已完成 M0，并有一个不依赖 UI、网络或外部数据源的 M1 确定性实验引擎。当前仍没有界面、真实行情接入或实盘能力；任何合成数据收益都不能被视为已验证的策略表现。

## MVP 闭环

选择数据 → 用有限条件卡片搭建并确认规则 → 运行确定性历史实验 → 在 K 线和逐日记录中解释交易/无交易/未成交 → 复制并修改规则 → 在相同条件下比较 → 保存、恢复和导出摘要。

首版默认范围：单标的、日线、只做多、不加杠杆、规则由用户确认后执行。默认范围是为了快速验证闭环，不是投资建议，也不是最终产品边界。

首版暂不做全市场选股、多标的组合、任意代码/自由 DAG、机器学习、实时舆情、自动调参、多券商接入或自动下单。

## 目录

```text
apps/web/             前端（M2 建立）
apps/api/             HTTP/API 层（M2 建立）
packages/engine/      M1 规则、指标、事件和成交模拟
contracts/            跨层数据契约与示例
fixtures/             可人工核对的合成数据和黄金样本
tests/                单元、契约和端到端测试
docs/handoff/         交接文档
docs/decisions/       可追溯的产品与工程决策
```

## 开发顺序

1. M0：仓库、契约、范围和交易假设。
2. M1：不依赖 UI 的可核验引擎与合成数据。
3. M2：数据选择、规则卡片、运行、K 线和逐日解释。
4. M3：版本、修改理由、受控比较、保存恢复和检验区间记录。
5. M4：小范围受控试用，区分软件理解问题、数据问题和策略问题。

每个阶段必须有可复核的完成门槛；“页面看起来完成”不等于计算可信。

## 版本管理约定

- `main`：可复现、可演示的稳定分支。
- `dev`：阶段集成分支；完成一个纵向小闭环后再合并到 `main`。
- `feature/<topic>`：短生命周期功能分支，单一目的，完成后通过 Pull Request 合并。
- 提交信息使用动词开头，例如 `Add deterministic run fixture`、`Clarify T+1 semantics`。
- 一个提交只表达一个可解释变化；契约变化与实现变化尽量分开。

## 质量底线

- 同一规则、数据快照、实验配置和引擎版本必须产生确定性结果。
- 信号时点、订单尝试时点、成交/未成交原因必须分开记录。
- 无交易、策略亏损、运行失败和数据不足不能混成“收益为 0”。
- 图表、交易清单和解释必须读取同一次运行记录，不能各自重算。
- 研究区间和保留检验区间必须在运行前固定；未解锁区间不得从接口、图表、比较或导出泄露。

## 文档入口

- [MVP 交接文档](docs/handoff/cherryquant-mvp-handoff-2026-10-29.md)
- [MVP 范围决策](docs/decisions/0001-mvp-scope.md)
- [交易语义决策](docs/decisions/0002-trading-semantics.md)
- [开发计划与节奏](docs/development-plan.md)

## 本地开发

### 运行 M1 测试

```bash
python -m pip install -e packages/engine
python -m pytest
```

### 在 Python 中运行一次实验

```python
from decimal import Decimal
from pathlib import Path

from cherryquant_engine import (
    CloseAboveSMA,
    CloseBelowSMA,
    DataSnapshot,
    ExperimentConfig,
    StrategySpec,
    bars_from_records,
    read_json_records,
    run_experiment,
)

records = read_json_records(Path("fixtures/synthetic_daily.json"))
snapshot = DataSnapshot(
    source="cherryquant.synthetic",
    frequency="1d",
    symbol="600000.SH",
    bars=bars_from_records(records),
)
strategy = StrategySpec(
    version_id="demo-v1",
    entry_condition=CloseAboveSMA(2),
    exit_condition=CloseBelowSMA(2),
    position_fraction=Decimal("0.5"),
)
result = run_experiment(snapshot, strategy, ExperimentConfig())
print(result.to_dict()["summary"])
```

也可以直接运行仓库里的演示脚本：

```bash
python scripts/run_m1_demo.py
```

测试命令使用仓库根目录的 `pyproject.toml`，会自动把 `packages/engine/src` 加入测试路径。M1 当前使用 JSON 合成样本；真实 Parquet/Provider 接入留到后续数据层，不把旧项目的原始文件或网络凭证带入仓库。

