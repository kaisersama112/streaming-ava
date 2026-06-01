# Domain Layer

`ava/domain/` 保存系统的核心领域模型与领域状态。

它描述“系统中有什么”，而不是“单轮如何执行”。

## 当前正式内容

- `conversation/`
  - `ConversationState`
  - 标准消息读取与派生辅助
- `memory/`
  - `SessionMemory`
  - 教育状态、摘要记忆、附件分析缓存
- `multimodal/`
  - `MediaArtifact`
- `strategy/`
  - `BranchStrategy`
  - `ResolvedPromptSpec`

## 边界

该层负责：

- 会话状态与 turn records
- 领域记忆状态
- 路由与策略相关领域模型
- 多模态附件的领域表示

该层不负责：

- 调用 LLM / TTS / ASR
- 读取 prompt 资源文件
- 编排完整单轮执行流程
- 把输入包装成任何旧输入对象形式

## 状态与记忆分层

- `ConversationState`
  - 只保存原始标准消息与会话运行状态
  - 不承担摘要、文本提取、UI 标签等派生职责
- `SessionMemory`
  - 保存教育连续性状态
  - 保存摘要记忆与附件分析缓存

正式访问路径：

```python
state.memory.*
```

记忆层内部说明：

- `ava/domain/memory/ARCHITECTURE.md`
