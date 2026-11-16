"""快速探针：验证 0.5B 文本小模型对路由 JSON 契约的跟随能力与 CPU 延迟。"""
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from dataio import first_system_prompt

ROOT = Path(__file__).resolve().parent
torch.set_num_threads(12)

BASE = ROOT / "models" / "qwen2.5-0.5b-instruct"
SYSTEM = first_system_prompt(ROOT.parent / "data" / "router_sft_train.jsonl", "你是路由分类器，只输出一个 JSON 对象。")

CASES = [
    "帮我解这道方程 2x+3=7",
    "这道题我做得对吗？答案是 x=5",
    "今天天气怎么样",
    "给我讲讲光合作用",
]


def main():
    tok = AutoTokenizer.from_pretrained(str(BASE))
    model = AutoModelForCausalLM.from_pretrained(str(BASE), dtype=torch.float32)
    model.eval()
    for text in CASES:
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = tok(prompt, return_tensors="pt")
        t0 = time.monotonic()
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=160, do_sample=False, use_cache=True)
        dt = (time.monotonic() - t0) * 1000
        gen = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        print(f"[{dt:.0f}ms] {text}\n  -> {gen.strip()[:300]}\n", flush=True)


if __name__ == "__main__":
    main()