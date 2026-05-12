# streaming-ava

`streaming-ava` is a realtime multimodal agent stack focused on text, voice, and attachment-driven conversations.

## Main flow

```text
text / voice / attachments
-> TurnInput
-> build_context_snapshot
-> route_with_context
-> build_turn_plan
-> responder
-> speech postprocess
-> TTS / WebRTC playback
```

## Message architecture

```text
system
-> developer(runtime context)
-> conversation history
-> user
```

- `system`
  - stable prompt assets and long-lived rules
- `developer`
  - structured runtime state and routing/strategy context
- `history`
  - real conversation turns
- `user`
  - current input

## Current package layout

- `app.py`
  - FastAPI + WebSocket entry
- `realtime_server.py`
  - local server bootstrap
- `ava/application/`
  - use-case orchestration and runtime workflows
- `ava/domain/`
  - domain models, state machine, memory, routing schema
- `ava/infrastructure/`
  - external adapters for LLM, ASR, TTS, realtime, prompts
- `prompt-plugin/`
  - prompt assets
- `config/`
  - runtime configuration
- `state/`
  - local persisted state

## Key design points

- Router returns `route + plan` in one step
- Orchestration consumes `router_plan` instead of re-routing locally
- `ConversationState` and `SessionMemory` are separated
- runtime state is injected through structured developer messages
- local routing-rule stacks have been removed from the main chain

## Documentation

- `docs/project-structure.md`
- `ava/application/README.md`
- `ava/domain/README.md`
- `ava/infrastructure/README.md`
- `prompt-plugin/README.md`
