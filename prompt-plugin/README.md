# Prompt Plugin

`prompt-plugin/` is the prompt asset layer for the system.

It is responsible for:

1. storing structured prompt assets in Markdown
2. providing stable system-prompt sources for Router and Responder

It is not responsible for:

- top-level intent recognition
- local rule-based module / subject / style / mode selection in the main chain
- carrying runtime state directly inside system prompts

## Position in the main chain

```text
user input / attachments / history
-> Router one-shot planning
-> route + router_plan
-> model_plan_builder validates and materializes BranchStrategy
-> prompt-plugin provides system prompt assets
-> build_responder_messages
-> responder generates reply
```

## Message structure

```text
system
-> system(runtime context)
-> history
-> user
```

- `system`
  - stable prompt assets from `prompt-plugin`
- `system(runtime context)`
  - structured runtime context built at execution time
- `history`
  - real conversation turns
- `user`
  - current turn input

## Layout

```text
prompt-plugin/
?? core/
?  ?? base/
?  ?? contracts/
?  ?? renderer/
?  ?? router/
?? plugins/
?  ?? education/
?  ?? general_qa/
?  ?? casual_chat/
?  ?? clarify/
?? evals/
```

## Current design rule

Prompt assets define stable policy and structure.
Runtime context carries dynamic state separately.
