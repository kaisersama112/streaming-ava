"""Pipeline package.

This package owns turn-level orchestration:

- input/context: normalize user input and assemble visible context.
- routing: decide the scene, intent, and minimal execution plan.
- generation: turn the router plan into prompts and produce assistant text.
- speech/streaming: convert streamed text into low-latency spoken audio.
- output: write evaluation signals for later tuning.

Domain state and memory models live outside this package. Pipeline code should
read memory through context/projection helpers and emit completed-turn signals,
but long-term memory extraction should stay in a dedicated memory layer.
"""
