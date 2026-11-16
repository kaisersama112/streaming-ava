"""鲁棒数据加载：兼容 JSON 数组 / JSONL / 拼接 pretty-printed JSON 流三种格式。

data/ 下的路由数据集可能以任意一种形式落盘，统一用 load_records 读取。
"""
import json
from pathlib import Path


def load_records(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, list) else [obj]
    except json.JSONDecodeError:
        pass
    recs, ok = [], True
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            ok = False
            break
    if ok and recs:
        return recs
    dec, idx, out, n = json.JSONDecoder(), 0, [], len(text)
    while idx < n:
        while idx < n and text[idx] in " \t\r\n":
            idx += 1
        if idx >= n:
            break
        obj, end = dec.raw_decode(text, idx)
        out.append(obj)
        idx = end
    return out


def first_system_prompt(path, fallback="你是路由分类器。只输出一个 JSON 对象。"):
    for rec in load_records(path):
        for m in rec.get("messages", []):
            if m.get("role") == "system":
                return str(m.get("content", ""))
    return fallback