from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse
from urllib.request import Request, urlopen

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ava.interfaces.websocket import PlayerConfig, get_bridge
from ava.capabilities.asr.asr_streaming_client import StreamingASRClient
from ava.capabilities.asr.asr_streaming_sdk import ASRError
from ava.capabilities.asr.factory import build_asr_config
from ava.pipeline.streaming import RealtimeConversationSession
from ava.domain.conversation.state import ConversationState
from configs import settings

# WebSocket 实时服务模块日志记录器
_LOG = logging.getLogger("streaming_ava.ws")
_URL_ATTACHMENT_TIMEOUT_SECONDS = 12
_URL_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024


@dataclass
class WSRuntime:
    """封装单个 WebSocket 会话运行时依赖。

    用于聚合当前连接生命周期内所需的核心对象：
    - session: 实时对话会话，负责管理对话状态、事件流与中断
    - asr: 流式 ASR 客户端，负责接收 PCM 音频并返回识别结果
    - player_url: 前端播放器地址
    - asr_task/event_task: 后台异步任务
    - staged_attachments: 暂存的标准附件内容块，供后续文本/语音轮次消费
    """

    session: RealtimeConversationSession
    asr: StreamingASRClient
    player_url: str
    asr_task: asyncio.Task | None = None
    event_task: asyncio.Task | None = None
    staged_attachments: list[dict[str, object]] = field(default_factory=list)


def _normalize_attachment_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.netloc == "github.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 5 and parts[2] == "blob":
            owner, repo, _, branch = parts[:4]
            remaining = "/".join(parts[4:])
            value = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{remaining}"
            parsed = urlparse(value)
    encoded_path = quote(unquote(parsed.path), safe="/:@")
    encoded_query = quote(unquote(parsed.query), safe="=&?/:,+")
    return urlunparse(parsed._replace(path=encoded_path, query=encoded_query))


def _candidate_attachment_urls(raw: str) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    parsed = urlparse(value)
    candidates: list[str] = []
    if parsed.scheme in {"http", "https"} and parsed.netloc == "github.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 5 and parts[2] == "blob":
            owner, repo, _, branch = parts[:4]
            remaining = "/".join(parts[4:])
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{remaining}"
            query_url = value + ("&" if parsed.query else "?") + "raw=1"
            cdn_url = f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/{remaining}"
            candidates.extend([raw_url, query_url, cdn_url])
    candidates.append(value)
    normalized: list[str] = []
    for candidate in candidates:
        encoded = _normalize_attachment_url(candidate)
        if encoded and encoded not in normalized:
            normalized.append(encoded)
    return normalized


def _guess_attachment_name(uri: str, mime_type: str) -> str:
    parsed = urlparse(uri)
    name = unquote(Path(parsed.path).name)
    if name:
        return name
    ext = mimetypes.guess_extension(mime_type or "") or ""
    return f"attachment{ext}"


def _guess_audio_format(mime_type: str) -> str:
    value = str(mime_type or "").strip().lower()
    if "/" in value:
        return value.split("/", 1)[1] or "wav"
    return "wav"


