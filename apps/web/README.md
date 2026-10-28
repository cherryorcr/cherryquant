# CherryQuant M2 Web Demo

这是一个无构建依赖的 M2 规则卡片与运行结果演示页。它只调用 M2 API，不在浏览器中重算指标或收益。

启动 API 后，在另一个终端执行：

```bash
python -m http.server 5173 --directory apps/web
```

然后打开 <http://127.0.0.1:5173>。如果 API 不在 `http://127.0.0.1:8000`，可通过 `?api=http://host:port` 指定。

当前页面只用于 M2 纵向验证，不是最终视觉设计，也不包含登录、持久化或大模型能力。

