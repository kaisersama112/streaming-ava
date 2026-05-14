import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from configs.settings import load_config


class ConfigLoadingTest(unittest.TestCase):
    def test_load_config_merges_includes_and_entrypoint_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "model.yaml").write_text(
                """
openai_config:
  model: "included-model"
voice_config:
  provider: "doubao"
  dou_bao:
    x_api_key: "test-key"
    req_params:
      speaker: "included-speaker"
""".strip(),
                encoding="utf-8",
            )
            (root / "system.yaml").write_text(
                """
server:
  port: 9000
runtime:
  barge_in_partial_chars: 3
""".strip(),
                encoding="utf-8",
            )
            entrypoint = root / "config.yaml"
            entrypoint.write_text(
                """
config_files:
  - "model.yaml"
  - "system.yaml"
server:
  port: 9001
""".strip(),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                cfg = load_config(entrypoint)

        self.assertEqual(cfg.config_files, ["model.yaml", "system.yaml"])
        self.assertEqual(cfg.openai_config.model, "included-model")
        self.assertEqual(cfg.voice_config.provider, "doubao")
        self.assertEqual(cfg.voice_config.dou_bao.req_params.speaker, "included-speaker")
        self.assertEqual(cfg.runtime.barge_in_partial_chars, 3)
        self.assertEqual(cfg.server.port, 9001)


if __name__ == "__main__":
    unittest.main()