def _to_data_url(mime_type: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _attachment_item_to_content_block(
        *,
        name: str,
        mime_type: str,
        data: bytes | None = None,
        uri: str | None = None,
        summary: str = "",
) -> dict[str, object] | None:
    """把附件元数据转换为标准 user message 内容块。"""
    normalized_name = str(name or "attachment").strip() or "attachment"
    normalized_mime_type = str(mime_type or "application/octet-stream").strip() or "application/octet-stream"
    normalized_uri = str(uri or "").strip()
    normalized_summary = str(summary or "").strip()
    data_url = _to_data_url(normalized_mime_type, data) if data else ""

    if normalized_mime_type.startswith("image/"):
        image_url = data_url or normalized_uri
        if not image_url:
            return None
        return {
            "type": "input_image",
            "image_url": image_url,
            "filename": normalized_name,
            "mime_type": normalized_mime_type,
            "summary": normalized_summary,
            "uri": normalized_uri or None,
        }

    if normalized_mime_type.startswith("audio/"):
        audio_data = data_url or normalized_uri
        if not audio_data:
            return None
        return {
            "type": "input_audio",
            "input_audio": {
                "data": audio_data,
                "format": _guess_audio_format(normalized_mime_type),
            },
            "filename": normalized_name,
            "mime_type": normalized_mime_type,
            "summary": normalized_summary,
            "uri": normalized_uri or None,
        }

    block: dict[str, object] = {
        "type": "input_file",
        "filename": normalized_name,
        "mime_type": normalized_mime_type,
        "summary": normalized_summary,
    }
    if data_url:
        block["file_data"] = data_url
    if normalized_uri:
        block["file_url"] = normalized_uri
        block["uri"] = normalized_uri
    if "file_data" not in block and "file_url" not in block:
        return None
    return block


def _fetch_attachment_from_url(item: dict[str, object]) -> dict[str, object] | None:
    candidates = _candidate_attachment_urls(str(item.get("uri", "") or ""))
    if not candidates:
        return None

    last_error: Exception | None = None
    for uri in candidates:
        try:
            req = Request(
                uri,
                headers={
                    "User-Agent": "streaming-ava/1.0",
                    "Accept": "*/*",
                    "Connection": "close",
                },
            )
            with urlopen(req, timeout=_URL_ATTACHMENT_TIMEOUT_SECONDS) as resp:
                content_type = str(resp.headers.get("Content-Type", "") or "").split(";", 1)[0].strip()
                mime_type = content_type or mimetypes.guess_type(uri)[0] or "application/octet-stream"
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _URL_ATTACHMENT_MAX_BYTES:
                        raise ValueError(f"attachment from url exceeds {_URL_ATTACHMENT_MAX_BYTES} bytes")
                    chunks.append(chunk)
                data = b"".join(chunks)

            return _attachment_item_to_content_block(
                name=str(item.get("name") or _guess_attachment_name(uri, mime_type)),
                mime_type=str(item.get("mime_type") or mime_type),
                data=data,
                summary=str(item.get("summary", "") or ""),
                uri=uri,
            )
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return None


async def _decode_attachments(items: list[dict[str, object]] | None) -> list[dict[str, object]]:
    """将前端附件字典列表解码为标准用户消息内容块列表。

    输入格式约定：
    - data_base64: base64 编码后的二进制内容
    - uri: 远程附件 URL（可选）
    - name: 文件名
    - mime_type: MIME 类型
    - summary: 附件摘要（可选）

    说明：
    - 空数据会被跳过
    - base64 解码失败的项会被忽略
    """
    attachments: list[dict[str, object]] = []
    for item in items or []:
        raw = str(item.get("data_base64", "") or "").strip()
        if raw:
            try:
                binary = base64.b64decode(raw)
            except Exception:
                # 非法 base64 数据直接跳过，避免影响整条请求。
                continue
            block = _attachment_item_to_content_block(
                name=str(item.get("name", "attachment")),
                mime_type=str(item.get("mime_type", "application/octet-stream")),
                data=binary,
                summary=str(item.get("summary", "") or ""),
                uri=str(item.get("uri", "") or "") or None,
            )
            if block is not None:
                attachments.append(block)
            continue
        try:
            attachment = await asyncio.to_thread(_fetch_attachment_from_url, item)
        except Exception:
            continue
        if attachment is not None:
            attachments.append(attachment)
    return attachments


def _attachment_payloads(attachments: list[dict[str, object]]) -> list[dict[str, object]]:
    """将标准附件内容块转换为前端可消费的预览载荷。"""
    payload: list[dict[str, object]] = []
    for index, attachment in enumerate(attachments, start=1):
        block_type = str(attachment.get("type", "") or "").strip()
        if block_type == "input_image":
            image_url = str(attachment.get("image_url", "") or "").strip()
            image_uri = str(attachment.get("uri", "") or "").strip()
            if not image_uri and image_url and not image_url.startswith("data:"):
                image_uri = image_url
            payload.append(
                {
                    "name": str(attachment.get("filename", "") or f"image-{index}"),
                    "mime_type": str(attachment.get("mime_type", "image/*") or "image/*"),
                    "summary": str(attachment.get("summary", "") or ""),
                    "size_bytes": 0,
                    "data_url": image_url if image_url.startswith("data:") else "",
                    "uri": image_uri,
                    "preview_url": image_url,
                }
            )
            continue

        if block_type == "input_audio":
            audio_payload = dict(attachment.get("input_audio") or {})
            audio_data = str(audio_payload.get("data", "") or "").strip()
            audio_format = str(audio_payload.get("format", "") or "wav").strip()
            mime_type = str(attachment.get("mime_type", "") or f"audio/{audio_format}")
            audio_uri = str(attachment.get("uri", "") or "").strip()
            if not audio_uri and audio_data and not audio_data.startswith("data:"):
                audio_uri = audio_data
            payload.append(
                {
                    "name": str(attachment.get("filename", "") or f"audio-{index}"),
                    "mime_type": mime_type,
                    "summary": str(attachment.get("summary", "") or ""),
                    "size_bytes": 0,
                    "data_url": audio_data if audio_data.startswith("data:") else "",
                    "uri": audio_uri,
                    "preview_url": audio_data,
                }
            )
            continue

        if block_type == "input_file":
            file_data = str(attachment.get("file_data", "") or "").strip()
            file_url = str(attachment.get("file_url", "") or attachment.get("uri", "") or "").strip()
            payload.append(
                {
                    "name": str(attachment.get("filename", "") or f"file-{index}"),
                    "mime_type": str(
                        attachment.get("mime_type", "application/octet-stream") or "application/octet-stream"),
                    "summary": str(attachment.get("summary", "") or ""),
                    "size_bytes": 0,
                    "data_url": file_data if file_data.startswith("data:") else "",
                    "uri": file_url,
                    "preview_url": file_data or file_url,
                }
            )
            continue
    return payload


async def _safe_send_json(ws: WebSocket, payload: dict[str, object], closed: asyncio.Event) -> bool:
    """安全地向 WebSocket 发送 JSON 文本消息。

    返回值：
    - True: 发送成功
    - False: 连接已关闭或发送失败

    说明：
    - 如果 closed 事件已设置，则不再尝试发送
    - 发送失败时会同步设置 closed，避免后续协程继续写入
    """
    if closed.is_set():
        return False
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
        return True
    except (WebSocketDisconnect, RuntimeError):
        closed.set()
        return False


def _resolve_player_url(raw_url: str, ws: WebSocket) -> str:
    """解析并修正播放器地址，使前端能够正确访问。

    优先级：
    1. 如果配置中显式提供 realtime_audio_public_url，则直接使用
    2. 否则使用 bridge 返回的 raw_url
    3. 若 raw_url 绑定在本地地址（127.0.0.1 / localhost / 0.0.0.0），
       则改写为当前 WebSocket 请求所对应的主机名，便于外部访问

    适用场景：
    - 服务部署在远端机器/容器中，播放器不能继续使用 127.0.0.1 暴露给浏览器
    """
    public_url = getattr(settings.runtime, "realtime_audio_public_url", "") or ""
    if public_url:
        return public_url

    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        return raw_url

    host = parsed.hostname or ""
    if host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        return raw_url

    request_host = ws.headers.get("host") or ""
    request_host = request_host.split(":", 1)[0] if request_host else (ws.url.hostname or host)
    scheme = "https" if ws.url.scheme == "wss" else "http"
    port = parsed.port or getattr(settings.runtime, "realtime_audio_port", 7860)
    return urlunparse((scheme, f"{request_host}:{port}", parsed.path or "", "", "", ""))


def _resolve_session_id(raw: str | None) -> str:
    """规范化会话 ID。

    若前端未提供 session_id，则回退到默认配置值。
    最终通过 ConversationState.normalize_session_id 进行标准化处理。
    """
    return ConversationState.normalize_session_id(raw or settings.runtime.default_session_id)


def _build_bridge_session(ws: WebSocket, session_id: str) -> tuple[RealtimeConversationSession, str]:
    """构建实时音频桥接器与对话会话对象。

    主要步骤：
    1. 组装 PlayerConfig
    2. 获取 bridge 并尝试启动播放器
    3. 修正播放器可访问地址
    4. 加载指定 session_id 的历史状态
    5. 创建 RealtimeConversationSession

    返回：
    - RealtimeConversationSession 实例
    - 前端可访问的播放器 URL
    """
    bind_host = getattr(settings.runtime, "realtime_audio_host", "127.0.0.1")
    if not (getattr(settings.runtime, "realtime_audio_public_url", "") or "") and bind_host in {"127.0.0.1",
                                                                                                "localhost"}:
        # 若未配置公网地址且当前仅绑定本地回环地址，则提升为 0.0.0.0，
        # 以便播放器服务可被外部访问
        bind_host = "0.0.0.0"

    cfg = PlayerConfig(
        host=bind_host,
        port=getattr(settings.runtime, "realtime_audio_port", 7860),
        public_url=getattr(settings.runtime, "realtime_audio_public_url", ""),
        sample_rate=settings.voice_config.sample_rate,
    )
    bridge = get_bridge(cfg)

    # 确保播放器在当前进程生命周期内只需启动一次。
    # 调用方拿到 URL 后，可在浏览器中打开播放器页面。
    player_url = cfg.public_url or f"http://127.0.0.1:{cfg.port}"
    try:
        player_url = bridge.launch()
    except Exception:
        # 若 bridge 已启动或启动失败，则保留兜底地址。
        pass

    player_url = _resolve_player_url(player_url, ws)

    # 若 bridge 已启动或启动失败，则保留兜底地址
    state = ConversationState(
        settings.runtime.state_file,
        settings.runtime.history_window,
        session_id=session_id,
    )
    state.load()
    return (
        RealtimeConversationSession(
            bridge,
            state=state,
            history_window=settings.runtime.history_window,
            max_context_messages=settings.runtime.max_context_messages,
            session_id=session_id,
        ),
        player_url,
    )


def create_app() -> FastAPI:
    """创建 FastAPI 应用并注册 HTTP / WebSocket 路由。"""
    app = FastAPI(title="streaming-ava-realtime")

    # 提供一个最小可用的静态前端页面（非 Streamlit）。
    # 使用静态文件部署更轻量，无需额外打包工具即可直接运行。
    import pathlib

    static_dir = pathlib.Path(__file__).resolve().parent / "static"
    print(static_dir)
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        async def index():  # type: ignore[override]
            """返回静态前端首页。"""
            return FileResponse(str(static_dir / "index.html"))

    @app.get("/health")
    async def health() -> dict[str, str]:
        """健康检查接口。"""
        return {"status": "ok"}

    @app.websocket("/ws/audio")
    async def ws_audio(ws: WebSocket):
        """实时音频 WebSocket 接口。"""
        await ws.accept()
        ws_closed = asyncio.Event()
        session_id = _resolve_session_id(ws.query_params.get("session_id"))

        # 从配置中组装 ASRConfig，兼容旧的扁平配置和新的 provider 配置。
        asr_cfg = build_asr_config(settings.asr_config)

        # 创建实时会话与播放器桥接
        session, player_url = _build_bridge_session(ws, session_id)
        runtime = WSRuntime(session=session, asr=StreamingASRClient(asr_cfg), player_url=player_url)

        # 临时 PCM 缓冲区：将前端持续发送的小块音频拼成适合 ASR 上传的帧大小
        pcm_buffer = bytearray()
        frame_bytes = max(320, int(asr_cfg.sample_rate * 2 * 0.1))  # 约 0.1 秒，PCM16 / 单声道

        async def _asr_result_loop():
            """Poll ASR results and forward them into the realtime session."""
            try:
                while not ws_closed.is_set():
                    results = runtime.asr.pop_results(max_items=16)
                    if results:
                        for r in results:
                            if r.is_final:
                                # final 结果到来时，消费当前暂存附件并作为本轮输入的一部分
                                content_blocks = list(runtime.staged_attachments)
                                runtime.session.on_asr_final(
                                    r.text,
                                    content_blocks=content_blocks,
                                    stability=r.stability,
                                    start_ms=r.start_ms,
                                    end_ms=r.end_ms,
                                    ts=r.received_at,
                                )
                            else:
                                runtime.session.on_asr_partial(
                                    r.text,
                                    stability=r.stability,
                                    start_ms=r.start_ms,
                                    end_ms=r.end_ms,
                                    ts=r.received_at,
                                )
                    await asyncio.sleep(0.02)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                _LOG.exception("ASR result loop crashed: %s", exc)
                await _safe_send_json(ws, {"type": "error", "scope": "asr", "message": str(exc)}, ws_closed)

        async def _session_event_loop():
            """Drain realtime session events and push them to the client."""
            try:
                while not ws_closed.is_set():
                    events = runtime.session.poll_events(max_items=64)
                    for payload in events:
                        if not await _safe_send_json(ws, payload, ws_closed):
                            return
                    await asyncio.sleep(0.02)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                _LOG.exception("Session event loop crashed: %s", exc)

        try:
            # 启动流式 ASR，并创建两个后台消费任务
            runtime.asr.start()
            runtime.asr_task = asyncio.create_task(_asr_result_loop())
            runtime.event_task = asyncio.create_task(_session_event_loop())

            # 建连成功后向前端发送 hello 包，声明协议与初始状态
            if not await _safe_send_json(
                    ws,
                    {
                        "type": "hello",
                        "protocol": 1,
                        "audio": {
                            "format": "pcm_s16le",
                            "sample_rate": asr_cfg.sample_rate,
                            "channels": 1,
                        },
                        "player_url": runtime.player_url,
                        "session_id": runtime.session.session_id,
                        "history": runtime.session.history_snapshot(limit=16),
                        "staged_attachments": _attachment_payloads(runtime.staged_attachments),
                        "note": "Send binary frames as raw PCM audio and JSON text as control messages such as interrupt or ping.",
                    },
                    ws_closed,
            ):
                return

            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    ws_closed.set()
                    break

                # ---------------------------
                # 处理二进制音频帧
                # ---------------------------
                if "bytes" in msg and msg["bytes"] is not None:
                    audio_bytes = msg["bytes"]

                    # 将音频帧通知给 session，用于本地实时状态跟踪
                    runtime.session.on_audio_frame(audio_bytes, ts=time.monotonic())

                    # 放入缓冲区，按固定帧大小切片发送给 ASR
                    pcm_buffer.extend(audio_bytes)

                    while len(pcm_buffer) >= frame_bytes:
                        chunk = bytes(pcm_buffer[:frame_bytes])
                        del pcm_buffer[:frame_bytes]
                        try:
                            runtime.asr.send_audio(chunk)
                        except ASRError as exc:
                            # 若为可恢复错误，则尝试重连 ASR 上游
                            if runtime.asr.is_recoverable_error(exc):
                                _LOG.warning("ASR upstream closed, restarting realtime ASR: %s", exc)
                                try:
                                    runtime.asr.restart()
                                    await _safe_send_json(
                                        ws,
                                        {
                                            "type": "control",
                                            "action": "asr_restarted",
                                            "detail": "recoverable_upstream_close",
                                        },
                                        ws_closed,
                                    )
                                except Exception as restart_exc:
                                    _LOG.exception("ASR restart failed: %s", restart_exc)
                                    await _safe_send_json(
                                        ws,
                                        {
                                            "type": "error",
                                            "scope": "asr",
                                            "message": str(restart_exc),
                                        },
                                        ws_closed,
                                    )
                            else:
                                # 不可恢复错误：告知前端并停止 ASR
                                _LOG.exception("Fatal ASR send error: %s", exc)
                                await _safe_send_json(
                                    ws,
                                    {"type": "error", "scope": "asr", "message": str(exc)},
                                    ws_closed,
                                )
                                try:
                                    runtime.asr.stop()
                                except Exception:
                                    pass

                    continue

                # ---------------------------
                # 处理文本控制消息
                # ---------------------------
                text = msg.get("text")
                if not text:
                    continue

                try:
                    obj = json.loads(text)
                except Exception:
                    # 非 JSON 文本时，自动视为普通文本输入
                    obj = {"type": "text", "text": text}

                mtype = obj.get("type")

                if mtype == "interrupt":
                    # 手动打断当前 assistant 响应 / TTS 播放
                    runtime.session.interrupt(reason=str(obj.get("reason", "manual")))
                    continue

                if mtype == "mic_stopped":
                    # 前端通知“麦克风已停止采集”
                    # 将剩余缓冲区补齐后提交给 ASR，并显式 commit 当前输入段
                    try:
                        tail_len = len(pcm_buffer)
                        if pcm_buffer:
                            tail = bytes(pcm_buffer)
                            pcm_buffer.clear()
                            if len(tail) < frame_bytes:
                                # 尾帧不足时补零，保证 ASR 上传帧格式稳定
                                tail = tail + (b"\x00" * (frame_bytes - len(tail)))
                            runtime.asr.send_audio(tail)

                        runtime.asr.commit()

                        await _safe_send_json(
                            ws,
                            {"type": "control", "action": "audio_input_committed"},
                            ws_closed,
                        )
                    except ASRError as exc:
                        _LOG.exception("ASR commit on mic stop failed: %s", exc)
                        await _safe_send_json(
                            ws,
                            {"type": "error", "scope": "asr_commit", "message": str(exc)},
                            ws_closed,
                        )
                    continue

                if mtype == "ping":
                    # 简单保活 / 连通性探测
                    await _safe_send_json(ws, {"type": "pong"}, ws_closed)
                    continue

                if mtype == "playback_started":
                    continue

                if mtype == "text":
                    # 文本输入模式：支持同时附带附件
                    text = str(obj.get("text", "")).strip()
                    attachments = await _decode_attachments(obj.get("attachments", []) or [])
                    if text or attachments:
                        user_message_content: list[dict[str, object]] = []
                        if text:
                            user_message_content.append({"type": "input_text", "text": text})
                        user_message_content.extend(attachments)
                        runtime.session.submit_turn(
                            {"role": "user", "content": user_message_content},
                            source="realtime_web_text",
                        )
                    continue

                if mtype == "stage_attachments":
                    # 仅暂存附件，不立即触发一轮对话
                    # 后续 ASR final 或 text 提交时可一并消费
                    runtime.staged_attachments = await _decode_attachments(obj.get("attachments", []) or [])
                    await _safe_send_json(
                        ws,
                        {
                            "type": "staged_attachments",
                            "attachments": _attachment_payloads(runtime.staged_attachments),
                            "consumed_by": "",
                        },
                        ws_closed,
                    )
                    continue

                if mtype == "clear_staged_attachments":
                    # 清空当前暂存附件
                    runtime.staged_attachments.clear()
                    await _safe_send_json(
                        ws,
                        {
                            "type": "staged_attachments",
                            "attachments": [],
                            "consumed_by": "",
                        },
                        ws_closed,
                    )
                    continue

                # 未识别的消息类型统一回传错误
                await _safe_send_json(ws, {"type": "error", "message": f"unknown message type: {mtype}"}, ws_closed)

        except WebSocketDisconnect:
            ws_closed.set()
        finally:
            # 无论正常断开还是异常退出，均统一清理资源
            ws_closed.set()

            # 关闭实时对话会话
            runtime.session.shutdown()

            # 停止 ASR
            try:
                runtime.asr.stop()
            except Exception:
                pass

            # 取消后台 ASR 结果任务
            if runtime.asr_task is not None:
                runtime.asr_task.cancel()
                try:
                    await runtime.asr_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            # 取消后台 session 事件任务
            if runtime.event_task is not None:
                runtime.event_task.cancel()
                try:
                    await runtime.event_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

    return app

# # 模块级应用实例，供 uvicorn / gunicorn 直接加载
# app = create_app()
