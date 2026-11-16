"""端侧本地推理服务：剪枝+INT8 量化的视觉小模型 Qwen2-VL，OpenAI 兼容 :8080。

同时承担「多模态意图路由」与「image->text 视觉分析」，支持纯文本与 image_url 输入、
真流式（TextIteratorStreamer）、KV cache（use_cache）。/health 供探活。
用法: python edge_router/serve_local.py [--threads N] [--port 8080]
"""
import argparse
import base64
import io
import json
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"


def load_router(int8_dir, pruned_dir, quantize=True):
    import torch
    from transformers import AutoProcessor

    from prune_router import load_model, language_layers

    model, _ = load_model(pruned_dir)
    proc = AutoProcessor.from_pretrained(pruned_dir)
    if quantize:
        lang = torch.ao.quantization.quantize_dynamic(language_layers(model), {torch.nn.Linear}, dtype=torch.qint8)
        state = torch.load(str(Path(int8_dir) / "pytorch_model.int8.bin"), map_location="cpu", weights_only=True)
        lang.load_state_dict(state)
    model.eval()
    return model, proc


def _load_image(url):
    from PIL import Image

    if url.startswith("data:"):
        return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
    if url.startswith("http"):
        import httpx

        return Image.open(io.BytesIO(httpx.get(url, timeout=30, trust_env=False).content)).convert("RGB")
    return Image.open(url).convert("RGB")


def build_app(model, proc, model_name):
    import torch
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    from transformers import TextIteratorStreamer

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/v1/models")
    def models():
        return {"data": [{"id": model_name, "object": "model"}]}

    def _prepare(body):
        messages = body.get("messages") or []
        images, conv = [], []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                conv.append({"role": msg.get("role", "user"), "content": [{"type": "text", "text": content}]})
                continue
            parts = []
            for block in content or []:
                btype = block.get("type")
                if btype in ("image_url", "input_image"):
                    url = block.get("image_url")
                    if isinstance(url, dict):
                        url = url.get("url")
                    if url:
                        images.append(_load_image(str(url)))
                        parts.append({"type": "image"})
                elif btype in ("text", "input_text"):
                    parts.append({"type": "text", "text": block.get("text", "")})
            conv.append({"role": msg.get("role", "user"), "content": parts})
        prompt = proc.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
        inputs = proc(text=[prompt], images=images or None, padding=True, return_tensors="pt")
        return inputs

    @app.post("/v1/chat/completions")
    def chat(body: dict):
        inputs = _prepare(body)
        max_new = int(body.get("max_tokens") or 256)
        if body.get("stream"):
            streamer = TextIteratorStreamer(proc.tokenizer, skip_prompt=True, skip_special_tokens=True)

            def run():
                with torch.no_grad():
                    model.generate(**inputs, max_new_tokens=max_new, do_sample=False,
                                   use_cache=True, streamer=streamer)

            threading.Thread(target=run, daemon=True).start()

            def sse():
                cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
                for piece in streamer:
                    chunk = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                             "model": model_name,
                             "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                done = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                        "model": model_name, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                yield f"data: {json.dumps(done)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(sse(), media_type="text/event-stream")
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=max_new, do_sample=False, use_cache=True)
        text = proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion",
            "created": int(time.time()), "model": model_name,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": int(inputs["input_ids"].shape[1]),
                      "completion_tokens": int(out.shape[1] - inputs["input_ids"].shape[1])},
        }

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--int8", default=str(MODELS / "router-pruned-int8"))
    ap.add_argument("--pruned", default=str(MODELS / "router-pruned-hf"))
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--no-quantize", action="store_true", help="加载剪枝后 fp32 基线（用于精度对比）")
    ap.add_argument("--model-name", default="")
    args = ap.parse_args()

    import torch
    import uvicorn

    torch.set_num_threads(args.threads)
    quantize = not args.no_quantize
    name = args.model_name or ("qwen2-vl-2b-pruned-int8-router" if quantize else "qwen2-vl-2b-pruned-fp32-router")
    print(f"loading vision router (pruned{' + INT8' if quantize else ' fp32'}) ...", flush=True)
    model, proc = load_router(args.int8, args.pruned, quantize=quantize)
    app = build_app(model, proc, name)
    print("EDGE_LOCAL_UP port=", args.port, flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()