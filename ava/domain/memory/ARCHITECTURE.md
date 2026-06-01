# Memory Module Architecture

## 目标

`ava/domain/memory/` 是会话记忆域模型。

当前版本遵循两条原则：

- 只围绕原始标准消息与其派生记忆工作
- 不再以旧式附件继承语义作为架构中心

## 目录

```text
ava/domain/memory/
  __init__.py
  session_memory.py
  education.py
  summaries.py
  message_blocks.py
  retriever.py
  projector.py
  types.py
```

## 分层

### 聚合根

- `SessionMemory`
- 对外提供统一记忆 API
- 组合教育连续性、摘要记忆、内容块分析缓存、检索器、投影器

### 内部状态/存储

- `EducationMemory`
- 保存教育场景连续性状态

- `SummaryMemory`
- 基于 `turn_records` 生成最近主题与派生摘要

- `MessageBlockMemoryStore`
- 缓存当前轮消息内容块的结构化分析结果

### 内部服务

- `MemoryRetriever`
- 为当前轮挑选最相关的记忆条目

- `MemoryProjector`
- 构建给模型可见的记忆投影

### 数据类型

- `RetrievedMemory`
- `MessageBlockMemoryEntry`
- `MemoryProjection`

## 关系图

```text
ConversationState
  -> SessionMemory

SessionMemory
  -> EducationMemory
  -> SummaryMemory
  -> MessageBlockMemoryStore
  -> MemoryRetriever
  -> MemoryProjector
```

## 运行顺序

### 1. 写入路径

```text
user_message / assistant_message
  -> ConversationState.upsert_realtime_user_turn()
  -> ConversationState.complete_realtime_turn()
  -> SessionMemory.update_education_state_from_strategy()
  -> SessionMemory.refresh_summaries(turn_records=...)
```

### 2. 记忆投影路径

```text
multi_turn_context_builder
  -> SessionMemory.build_projection(...)
  -> MemoryProjector.build(...)
  -> MemoryProjection
```

### 3. 记忆检索路径

```text
multi_turn_context_builder
  -> SessionMemory.retrieve_relevant_memories(...)
  -> MemoryRetriever.retrieve(...)
  -> list[RetrievedMemory]
```

## Source of Truth

- 会话原始记录：`ConversationState.turn_records`
- 教育连续性：`EducationMemory`
- 消息内容块分析缓存：`MessageBlockMemoryStore`
- 派生摘要：`SummaryMemory`

其中：

- `recent_topics`
- `context_summary`
- `multimodal_context_summary`

都属于派生记忆，不是独立真值源。

## 对外 API 规则

外部代码应只通过 `SessionMemory` 使用记忆能力，不直接改内部对象。

允许：

```python
state.memory.set_education_state_value(...)
state.memory.retrieve_relevant_memories(...)
state.memory.build_projection(...)
state.memory.remember_block_analysis(...)
```

避免：

```python
state.memory.education_state["key"] = value
state.memory.summary_memory.context_summary = "..."
state.memory.message_block_store._cache["..."] = {}
```

## 边界

`ava/domain/memory/` 负责：

- 会话内派生记忆
- 教育连续性状态
- 内容块分析缓存
- 模型可见记忆投影

`ava/domain/memory/` 不负责：

- 原始会话状态持久化
- UI 文案展示
- 路由决策
- 模型请求发送

