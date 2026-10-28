# CherryQuant natural-language strategy workspace

这是一个无构建依赖的自然语言策略工作台。用户输入交易想法后，页面请求 API 生成结构化候选，查看候选的条件、假设和风险，选择后确认并运行；结果区展示同一次确定性运行生成的摘要、图表和逐日 DecisionTrace。

启动 API 后，在另一个终端执行：

```bash
python -m http.server 5173 --directory apps/web
```

然后打开 <http://127.0.0.1:5173>。如果 API 不在 `http://127.0.0.1:8000`，可通过 `?api=http://host:port` 指定。

页面当前仍是本地纵向闭环，不包含登录、持久化、真实行情或自动下单。语言模型 provider 由 API 侧配置；未配置密钥时使用 mock provider，浏览器不会接触任何密钥。

