"""路由小模型 LoRA SFT 微调（序列级蒸馏：教师标注规范 → 3B 学生模型）。

依赖（训练机安装，服务运行不需要）：
    pip install torch transformers peft trl datasets accelerate

用法：
    python scripts/sft_train_router.py \
        --base-model Qwen/Qwen3-4B \
        --train data/router_sft_train.jsonl --val data/router_sft_val.jsonl \
        --output outputs/router-lora [--epochs 3] [--lora-r 16] [--max-len 1024]

产出 LoRA adapter；合并后用 scripts/quantize_router.py 转 GGUF/ONNX 部署。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", default="Qwen/Qwen3-4B")
    parser.add_argument("--train", default="data/router_sft_train.jsonl")
    parser.add_argument("--val", default="data/router_sft_val.jsonl")
    parser.add_argument("--output", default="outputs/router-lora")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--max-len", type=int, default=1024)
    args = parser.parse_args()

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise SystemExit(
            f"缺少训练依赖：{exc}\n请先安装：pip install torch transformers peft trl datasets accelerate"
        )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
    )

    def to_text(record: dict) -> dict:
        messages = record["messages"]
        prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
        target = messages[-1]["content"]
        return {"text": prompt + target + tokenizer.eos_token}

    train_ds = Dataset.from_list([to_text(r) for r in _load_jsonl(Path(args.train))])
    val_ds = Dataset.from_list([to_text(r) for r in _load_jsonl(Path(args.val))])

    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )
    training_args = SFTConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        max_length=args.max_len,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        bf16=torch.cuda.is_available(),
        report_to=[],
    )
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        peft_config=peft_config,
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    print(f"LoRA adapter 已保存：{args.output}")
    print("下一步：合并 adapter 后运行 scripts/quantize_router.py 量化部署")


if __name__ == "__main__":
    main()