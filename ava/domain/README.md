# Domain Layer

`ava/domain/` 放系统的核心状态模型、上下文模型、路由 schema 和策略模型。

这一层的重点是“表达系统是什么”，而不是“执行一次 turn 要怎么做”。

## 当前职责

- 定义输入与上下文快照
- 定义路由决策模型
- 定义会话状态聚合
- 定义策略与 prompt 选择相关的结构化模型

## 当前子模块

- `context/`
  - `TurnInput`
  - `MediaArtifact`
  - `ContextSnapshot`
  - `assemble_context()`
- `routing/`
  - `RouteDecision`
  - 置信度策略与 policy
- `session/`
  - `ConversationState`
- `strategy/`
  - `PromptSelection`
  - `ResolvedPromptSpec`
  - `BranchStrategy`

## 设计边界

这一层负责：

- 保存“当前会话有哪些事实、turn records、education_state”
- 表达“当前路由决策长什么样”
- 表达“编排层最终选中的策略长什么样”

这一层不负责：

- 调 LLM / TTS / ASR
- 直接读取 Prompt markdown 文件
- 组织一轮 turn 的执行顺序

## 关键对象

### Context

- [context/media.py](/app/streaming-ava/ava/domain/context/media.py)
- [context/models.py](/app/streaming-ava/ava/domain/context/models.py)
- [context/assembler.py](/app/streaming-ava/ava/domain/context/assembler.py)

### Routing

- [routing/schema.py](/app/streaming-ava/ava/domain/routing/schema.py)
- [routing/policy.py](/app/streaming-ava/ava/domain/routing/policy.py)

### Session

- [session/state.py](/app/streaming-ava/ava/domain/session/state.py)

### Strategy

- [strategy/models.py](/app/streaming-ava/ava/domain/strategy/models.py)

## 与其他层关系

- 被 [ava/application/README.md](/app/streaming-ava/ava/application/README.md) 消费
- 不直接依赖 `ava/infrastructure/`
- 是整个系统文档里判断“真实模型边界”的基准层
