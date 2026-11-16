"""路由小模型量化压缩：GGUF（llama.cpp）与 ONNX INT8 两条路线。

GGUF 路线（推荐侧端部署，配合 llama-server --cache-reuse）：
    python scripts/quantize_router.py --mode gguf \
        --hf-model outputs/router-merged \
        --llama-cpp-dir third_party/llama.cpp --quant Q5_K_M

ONNX INT8 路线（ONNX Runtime 部署）：
    python scripts/quantize_router.py --mode onnx \
        --hf-model outputs/router-merged --onnx-out outputs/router-onnx-int8

产出 compression_report.json：原始/量化体积与压缩率（目标 ≥70%）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _dir_size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / 1024 / 1024
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024


def _report(original_mb: float, quantized_mb: float, out: Path, extra: dict) -> None:
    ratio = 1.0 - quantized_mb / original_mb if original_mb > 0 else 0.0
    report = {
        "original_mb": round(original_mb, 1),
        "quantized_mb": round(quantized_mb, 1),
        "compression_ratio": round(ratio, 4),
        "target_compression": 0.70,
        "target_met": ratio >= 0.70,
        **extra,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def quantize_gguf(args: argparse.Namespace) -> None:
    llama_dir = Path(args.llama_cpp_dir)
    convert_script = llama_dir / "convert_hf_to_gguf.py"
    quantize_bin = llama_dir / "build" / "bin" / "llama-quantize"
    if not quantize_bin.exists():
        quantize_bin = llama_dir / "llama-quantize"
    if not convert_script.exists() or not quantize_bin.exists():
        raise SystemExit(
            f"llama.cpp 工具不完整：{convert_script} / {quantize_bin}\n"
            "请先克隆并编译 llama.cpp（cmake -B build && cmake --build build --config Release）"
        )
    out_dir = Path(args.gguf_out)
    out_dir.mkdir(parents=True, exist_ok=True)
    f16_path = out_dir / "router-f16.gguf"
    quant_path = out_dir / f"router-{args.quant.lower()}.gguf"
    subprocess.run(
        [sys.executable, str(convert_script), args.hf_model, "--outfile", str(f16_path), "--outtype", "f16"],
        check=True,
    )
    subprocess.run([str(quantize_bin), str(f16_path), str(quant_path), args.quant], check=True)
    _report(
        _dir_size_mb(Path(args.hf_model)),
        _dir_size_mb(quant_path),
        out_dir / "compression_report.json",
        {"mode": "gguf", "quant": args.quant, "artifact": str(quant_path)},
    )
    f16_path.unlink(missing_ok=True)


def quantize_onnx(args: argparse.Namespace) -> None:
    try:
        from optimum.onnxruntime import ORTModelForCausalLM, ORTQuantizer
        from optimum.onnxruntime.configuration import AutoQuantizationConfig
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise SystemExit(f"缺少 ONNX 依赖：{exc}\n请先安装：pip install optimum[onnxruntime] transformers")

    out_dir = Path(args.onnx_out)
    fp32_dir = out_dir / "fp32"
    int8_dir = out_dir / "int8"
    model = ORTModelForCausalLM.from_pretrained(args.hf_model, export=True)
    model.save_pretrained(str(fp32_dir))
    AutoTokenizer.from_pretrained(args.hf_model).save_pretrained(str(fp32_dir))
    quantizer = ORTQuantizer.from_pretrained(model)
    qconfig = AutoQuantizationConfig.avx512_vnni(is_static=False, per_channel=True)
    quantizer.quantize(save_dir=str(int8_dir), quantization_config=qconfig)
    AutoTokenizer.from_pretrained(args.hf_model).save_pretrained(str(int8_dir))
    _report(
        _dir_size_mb(fp32_dir),
        _dir_size_mb(int8_dir),
        out_dir / "compression_report.json",
        {"mode": "onnx_int8", "artifact": str(int8_dir)},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["gguf", "onnx"], default="gguf")
    parser.add_argument("--hf-model", required=True, help="合并 LoRA 后的 HF 模型目录")
    parser.add_argument("--quant", default="Q5_K_M", help="GGUF 量化级别：Q4_K_M/Q5_K_M/Q8_0")
    parser.add_argument("--llama-cpp-dir", default="third_party/llama.cpp")
    parser.add_argument("--gguf-out", default="outputs/router-gguf")
    parser.add_argument("--onnx-out", default="outputs/router-onnx")
    args = parser.parse_args()
    if args.mode == "gguf":
        quantize_gguf(args)
    else:
        quantize_onnx(args)


if __name__ == "__main__":
    main()