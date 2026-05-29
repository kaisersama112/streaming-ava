# Routing（兼容层）

`ava.routing` 已降为兼容层。

## 当前状态

- 这里不再承载真实路由实现
- 这里只保留旧导入路径，统一转发到 `ava.router_selector`

## 推荐新入口

- `ava.router_selector.schema`
- `ava.router_selector.policy`
- `ava.router_selector.request`
- `ava.router_selector.service`

## 迁移建议

新代码不要再直接依赖 `ava.routing`。
如无历史兼容需求，应直接从 `ava.router_selector` 导入。
