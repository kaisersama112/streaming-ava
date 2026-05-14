import base64
import json
import unittest

from ava.capabilities.tts.base import TTSError, TTSRuntimeOptions
from ava.capabilities.tts.doubao_streaming import StreamingDoubaoTTS
from configs.tts import DoubaoTTSReqParams


def _client() -> StreamingDoubaoTTS:
    return StreamingDoubaoTTS(
        x_api_key="test-key",
        x_api_resource_id="seed-tts-2.0",
        sse_url="https://example.test/sse",
        model="seed-tts-2.0",
        options=TTSRuntimeOptions(audio_format="pcm", sample_rate=24000),
        fallback_speaker="zh_male_dayi_saturn_bigtts",
    )


class StreamingDoubaoTTSTest(unittest.TestCase):
    def test_volcengine_success_terminal_payload_is_not_error(self) -> None:
        tts = _client()

        tts._push_audio_from_payload({"code": 20000000, "message": "OK", "data": None})

        self.assertIsNone(tts._error)
        self.assertEqual(tts.pop_chunks(), [])

    def test_success_payload_pushes_base64_audio(self) -> None:
        tts = _client()
        audio = b"\x01\x02\x03\x04"

        tts._push_audio_from_payload(
            {"code": 20000000, "data": {"audio": base64.b64encode(audio).decode("ascii")}}
        )

        self.assertIsNone(tts._error)
        self.assertEqual(tts.pop_chunks(), [audio])

    def test_non_success_payload_sets_error(self) -> None:
        tts = _client()

        tts._push_audio_from_payload({"code": 45000000, "message": "speaker permission denied"})

        self.assertIsInstance(tts._error, TTSError)

    def test_payload_uses_req_params_model(self) -> None:
        tts = StreamingDoubaoTTS(
            x_api_key="test-key",
            x_api_resource_id="seed-tts-2.0",
            sse_url="https://example.test/sse",
            model="seed-tts-2.0",
            options=TTSRuntimeOptions(audio_format="pcm", sample_rate=24000),
            fallback_speaker="legacy_speaker",
            req_params=DoubaoTTSReqParams.model_validate(
                {
                    "model": "seed-tts-2.0-expressive",
                    "speaker": "configured_speaker",
                    "audio_params": {
                        "format": "mp3",
                        "sample_rate": 24000,
                        "speech_rate": 0,
                        "loudness_rate": 0,
                        "emotion": "happy",
                    },
                    "additions": {
                        "disable_markdown_filter": True,
                        "enable_latex_tn": True,
                        "latex_parser": True,
                        "context_texts": ["配置语气。"],
                    },
                }
            ),
        )

        payload = tts._payload("你好")
        req_params = payload["req_params"]
        additions = json.loads(req_params["additions"])

        self.assertEqual(req_params["text"], "你好")
        self.assertEqual(req_params["model"], "seed-tts-2.0-expressive")
        self.assertEqual(req_params["speaker"], "configured_speaker")
        self.assertEqual(req_params["audio_params"]["format"], "mp3")
        self.assertEqual(req_params["audio_params"]["emotion"], "happy")
        self.assertEqual(additions["context_texts"], ["配置语气。"])
        self.assertNotIn("silence_duration", additions)

    def test_payload_falls_back_to_global_audio_defaults_without_req_params(self) -> None:
        tts = StreamingDoubaoTTS(
            x_api_key="test-key",
            x_api_resource_id="seed-tts-2.0",
            sse_url="https://example.test/sse",
            model="seed-tts-2.0",
            options=TTSRuntimeOptions(audio_format="pcm", sample_rate=24000),
            fallback_speaker="fallback_speaker",
        )

        payload = tts._payload("你好")
        req_params = payload["req_params"]

        self.assertEqual(req_params["speaker"], "fallback_speaker")
        self.assertEqual(req_params["audio_params"]["format"], "pcm")
        self.assertNotIn("additions", req_params)


if __name__ == "__main__":
    unittest.main()
