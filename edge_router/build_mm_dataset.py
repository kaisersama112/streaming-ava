"""构建多模态路由数据集（合成图片 artifact + 路由 JSON 标签）。

生成：
- data/mm_images/*.png         合成教育/通用图片 artifact（题目、作答、几何图、场景）
- data/router_golden_mm.jsonl  多模态评测金标（id/text/image/expected）
- data/router_sft_train_mm.jsonl 多模态 SFT 样本（messages: system/user[text+image]/assistant JSON）

图片用 PIL 合成（ASCII 公式/几何图形），无需外部素材；标签与文本路由契约一致。
用法: python edge_router/build_mm_dataset.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMG = DATA / "mm_images"

SYSTEM = (
    "你是路由分类器。只输出一个 JSON 对象，字段：session_scene(education/general), "
    "turn_scene(education/general_qa/casual_chat/clarify), intent, confidence(0-1), "
    "need_clarification(bool), should_preserve_teaching_state(bool), "
    "plan{module, subject, secondary_actions[]}。不要输出其它文字。"
)


def _label(turn_scene, intent, module, session_scene=None, confidence=0.9, preserve=True):
    return {
        "session_scene": session_scene or ("education" if turn_scene == "education" else "general"),
        "turn_scene": turn_scene,
        "intent": intent,
        "confidence": confidence,
        "need_clarification": turn_scene == "clarify",
        "should_preserve_teaching_state": preserve,
        "plan": {"module": module, "subject": "math" if turn_scene == "education" else "general",
                 "secondary_actions": []},
    }


def _draw(kind, path):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (480, 320), "white")
    d = ImageDraw.Draw(img)
    if kind == "equation":
        d.text((40, 60), "Solve for x:", fill="black")
        d.text((40, 120), "2x + 3 = 11", fill="black")
        d.line([(40, 180), (440, 180)], fill="gray", width=2)
    elif kind == "answer":
        d.text((40, 60), "My answer:", fill="black")
        d.text((40, 120), "x = 4", fill="blue")
        d.text((40, 180), "2*4 + 3 = 11  OK?", fill="blue")
    elif kind == "geometry":
        d.polygon([(80, 260), (400, 260), (400, 60)], outline="black", width=3)
        d.text((180, 270), "a", fill="black")
        d.text((410, 160), "b", fill="black")
        d.text((200, 140), "c", fill="black")
        d.text((60, 30), "Right triangle", fill="black")
    elif kind == "scene":
        d.ellipse([(360, 30), (440, 110)], fill="yellow", outline="orange")
        d.rectangle([(0, 240), (480, 320)], fill="green")
        d.polygon([(120, 240), (180, 140), (240, 240)], fill="brown")
        d.rectangle([(150, 200), (210, 240)], fill="red")
    elif kind == "wordproblem":
        d.text((30, 50), "A pool fills 3 t/h,", fill="black")
        d.text((30, 90), "drains 2 t/h.", fill="black")
        d.text((30, 130), "When is it full?", fill="black")
        d.rectangle([(30, 180), (200, 280)], outline="blue", width=2)
    img.save(path)


# (kind, text, turn_scene, intent, module)
SPEC = [
    ("equation", "看图解题", "education", "solve", "solve"),
    ("equation", "这道题怎么做？", "education", "solve", "solve"),
    ("wordproblem", "帮我看看图里的应用题", "education", "solve", "solve"),
    ("answer", "我做的对吗？", "education", "check", "check"),
    ("answer", "批改一下图上我的答案", "education", "check", "check"),
    ("answer", "这个答案对不对", "education", "check", "check"),
    ("geometry", "图里这个几何定理是什么意思", "education", "explain", "explain"),
    ("geometry", "讲讲这张图里的三角形", "education", "explain", "explain"),
    ("scene", "这张图里有什么", "general_qa", "qa", "visual"),
    ("scene", "描述一下这张图片", "general_qa", "qa", "visual"),
]


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    golden, sft = [], []
    for i, (kind, text, scene, intent, module) in enumerate(SPEC):
        name = f"mm_{i:03d}_{kind}.png"
        path = IMG / name
        _draw(kind, path)
        label = _label(scene, intent, module)
        abs_path = str(path.resolve())
        golden.append({
            "id": f"mm_{i:03d}", "text": text, "image": abs_path,
            "has_artifact": True,
            "expected": {"turn_scene": scene, "intent": intent, "module": module},
        })
        # 每个金标扩两条 SFT 变体（同图不同问法）
        variants = [text, text + "（结合图片判断）"]
        for v in variants:
            sft.append({"messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": v},
                    {"type": "image_url", "image_url": {"url": abs_path}},
                ]},
                {"role": "assistant", "content": json.dumps(label, ensure_ascii=False)},
            ]})
    (DATA / "router_golden_mm.jsonl").write_text(
        "\n".join(json.dumps(g, ensure_ascii=False) for g in golden) + "\n", encoding="utf-8")
    (DATA / "router_sft_train_mm.jsonl").write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in sft) + "\n", encoding="utf-8")
    print(json.dumps({"images": len(golden), "golden_mm": len(golden), "sft_mm": len(sft),
                      "image_dir": str(IMG)}, ensure_ascii=False))
    print("MM_DATASET_OK")


if __name__ == "__main__":
    main()