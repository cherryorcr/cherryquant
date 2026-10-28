# 决策 0004：自然语言策略草稿与确定性执行边界

日期：2026-10-29
状态：已实现最小纵向切片，后续可扩展

## 背景

CherryQuant 的目标不是让模型直接替用户下单，也不是把自然语言转换成任意 Python。用户需要的是：用自己的话描述交易想法，看到几种不同的结构化解释，检查假设和风险，再选择一条规则交给可复核的实验引擎。

## 决策

自然语言功能采用四段式边界：

```text
自然语言输入
  → LLM provider 生成 DraftEnvelope / strategy-ir.v1
  → Pydantic 结构化校验 + 编译器能力检查
  → 用户选择、确认运行时点和参数
  → M1 确定性引擎生成 Run / DecisionTrace
```

- provider 可替换。没有密钥时使用本地 mock provider，离线开发不依赖网络。
- provider 只生成最多三个候选草稿；候选必须声明 assumptions、data_requirements 和 risk_notes。
- 未被当前引擎支持的形式（例如多因子加权评分）可以展示为 `partial`，但不能确认运行。
- 编译器只把白名单条件映射到 M1 引擎；未知条件、悬空因子引用、因子参数与条件不一致时拒绝运行。
- 用户确认前不运行实验；模型不能直接调用引擎，也不能生成收益承诺。
- 图表和逐日说明只读取同一次运行的确定性 `DecisionTrace`，不让模型事后编造解释。

## 配置和凭证

- `JACKBUDDY_BASE_URL`、`JACKBUDDY_API_KEY`、`JACKBUDDY_MODEL` 只从启动 API 的进程环境读取。
- `.env.example` 只保留空占位符；真实 key 不进入 Git、前端 bundle、策略 metadata 或 `/health` 响应。
- `/health` 只提供 provider、地址、模型和 `api_key_configured` 布尔值，便于检查配置而不泄露凭证。
- 如果 key 曾经在聊天、日志或截图中暴露，应在 provider 侧轮换；本仓库不保存该 key。

## 当前范围

M3 纵向切片只支持单标的日线和少量均线条件。真实行情、横截面股票池、完整多因子评分、持久化、用户隔离、实盘和自动下单不属于当前实现；新增能力必须先扩展 IR、编译器和引擎测试，不能仅修改提示词让 UI 声称“可运行”。
