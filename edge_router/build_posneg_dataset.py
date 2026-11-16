"""构建路由「正负样本」微调数据集（contrastive / preference SFT）。

正样本：正确路由 JSON（来自 router_sft_train.jsonl / router_sft_train_mm.jsonl）。
负样本：在同一 prompt 下，把路由关键字段扰动成「看似合理但错误」的 JSON
        （场景错配 / 意图错配 / 模块错配），用于让模型学会区分正确与错误路由。

产出：
- data/router_sft_posneg.jsonl     文本正负样本对
- data/router_sft_posneg_mm.jsonl  多模态正负样本对（user 含 image_url）

每条记录：{id, prompt_messages:[system,user], positive:str, negative:str, modality}
用法: python edge_router/build_posneg_dataset.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 场景 → 一个「错误但 plausible」的对照路由（用于生成负样本）
_WRONG = {
    "education": {"session_scene": "general", "turn_scene": "general_qa", "intent": "qa",
                  "module": "qa", "subject": "general"},
    "general_qa": {"session_scene": "education", "turn_scene": "education", "intent": "solve",
                   "module": "solve", "subject": "math"},
    "casual_chat": {"session_scene": "education", "turn_scene": "education", "intent": "explain",
                    "module": "explain", "subject": "general"},
    "clarify": {"session_scene": "general", "turn_scene": "general_qa", "intent": "qa",
                "module": "qa", "subject": "general"},
}


def _make_negative(label: dict) -> dict:
    neg = json.loads(json.dumps(label))
    scene = str(label.get("turn_scene", "general_qa"))
    wrong = _WRONG.get(scene, _WRONG["general_qa"])
    neg["session_scene"] = wrong["session_scene"]
    neg["turn_scene"] = wrong["turn_scene"]
    neg["intent"] = wrong["intent"]
    neg["confidence"] = 0.9  # 负样本同样「自信」，迫使模型靠语义而非置信度区分
    neg["need_clarification"] = False
    plan = neg.get("plan") or {}
    plan["module"] = wrong["module"]
    plan["subject"] = wrong["subject"]
    neg["plan"] = plan
    return neg


def _convert(src: Path, modality: str):
    from dataio import load_records

    out = []
    if not src.exists():
        return out
    for i, rec in enumerate(load_records(src)):
        msgs = rec["messages"]
        prompt = [m for m in msgs if m["role"] != "assistant"]
        assistant = next(m["content"] for m in msgs if m["role"] == "assistant")
        label = json.loads(assistant)
        neg = _make_negative(label)
        out.append({
            "id": f"{modality}_{i:03d}",
            "prompt_messages": prompt,
            "positive": json.dumps(label, ensure_ascii=False),
            "negative": json.dumps(neg, ensure_ascii=False),
            "modality": modality,
        })
    return out


def main():
    text = _convert(DATA / "router_sft_train.jsonl", "text")
    mm = _convert(DATA / "router_sft_train_mm.jsonl", "mm")
    (DATA / "router_sft_posneg.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in text) + "\n", encoding="utf-8")
    (DATA / "router_sft_posneg_mm.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in mm) + "\n", encoding="utf-8")
    print(json.dumps({"text_pairs": len(text), "mm_pairs": len(mm)}, ensure_ascii=False))
    print("POSNEG_DATASET_OK")


if __name__ == "__main__":
    main()