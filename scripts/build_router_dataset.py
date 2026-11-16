"""构建路由小模型 SFT 数据集与评测黄金集。

用法：
    .venv/Scripts/python.exe scripts/build_router_dataset.py [--out-dir data] [--val-ratio 0.15]

产出：
- data/router_golden.jsonl     评测黄金集（人工标注种子，eval_intent.py 使用）
- data/router_sft_train.jsonl  SFT 训练集（ChatML messages，assistant 为目标路由 JSON）
- data/router_sft_val.jsonl    SFT 验证集

标签体系与 ava/router_selector/schema.py 的 RouteDecision 对齐；
种子样本同时作为「教师标注」，SFT 即序列级蒸馏（教师=云端大模型标注规范）。
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

# (text, turn_scene, intent, module, subject, has_artifact)
SEED_CASES: list[tuple[str, str, str, str, str, bool]] = [
    ("解一下这道方程：2x+3=11", "education", "solve", "solve", "math", False),
    ("这道题怎么做？", "education", "solve", "solve", "math", False),
    ("帮我算一下 37 乘 24", "education", "solve", "solve", "math", False),
    ("一个水池进水每小时3吨出水每小时2吨，多久能满", "education", "solve", "solve", "math", False),
    ("这道物理题帮我看看，斜面滑块求加速度", "education", "solve", "solve", "general", False),
    ("看图解题", "education", "solve", "solve", "math", True),
    ("这张卷子第一题怎么解", "education", "solve", "solve", "math", True),
    ("我做的对吗？x=4", "education", "check", "check", "math", False),
    ("批改一下我的答案", "education", "check", "check", "math", False),
    ("帮我看看这篇作文写得怎么样", "education", "check", "check", "chinese", False),
    ("检查这道题的步骤有没有错", "education", "check", "check", "math", True),
    ("我写的答案在图上，帮我对一下", "education", "check", "check", "math", True),
    ("这个答案对不对", "education", "check", "check", "general", True),
    ("讲讲什么是一元二次方程", "education", "explain", "explain", "math", False),
    ("解释一下光合作用的过程", "education", "explain", "explain", "general", False),
    ("能再讲一遍刚才那步吗，没听懂", "education", "explain", "explain", "math", False),
    ("这个单词怎么记比较好", "education", "explain", "explain", "english", False),
    ("给我讲讲这段代码为什么报错", "education", "explain", "explain", "cs", False),
    ("图里这个几何定理是什么意思", "education", "explain", "explain", "math", True),
    ("我掌握得怎么样？", "education", "assess", "assess", "math", False),
    ("评估一下我这单元的薄弱点", "education", "assess", "assess", "math", False),
    ("根据刚才的做题情况给我个学习建议", "education", "assess", "assess", "general", False),
    ("接下来我该练什么", "education", "assess", "assess", "math", False),
    ("批改并评估这道题", "education", "check", "check", "math", False),
    ("解完顺便讲讲思路", "education", "solve", "solve", "math", False),
    ("今天天气怎么样", "general_qa", "qa", "qa", "general", False),
    ("推荐几本科幻小说", "general_qa", "qa", "qa", "general", False),
    ("Python 怎么读取 csv 文件", "general_qa", "qa", "qa", "cs", False),
    ("世界上最高的山是哪座", "general_qa", "qa", "qa", "general", False),
    ("帮我写个周报开头", "general_qa", "qa", "qa", "general", False),
    ("这张图里有什么", "general_qa", "qa", "visual", "general", True),
    ("总结一下这段录音的要点", "general_qa", "qa", "qa", "general", True),
    ("你好呀", "casual_chat", "chat", "smalltalk", "general", False),
    ("哈哈哈太好笑了", "casual_chat", "chat", "reaction", "general", False),
    ("谢谢你，帮大忙了", "casual_chat", "chat", "praise", "general", False),
    ("你是谁", "casual_chat", "chat", "smalltalk", "general", False),
    ("嗯", "clarify", "clarify", "clarify-scene", "general", False),
    ("那个", "clarify", "clarify", "clarify-scene", "general", False),
    ("帮我", "clarify", "clarify", "clarify-focus", "general", False),
    ("看看这个", "clarify", "clarify", "clarify-missing-reference", "general", False),
]

# 模板增广：同一意图换表述，提升小模型泛化
AUGMENT_TEMPLATES: dict[str, list[str]] = {
    "solve": ["帮我解这道题：{q}", "{q}，求过程", "这道题不会，{q}"],
    "check": ["我算出来是 {q}，对吗", "批改：{q}", "我的答案 {q}，帮我判断对错"],
    "explain": ["讲讲{q}", "{q}是什么意思", "用简单的话解释{q}"],
    "assess": ["我{q}学得怎么样", "评估一下我的{q}水平", "{q}这块我还有哪些漏洞"],
    "qa": ["{q}是怎么回事", "告诉我{q}", "{q}，简短回答"],
}

AUGMENT_FILLERS: dict[str, list[str]] = {
    "solve": ["鸡兔同笼共35头94足", "相遇问题甲速60乙速40", "求三角形面积底8高5", "分解因式 x^2-5x+6"],
    "check": ["x=7", "答案是 120", "选 B", "y=2x+1"],
    "explain": ["勾股定理", "现在完成时", "递归", "牛顿第一定律", "比喻和拟人的区别"],
    "assess": ["数学", "英语语法", "物理力学", "文言文"],
    "qa": ["极光", "区块链", "黑洞", "马拉松世界纪录", "咖啡因的作用"],
}

ROUTER_SYSTEM = (
    "你是路由分类器。只输出一个 JSON 对象，字段："
    "session_scene(education/general), turn_scene(education/general_qa/casual_chat/clarify), "
    "intent, confidence(0-1), need_clarification(bool), should_preserve_teaching_state(bool), "
    "plan{module, subject, secondary_actions[]}。不要输出其它文字。"
)


def target_json(turn_scene: str, intent: str, module: str, subject: str, *, secondary=None) -> str:
    education = turn_scene == "education"
    payload = {
        "session_scene": "education" if education else "general",
        "turn_scene": turn_scene,
        "intent": intent,
        "confidence": 0.95,
        "need_clarification": turn_scene == "clarify",
        "should_preserve_teaching_state": education,
        "plan": {
            "module": module,
            "subject": subject if education else "general",
            "secondary_actions": list(secondary or []),
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def build_records() -> tuple[list[dict], list[dict]]:
    golden: list[dict] = []
    sft: list[dict] = []
    for idx, (text, scene, intent, module, subject, artifact) in enumerate(SEED_CASES):
        secondary = ["assess"] if text == "批改并评估这道题" else (["explain"] if text == "解完顺便讲讲思路" else [])
        target = target_json(scene, intent, module, subject, secondary=secondary)
        golden.append(
            {
                "id": f"seed_{idx:03d}",
                "text": text,
                "has_artifact": artifact,
                "expected": {"turn_scene": scene, "intent": intent, "module": module},
            }
        )
        sft.append(
            {
                "messages": [
                    {"role": "system", "content": ROUTER_SYSTEM},
                    {"role": "user", "content": text + ("\n[附件:图片]" if artifact else "")},
                    {"role": "assistant", "content": target},
                ]
            }
        )
    for intent, templates in AUGMENT_TEMPLATES.items():
        scene = "education" if intent in {"solve", "check", "explain", "assess"} else "general_qa"
        module = intent if intent != "qa" else "qa"
        for filler in AUGMENT_FILLERS[intent]:
            for template in templates:
                text = template.format(q=filler)
                subject = "math" if intent in {"solve", "check"} else "general"
                sft.append(
                    {
                        "messages": [
                            {"role": "system", "content": ROUTER_SYSTEM},
                            {"role": "user", "content": text},
                            {"role": "assistant", "content": target_json(scene, intent, module, subject)},
                        ]
                    }
                )
    return golden, sft


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    golden, sft = build_records()
    random.Random(args.seed).shuffle(sft)
    val_count = max(1, int(len(sft) * args.val_ratio))
    val, train = sft[:val_count], sft[val_count:]

    for name, records in (
        ("router_golden.jsonl", golden),
        ("router_sft_train.jsonl", train),
        ("router_sft_val.jsonl", val),
    ):
        path = out_dir / name
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{path}: {len(records)} 条")


if __name__ == "__main__":
    main()