"""CLI application service that drives a full conversation turn."""

import sys
from datetime import datetime
from pathlib import Path

from ava.interfaces.cli.commands import handle_state_command
from ava.core.context import build_context_snapshot, build_turn_input
from ava.core.session import load_state, persist_turn, prepare_state_for_turn
from ava.pipeline.generation import build_turn_plan
from ava.capabilities.prompt import build_prompt_center
from ava.pipeline.generation import generate_reply_sync
from ava.pipeline.routing import route_with_context
from ava.pipeline.speech import build_speech_text
from ava.interfaces.cli.audio_playback import maybe_play_audio
from ava.capabilities import tts as tts_client
from ava.core.runtime.errors import DashScopeError
from configs import settings


class VoiceChatService:
    """CLI-facing application service for one-turn route/respond/TTS flow."""

    def __init__(
            self,
            llm_api_base: str,
            llm_api_key: str,
            llm_model: str,
            tts_api_url: str,
            tts_api_key: str,
            tts_model: str,
            voice: str,
            audio_format: str,
            sample_rate: int,
            output_dir: str,
            state_file: str,
            history_window: int,
            session_id: str,
            play_audio: bool,
            llm_timeout: int = 60,
            tts_timeout: int = 120,
    ) -> None:
        self.llm_api_base = llm_api_base
        self.llm_api_key = llm_api_key
        self.llm_model = settings.openai_config.multimodal_model or llm_model
        self.tts_api_url = tts_api_url
        self.tts_api_key = tts_api_key
        self.tts_model = tts_model
        self.voice = voice
        self.audio_format = audio_format
        self.sample_rate = sample_rate
        self.output_dir = output_dir
        self.history_window = history_window
        self.session_id = session_id
        self.play_audio = play_audio
        self.llm_timeout = llm_timeout
        self.tts_timeout = tts_timeout

        self.state = load_state(state_file=state_file, history_window=history_window, session_id=session_id)
        self.prompt_center = build_prompt_center()

    def _handle_commands(self, text: str) -> bool:
        return handle_state_command(text, self.state)

    def _one_turn(self, user_text: str) -> None:
        """Run a single conversational turn end-to-end."""
        turn_input = build_turn_input(user_text, source="cli")

        prepare_state_for_turn(self.state, turn_input)
        snapshot = build_context_snapshot(
            self.state,
            turn_input,
            self.history_window,
            max_context_messages=(
                getattr(settings.runtime, "router_max_context_messages", 0)
                or settings.runtime.max_context_messages
            ),
            profile="router",
        )
        decision, snapshot = route_with_context(
            prompt_center=self.prompt_center,
            turn_input=turn_input,
            state=self.state,
            history_window=self.history_window,
            max_context_messages=(
                getattr(settings.runtime, "router_max_context_messages", 0)
                or settings.runtime.max_context_messages
            ),
            snapshot=snapshot,
            api_base=self.llm_api_base,
            api_key=self.llm_api_key,
            model=self.llm_model,
            timeout=min(self.llm_timeout, 30),
        )
        plan = build_turn_plan(
            state=self.state,
            turn_input=turn_input,
            decision=decision,
            prompt_center=self.prompt_center,
            history_window=self.history_window,
            max_context_messages=(
                getattr(settings.runtime, "responder_max_context_messages", 0)
                or settings.runtime.max_context_messages
            ),
            snapshot=snapshot,
        )

        reply_result = generate_reply_sync(
            state=self.state,
            turn_input=turn_input,
            decision=decision,
            plan=plan,
            snapshot=snapshot,
            api_base=self.llm_api_base,
            api_key=self.llm_api_key,
            model=self.llm_model,
            timeout=self.llm_timeout,
        )
        reply = reply_result.assistant_text

        persist_turn(self.state, turn_input, reply, decision, strategy=plan.strategy)

        print(
            f"助手(scene={decision.turn_scene}, session={decision.session_scene}, "
            f"confidence={decision.confidence:.2f}, handler={plan.orchestrator_name}, "
            f"strategy={plan.strategy.strategy_id}, backend={reply_result.backend}): {reply}"
        )

        speech_result = build_speech_text(reply, plan.strategy)

        audio_url = tts_client.synthesize(
            api_url=self.tts_api_url,
            api_key=self.tts_api_key,
            model=self.tts_model,
            text=speech_result.speech_text,
            voice=self.voice,
            audio_format=self.audio_format,
            sample_rate=self.sample_rate,
            timeout=self.tts_timeout,
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(self.output_dir) / f"reply_{timestamp}.{self.audio_format}"
        tts_client.download_audio(audio_url, output_path)
        print(f"音频已保存: {output_path}")

        if self.play_audio:
            maybe_play_audio(output_path)

    def run(self) -> int:
        if not self.llm_api_key:
            print("LLM api key is required.", file=sys.stderr)
            return 1
        if not self.tts_api_key:
            print("TTS api key is required.", file=sys.stderr)
            return 1

        print("语音对话已启动。输入内容并回车，输入 /exit 结束。")
        print("命令: /fact key=value, /facts, /memory, /reset")

        while True:
            try:
                user_text = input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出。")
                return 0

            if not user_text:
                continue
            if user_text.lower() in {"/exit", "exit", "quit", "/quit"}:
                print("退出。")
                return 0
            if self._handle_commands(user_text):
                continue

            try:
                self._one_turn(user_text)
            except DashScopeError as exc:
                print(f"[error] {exc}", file=sys.stderr)

        return 0
