# Context Engine（兼容层）

`ava.context_engine` 已降为兼容层。

## 当前状态

- 这里不再承载真实实现
- 这里只保留旧导入路径，统一转发到 `ava.multi_turn_context_builder`

## 推荐新入口

- `ava.multi_turn_context_builder.compiler`
- `ava.multi_turn_context_builder.types`

## 兼容目的

- 避免一次性改动所有历史 import
- 允许业务代码逐步迁移到四层正式模块
