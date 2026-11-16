"""启动端侧推理服务：路由小模型（8080）+ 视觉模型（8081），均暴露 OpenAI 兼容接口。

路由：剪枝+Q4_K_M 量化后的 GGUF，llama-cpp-python server，CPU 多线程 + KV slot 复用。
视觉：Qwen2-VL-2B GGUF + mmproj，llama-cpp-python server + qwen2vl chat handler，
      供多模态分析（image->text）调用，结果在会话层缓存。
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"


def wait_health(port, timeout=120):
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2, trust_env=False)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--router-model", default=str(MODELS / "router-pruned-q4_k_m.gguf"))
    ap.add_argument("--router-port", type=int, default=8080)
    ap.add_argument("--vision-port", type=int, default=8081)
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--no-vision", action="store_true")
    args = ap.parse_args()

    procs = []
    router_cmd = [
        sys.executable, "-m", "llama_cpp.server",
        "--model", args.router_model,
        "--host", "127.0.0.1", "--port", str(args.router_port),
        "--n_ctx", str(args.ctx), "--n_threads", str(args.threads),
        "--n_gpu_layers", "0", "--chat_format", "chatml",
    ]
    print("launch router:", " ".join(router_cmd), flush=True)
    procs.append(subprocess.Popen(router_cmd))

    if not args.no_vision:
        vlm_dir = MODELS / "qwen2-vl-2b-gguf"
        gguf = sorted(p for p in vlm_dir.glob("*.gguf") if "mmproj" not in p.name.lower())
        mmproj = sorted(p for p in vlm_dir.glob("*.gguf") if "mmproj" in p.name.lower())
        if gguf and mmproj:
            vision_cmd = [
                sys.executable, "-m", "llama_cpp.server",
                "--model", str(gguf[0]),
                "--clip_model_path", str(mmproj[0]),
                "--chat_handler", "qwen2vl",
                "--host", "127.0.0.1", "--port", str(args.vision_port),
                "--n_ctx", str(args.ctx), "--n_threads", str(args.threads),
                "--n_gpu_layers", "0",
            ]
            print("launch vision:", " ".join(vision_cmd), flush=True)
            procs.append(subprocess.Popen(vision_cmd))
        else:
            print("WARN: vision weights missing, skip vision server", flush=True)

    ok_router = wait_health(args.router_port)
    print("router health:", ok_router, flush=True)
    if not args.no_vision:
        ok_vision = wait_health(args.vision_port)
        print("vision health:", ok_vision, flush=True)
    print("EDGE_SERVE_UP (ctrl-c to stop)", flush=True)
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()