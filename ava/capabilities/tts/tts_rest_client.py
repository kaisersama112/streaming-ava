"""REST client for non-streaming TTS synthesis and audio download."""

from pathlib import Path

import requests

from ava.core.runtime.errors import DashScopeError


def synthesize(
    api_url: str,
    api_key: str,
    model: str,
    text: str,
    voice: str,
    audio_format: str = "wav",
    sample_rate: int = 24000,
    timeout: int = 120,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": {
            "text": text,
            "voice": voice,
            "format": audio_format,
            "sample_rate": sample_rate,
        },
    }

    resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise DashScopeError(f"TTS request failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    output = data.get("output", {})
    audio_url = output.get("audio", {}).get("url")
    if not audio_url:
        audio_url = output.get("audio_url")
    if not audio_url and isinstance(output.get("audio"), str):
        candidate = output["audio"].strip()
        if candidate.startswith("http://") or candidate.startswith("https://"):
            audio_url = candidate
    if not audio_url:
        candidate = output.get("url")
        if isinstance(candidate, str) and (
            candidate.startswith("http://") or candidate.startswith("https://")
        ):
            audio_url = candidate
    if not audio_url:
        raise DashScopeError(f"Unexpected TTS response: {data}")
    return audio_url


def download_audio(url: str, output_path: Path, timeout: int = 120) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as resp:
        if resp.status_code >= 400:
            raise DashScopeError(f"Audio download failed ({resp.status_code}): {resp.text}")
        with output_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
