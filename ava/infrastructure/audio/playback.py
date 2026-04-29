"""Local audio playback helpers used by the CLI path."""

import subprocess
import sys
from pathlib import Path


def maybe_play_audio(file_path: Path) -> None:
    players = [
        ["ffplay", "-nodisp", "-autoexit", str(file_path)],
        ["aplay", str(file_path)],
        ["afplay", str(file_path)],
    ]
    for cmd in players:
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    print("[warn] No supported audio player found (tried ffplay/aplay/afplay).", file=sys.stderr)
