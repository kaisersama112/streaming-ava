import gzip
import json
import unittest

from ava.capabilities.asr.doubao_streaming import StreamingDoubaoASR
from ava.capabilities.asr.asr_streaming_sdk import ASRConfig


class StreamingDoubaoASRProtocolTest(unittest.TestCase):
    def test_parse_gzip_json_server_response_with_sequence(self) -> None:
        payload = {
            "code": 20000000,
            "result": {
                "text": "你好",
                "utterances": [{"text": "你好", "start_time": 0, "end_time": 500, "definite": True}],
            },
        }
        body = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        header = StreamingDoubaoASR._header(
            message_type=StreamingDoubaoASR._FULL_SERVER_RESPONSE,
            flags=0x1,
            serialization=StreamingDoubaoASR._JSON,
            compression=StreamingDoubaoASR._GZIP,
        )
        frame = header + (1).to_bytes(4, "big", signed=True) + len(body).to_bytes(4, "big") + body

        parsed = StreamingDoubaoASR._parse_message(frame)

        self.assertEqual(parsed["type"], StreamingDoubaoASR._FULL_SERVER_RESPONSE)
        self.assertEqual(parsed["sequence"], 1)
        self.assertFalse(parsed["is_final"])
        self.assertEqual(parsed["payload"], payload)

    def test_parse_negative_flag_marks_response_final(self) -> None:
        payload = {"code": 20000000, "result": {"text": "结束"}}
        body = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        header = StreamingDoubaoASR._header(
            message_type=StreamingDoubaoASR._FULL_SERVER_RESPONSE,
            flags=StreamingDoubaoASR._NEG_SEQUENCE,
            serialization=StreamingDoubaoASR._JSON,
            compression=StreamingDoubaoASR._GZIP,
        )
        frame = header + len(body).to_bytes(4, "big") + body

        parsed = StreamingDoubaoASR._parse_message(frame)

        self.assertTrue(parsed["is_final"])
        self.assertEqual(parsed["payload"], payload)

    def test_final_audio_request_uses_empty_negative_packet(self) -> None:
        asr = object.__new__(StreamingDoubaoASR)

        frame = asr._audio_request(b"", final=True)

        self.assertEqual(frame[1] >> 4, StreamingDoubaoASR._AUDIO_ONLY_REQUEST)
        self.assertEqual(frame[1] & 0x0F, StreamingDoubaoASR._NEG_SEQUENCE)
        self.assertEqual(int.from_bytes(frame[4:8], "big"), 0)

    def test_handle_payload_emits_definite_utterance_as_final(self) -> None:
        asr = object.__new__(StreamingDoubaoASR)
        asr._user_callback = lambda text, is_final, metadata=None: emitted.append((text, is_final, metadata))
        asr._last_partial_text = ""
        asr._last_final_text = ""
        asr._final_keys = set()
        asr._error = None
        asr._ready = True
        asr._committed = False
        asr._stopping = False
        emitted = []

        asr._handle_payload(
            {
                "code": 20000000,
                "result": {
                    "utterances": [
                        {"text": "你好", "start_time": 0, "end_time": 500, "definite": True}
                    ]
                },
            },
            sequence=1,
        )

        self.assertEqual(emitted, [("你好", True, {"stability": 1.0, "start_ms": 0, "end_ms": 500})])

    def test_final_response_emits_aggregate_text_even_when_utterance_not_definite(self) -> None:
        asr = object.__new__(StreamingDoubaoASR)
        asr._user_callback = lambda text, is_final, metadata=None: emitted.append((text, is_final, metadata))
        asr._last_partial_text = "你好"
        asr._last_partial_metadata = {}
        asr._last_final_text = ""
        asr._final_keys = set()
        asr._error = None
        asr._ready = True
        asr._committed = False
        asr._stopping = False
        emitted = []

        asr._handle_payload(
            {
                "code": 20000000,
                "result": {
                    "text": "你好，帮我查一下天气",
                    "utterances": [
                        {"text": "你好", "start_time": 0, "end_time": 300, "definite": False},
                        {"text": "帮我查一下天气", "start_time": 300, "end_time": 1200, "definite": False},
                    ],
                },
            },
            sequence=None,
            final_response=True,
        )

        self.assertEqual(
            emitted,
            [("你好，帮我查一下天气", True, {"stability": 1.0, "start_ms": 0, "end_ms": 1200})],
        )

    def test_commit_fallback_promotes_latest_aggregate_partial_to_final(self) -> None:
        asr = object.__new__(StreamingDoubaoASR)
        asr._user_callback = lambda text, is_final, metadata=None: emitted.append((text, is_final, metadata))
        asr._last_partial_text = ""
        asr._last_partial_metadata = {}
        asr._last_final_text = ""
        asr._final_keys = set()
        asr._error = None
        asr._ready = True
        asr._committed = False
        asr._stopping = False
        emitted = []

        asr._handle_payload(
            {
                "code": 20000000,
                "result": {
                    "text": "你好，帮我查一下天气",
                    "utterances": [
                        {"text": "你好", "start_time": 0, "end_time": 300, "definite": False},
                        {"text": "帮我查一下天气", "start_time": 300, "end_time": 1200, "definite": False},
                    ],
                },
            },
            sequence=None,
            final_response=False,
        )
        asr._emit_pending_final_from_partial()

        self.assertEqual(
            emitted,
            [
                ("你好，帮我查一下天气", False, {"start_ms": 0, "end_ms": 1200}),
                ("你好，帮我查一下天气", True, {"stability": 1.0, "start_ms": 0, "end_ms": 1200}),
            ],
        )

    def test_partial_after_commit_reschedules_final_fallback(self) -> None:
        asr = object.__new__(StreamingDoubaoASR)
        asr._user_callback = lambda text, is_final, metadata=None: emitted.append((text, is_final, metadata))
        asr._last_partial_text = ""
        asr._last_partial_metadata = {}
        asr._last_final_text = ""
        asr._committed = True
        asr._stopping = False
        asr._schedule_commit_final_fallback = lambda: scheduled.append(True)
        emitted = []
        scheduled = []

        asr._emit_partial("提交之后才来的文本", {"start_ms": 10})

        self.assertEqual(emitted, [("提交之后才来的文本", False, {"start_ms": 10})])
        self.assertEqual(scheduled, [True])

    def test_headers_use_new_volcengine_asr_auth(self) -> None:
        asr = object.__new__(StreamingDoubaoASR)
        asr.config = ASRConfig(
            provider="dou_bao",
            doubao_x_api_key="api-key",
            doubao_resource_id="volc.seedasr.sauc.duration",
            doubao_request_id="request-id",
        )

        headers = asr._headers()

        self.assertIn("X-Api-Key: api-key", headers)
        self.assertIn("X-Api-Resource-Id: volc.seedasr.sauc.duration", headers)
        self.assertIn("X-Api-Request-Id: request-id", headers)
        self.assertFalse(any(header.startswith("X-Api-App-Key:") for header in headers))
        self.assertFalse(any(header.startswith("X-Api-Access-Key:") for header in headers))

    def test_resource_not_granted_error_points_to_resource_config(self) -> None:
        asr = object.__new__(StreamingDoubaoASR)
        asr.config = ASRConfig(provider="dou_bao", doubao_resource_id="volc.seedasr.sauc.duration")

        message = asr._format_upstream_error(
            "Handshake status 403 Forbidden -+-+- "
            "b'{\"error\":\"[resource_id=volc.seedasr.sauc.duration] requested resource not granted\"}'"
        )

        self.assertIn("Doubao ASR resource is not granted", message)
        self.assertIn("X-Api-Resource-Id='volc.seedasr.sauc.duration'", message)
        self.assertIn("asr_config.dou_bao.x_api_key", message)


if __name__ == "__main__":
    unittest.main()
