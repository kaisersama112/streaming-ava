# Memory Module Architecture

## Goal

`ava/domain/memory/` contains the session-memory model used by the conversation runtime.
It keeps memory responsibilities split into focused components instead of accumulating all
logic inside `SessionMemory`.

## Directory

```text
ava/domain/memory/
  __init__.py
  session_memory.py
  education.py
  summaries.py
  artifacts.py
  retriever.py
  projector.py
  types.py
```

## Layering

### Aggregate Root

- `SessionMemory`
- Owns the public memory API used by conversation and context-building code.
- Composes the internal memory stores and services.

### Internal Stores

- `EducationMemory`
- Stores lightweight education-scene continuity state.

- `SummaryMemory`
- Maintains recent topics and derived session summaries from `turn_records`.

- `ArtifactMemoryStore`
- Caches structured analysis for current or inherited multimodal artifacts.

### Memory Services

- `MemoryRetriever`
- Collects the most relevant memory entries for the current turn.

- `MemoryProjector`
- Builds the model-visible memory projection used by router and responder prompts.

### Types

- `RetrievedMemory`
- `ArtifactMemoryEntry`
- `MemoryProjection`

## Class Graph

```text
ConversationState
  -> SessionMemory

SessionMemory
  -> EducationMemory
  -> SummaryMemory
  -> ArtifactMemoryStore
  -> MemoryRetriever
  -> MemoryProjector

ContextCompiler
  -> ava/context_engine/memory.py
  -> SessionMemory.retrieve_relevant_memories()
  -> SessionMemory.build_projection()
```

## Runtime Order

### 1. Turn write path

```text
user input
  -> ConversationState.post_multimodal_turn() / complete_realtime_turn()
  -> SessionMemory.append_recent_topic()
  -> SessionMemory.remember_artifact_analysis()
  -> SessionMemory.update_education_state_from_strategy()
  -> SessionMemory.refresh_summaries(turn_records=...)
```

### 2. Context compile path

```text
ContextCompiler
  -> build_memory_projection(...)
  -> SessionMemory.build_projection(...)
  -> MemoryProjector.build(...)
  -> MemoryProjection
```

### 3. Retrieval path

```text
ContextCompiler
  -> retrieve_relevant_memories(...)
  -> SessionMemory.retrieve_relevant_memories(...)
  -> MemoryRetriever.retrieve(...)
  -> list[RetrievedMemory]
```

## Source of Truth

- Conversation records: `ConversationState.turn_records`
- Education continuity: `EducationMemory`
- Artifact continuity: `ArtifactMemoryStore`
- Derived summaries: `SummaryMemory`

`recent_topics`, `context_summary`, and `multimodal_context_summary` are derived memory,
not independent source-of-truth records.

## Public API Rule

External code should go through `SessionMemory` instead of mutating internal stores directly.

Allowed:

```python
state.memory.append_recent_topic(...)
state.memory.set_education_state_value(...)
state.memory.retrieve_relevant_memories(...)
state.memory.build_projection(...)
```

Avoid:

```python
state.memory.education_state["key"] = value
state.memory.recent_topics.append(...)
```

## Context Engine Boundary

`ava/context_engine/memory.py` is a bridge layer. Real memory behavior lives in:

- `ava/domain/memory/retriever.py`
- `ava/domain/memory/projector.py`
- `ava/domain/memory/session_memory.py`
