# 启动端侧路由小模型服务（llama.cpp llama-server，OpenAI 兼容接口）
# 用法：.\scripts\serve_router_llama.ps1 -ModelPath outputs\router-gguf\router-q5_k_m.gguf [-Threads 8] [-GpuLayers 0]
param(
    [Parameter(Mandatory = $true)][string]$ModelPath,
    [string]$LlamaServer = "third_party/llama.cpp/build/bin/Release/llama-server.exe",
    [int]$Port = 8080,
    [int]$Threads = 0,
    [int]$GpuLayers = 0,
    [int]$CtxSize = 4096
)

if (-not (Test-Path $LlamaServer)) {
    Write-Error "llama-server 不存在：$LlamaServer（请先编译 llama.cpp）"
    exit 1
}
if (-not (Test-Path $ModelPath)) {
    Write-Error "模型不存在：$ModelPath（请先运行 scripts/quantize_router.py）"
    exit 1
}

$threadArgs = @()
if ($Threads -gt 0) { $threadArgs = @("--threads", $Threads, "--threads-batch", $Threads) }

# --cache-reuse：跨请求复用 KV Cache 前缀，降低路由首 token 延迟
# --cont-batching：连续批处理提升并发吞吐
& $LlamaServer `
    --model $ModelPath `
    --host 127.0.0.1 --port $Port `
    --ctx-size $CtxSize `
    --n-gpu-layers $GpuLayers `
    --cache-reuse 256 `
    --cont-batching `
    --parallel 2 `
    --no-mmap `
    @threadArgs