Configuration is split into two YAML files:

- `configs/model_config.yaml`: model and provider settings, including LLM, TTS, ASR, and optional BigModel config.
- `configs/system_config.yaml`: server, runtime, realtime audio, barge-in, echo detection, and speech postprocess settings.

`configs/config.yaml` is only the entrypoint:

```yaml
config_files:
  - "configs/model_config.yaml"
  - "configs/system_config.yaml"
```

The Python schemas mirror that split:

- `configs/model.py`: LLM, BigModel, ASR, and the top-level provider group.
- `configs/tts.py`: TTS provider schemas, including Doubao `req_params`.
- `configs/system.py`: server and runtime schemas.
- `configs/settings.py`: root `Config`, include loading, deep merge, and environment overrides.

Runtime adapters under `ava/capabilities` consume config objects but do not define config schemas.
