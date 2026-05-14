import unittest

from ava.capabilities.asr.factory import build_asr_config
from configs.asr_config import ASRConfig as SettingsASRConfig


class ASRFactoryTest(unittest.TestCase):
    def test_legacy_flat_qwen_config_still_builds_qwen_runtime_config(self) -> None:
        cfg = SettingsASRConfig.model_validate(
            {
                "api_key": "legacy-key",
                "model": "qwen3-asr-flash-realtime-2026-02-10",
                "format": "pcm",
                "sample_rate": 16000,
                "language": "zh",
            }
        )

        runtime = build_asr_config(cfg)

        self.assertEqual(runtime.provider, "qwen3_asr")
        self.assertEqual(runtime.api_key, "legacy-key")
        self.assertEqual(runtime.model, "qwen3-asr-flash-realtime-2026-02-10")
        self.assertEqual(runtime.input_audio_format, "pcm")

    def test_doubao_alias_builds_doubao_runtime_config(self) -> None:
        cfg = SettingsASRConfig.model_validate(
            {
                "provider": "doubao",
                "doubao": {
                    "x_api_key": "api-key",
                    "x_api_resource_id": "volc.seedasr.sauc.duration",
                    "x_api_request_id": "request-id",
                    "audio": {"format": "pcm", "rate": 16000, "language": "zh-CN"},
                    "request": {"model_name": "bigmodel", "show_utterances": True},
                },
            }
        )

        runtime = build_asr_config(cfg)

        self.assertEqual(runtime.provider, "dou_bao")
        self.assertEqual(runtime.doubao_x_api_key, "api-key")
        self.assertEqual(runtime.doubao_request_id, "request-id")
        self.assertEqual(runtime.doubao_audio["rate"], 16000)
        self.assertTrue(runtime.doubao_request["show_utterances"])

    def test_doubao_legacy_app_key_alias_maps_to_new_x_api_key(self) -> None:
        cfg = SettingsASRConfig.model_validate(
            {
                "provider": "doubao",
                "doubao": {
                    "app_key": "legacy-app-key",
                    "resource_id": "volc.bigasr.sauc.concurrent",
                },
            }
        )

        runtime = build_asr_config(cfg)

        self.assertEqual(runtime.doubao_x_api_key, "legacy-app-key")
        self.assertEqual(runtime.doubao_resource_id, "volc.bigasr.sauc.concurrent")


if __name__ == "__main__":
    unittest.main()
