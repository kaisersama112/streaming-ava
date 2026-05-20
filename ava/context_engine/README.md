# Context Compiler

> 详细分层图与调用顺序见 `ava/context_engine/ARCHITECTURE.md:1`

`ava.context_engine` 现在采用**单主入口、显式分层**的结构。

## 主入口

- 根包只暴露 `ContextCompiler`
- 使用方式：

```python
from ava.context_engine import ContextCompiler
```

其余内容一律从明确子模块导入，例如：

- `ava.context_engine.types`
- `ava.context_engine.input`
- `ava.context_engine.continuity`

这样做的目标是：

- 避免根包重新变成“大杂烩工具箱”
- 让依赖方向更清晰
- 降低后续继续拆分和替换内部实现时的影响面

## 分层

### 1. Public API Layer

对外唯一主入口：

- `ava/context_engine/__init__.py`
  - `ContextCompiler`

职责：

- 给业务层一个稳定入口
- 不暴露内部拼装细节

---

### 2. Compiler Core Layer

核心实现位于：

- `ava/context_engine/compiler.py`

核心类：

- `ContextCompiler`
- `ContextSnapshotBuilder`
- `RuntimePayloadCompiler`
- `MessageCompiler`

职责划分：

- `ContextCompiler`
  - 总协调器
  - 统一调度 input → snapshot → runtime → instructions → messages
- `ContextSnapshotBuilder`
  - 构建单轮上下文快照
  - 负责历史裁剪、附件继承、memory projection、retrieved memories
- `RuntimePayloadCompiler`
  - 生成 router / responder 的 runtime JSON
- `MessageCompiler`
  - 生成最终发给模型的 messages

---

### 3. Instruction Layer

位于：

- `ava/context_engine/instructions.py`
- `ava/context_engine/skills.py`

职责：

- 把 base system prompt
- active skills
- runtime context

编译成高优先级 `instructions`

这里体现的是：

> system / instructions 不是一段固定 prompt，而是 Context Compiler 编译产物

---

### 4. Context Data Layer

位于：

- `ava/context_engine/types.py`

核心数据对象：

- `ContextSnapshot`
- `SnapshotCompileOptions`
- `CompiledContextEnvelope`
- `CompiledInstructions`

职责：

- 定义上下文编译过程中的标准中间产物
- 让 router、responder、legacy bridge 共用同一数据结构

---

### 5. Input / Memory / Continuity Support Layer

位于：

- `ava/context_engine/input.py`
- `ava/context_engine/memory.py`
- `ava/context_engine/continuity.py`

职责：

- `input.py`
  - 原始输入标准化为 `TurnInput`
- `memory.py`
  - 生成 memory projection
  - 召回 relevant memories
- `continuity.py`
  - 判断是否继承参考附件
  - 判断是否隔离当前附件上下文
  - 选择 router model

这些模块是**支持层**，不是主入口。

---

### 6. Legacy Removal Policy

旧入口已经移除，不再保留桥接层。

这意味着以下路径不应再存在或被引用：

- `ava/context_engine/snapshot.py`
- `ava/context_engine/runtime.py`
- `ava/context_engine/messages.py`
- `ava/core/context/*`
- `ava/capabilities/prompt/runtime_context.py`
- `ava/pipeline/generation/common.py`
- `ava/capabilities/llm/context/*`

原则：

> 不保留旧入口，不保留兼容桥，不允许第二套上下文编译链继续生长

## 调用顺序

## A. Router Phase

业务入口示例：

- `ava/domain/routing/runner.py`

调用顺序：

```text
raw input
  ↓
ContextCompiler.build_turn_input()
  ↓
ContextCompiler.build_snapshot(profile="router")
  ↓
ContextCompiler.compile_router_envelope()
  ├── RuntimePayloadCompiler.compile_router()
  ├── InstructionsCompiler.compile_router()
  └── MessageCompiler.compile_router()
  ↓
CompiledContextEnvelope
  ↓
LLM router call
```

router 阶段目标：

- 识别当前意图
- 判断是否延续上下文
- 产出结构化 `plan`

router 不负责最终回答用户。

---

## B. Responder Phase

业务入口示例：

- `ava/pipeline/generation/dispatcher.py`

调用顺序：

```text
router decision + router plan
  ↓
ContextCompiler.build_snapshot(profile="responder_minimal")
  ↓
继承 router_artifact_brief / router_plan
  ↓
ContextCompiler.compile_responder_envelope()
  ├── RuntimePayloadCompiler.compile_responder()
  ├── InstructionsCompiler.compile_responder()
  └── MessageCompiler.compile_responder()
  ↓
CompiledContextEnvelope
  ↓
LLM responder call
```

responder 阶段目标：

- 基于 router 已锁定的策略输出最终回复
- 必要时携带当前附件或继承附件
- 把 memory / history / skill 以编译结果形式注入模型

---

## C. LLM Service Path

`LLMService` 也已经直接接入新内核，不再经过旧的 `ava/capabilities/llm/context/*`。

调用顺序：

```text
LLMService.build_context()
  ↓
ContextCompiler.build_snapshot()
  ↓
LLMContext(metadata.visible_context = ContextSnapshot)
  ↓
InferenceRequestBuilder.build()
  ↓
ContextCompiler.compile_router_envelope()
  or
ContextCompiler.compile_responder_envelope()
```

## 设计原则

### 1. 单一上下文内核

真正的上下文编译只能有一套：

- 一套 snapshot 逻辑
- 一套 runtime payload 逻辑
- 一套 message assembly 逻辑

### 2. 编译产物优先

模型看到的不是零散字段，而是编译产物：

- `ContextSnapshot`
- `runtime_context`
- `instructions`
- `messages`

### 3. 根包只做入口，不做工具箱

根包只保留：

- `ContextCompiler`

这可以避免未来又把 helper、types、legacy shim 全塞回根包。

### 4. 旧入口直接移除

任何已经被新架构替代的旧入口：

- 直接删除
- 不做桥接
- 不保留双轨调用

## 推荐导入方式

### 业务层

```python
from ava.context_engine import ContextCompiler
from ava.context_engine.types import SnapshotCompileOptions
```

### 支持层

```python
from ava.context_engine.input import build_turn_input
from ava.context_engine.continuity import select_router_model
from ava.context_engine.types import ContextSnapshot
```

### 不推荐

例如过去那些“从根包直接导入 helper 函数”的写法，已经全部移除。
