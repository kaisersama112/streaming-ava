# Speech

`ava/application/speech/` 负责 responder 文本到 TTS 文本之间的后处理。

当前它的重点能力是数学公式口播。

## 当前职责

- 检测 LaTeX spans
- 生成轻量数学 IR
- 把公式转成适合中文语音朗读的文本
- 在 realtime 场景处理“公式未闭合前不 flush”

## 当前主链

### 非流式

```text
reply_text
-> detect_latex_spans
-> oralize_latex_span
-> build_speech_text
-> speech_text
```

### 流式

```text
token stream
-> LatexAwareSpeechBuffer.push
-> build_speech_text
-> flush chunks to TTS
```

## 关键文件

- `latex_span_detector.py`
  - 识别公式 span，检测未闭合公式
- `math_ir.py`
  - 生成 `MathSpeechIR`
- `math_oralizer.py`
  - 薄适配层，负责 span 级接口与 IR trace 绑定
- `math_latex_oralizer.py`
  - 唯一正式口播内核
- `text_builder.py`
  - 构建 `display_text / speech_text / trace`
- `stream_buffer.py`
  - realtime 数学口播缓冲器

## 当前实现原则

- 只在 `education + math` 分支默认启用
- 只改 LaTeX spans，不重写普通文本
- `math_latex_oralizer.py` 是唯一内核
- `demo_parse_latex.py` 只是兼容转发入口

## 当前 trace

每个 span 的 trace 至少包括：

- `expression_type`
- `oralizer_backend`
- `oralizer_mode`
- `oralizer_fallback_used`
- `oralizer_fallback_reason`
- `normalized_text`

## 与其他模块关系

- 被 [services/README.md](/app/streaming-ava/ava/application/services/README.md) 和 [realtime/README.md](/app/streaming-ava/ava/application/realtime/README.md) 调用
- 依赖 `BranchStrategy` 来决定是否启用
- 不直接调用 TTS SDK，TTS 仍由 `voice_stream.py` 或 infrastructure 层消费
