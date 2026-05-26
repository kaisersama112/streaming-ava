# Domain Layer

`ava/domain/` contains the core models and policies of the system.

It describes what the system is, not how a turn is executed.

## Current packages

- `context/`
  - `TurnInput`, `MediaArtifact`, `ContextSnapshot`
- `routing/`
  - `RouteDecision`, routing schema, confidence policy
- `session/`
  - `ConversationState`, `SessionMemory`
- `strategy/`
  - `BranchStrategy`, `ResolvedPromptSpec`

## Boundary

This layer is responsible for:

- input and context models
- routing decision models
- session state machine and memory models
- prompt-selection strategy models

This layer is not responsible for:

- calling LLM / TTS / ASR
- reading prompt asset files
- orchestrating full turn execution order

## State and memory split

- `ConversationState`
  - session flow state, turn records, route continuity, realtime lifecycle
- `SessionMemory`
  - education state, summaries, artifact analysis cache

Official access path:

```python
state.memory.*
```

Memory internals:

- `ava/domain/memory/ARCHITECTURE.md`
