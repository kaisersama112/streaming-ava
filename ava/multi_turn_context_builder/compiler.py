"""多轮上下文构造主实现。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ava.capabilities.prompt.prompt_builder import (
    build_responder_prompt_package,
    build_responder_system_prompt,
    build_router_system_prompt,
)
from ava.capabilities.prompt.prompt_loader import PromptCenter
from ava.domain.conversation.state import ConversationState
from ava.domain.multimodal.continuity import (
    ARTIFACT_BLOCK_TYPES,
    artifact_blocks,
    blocks_to_artifacts,
)
from configs import settings

from .runtime import build_runtime_payload, render_runtime_section
from .types import (
    CompiledContext,
    CompiledConversationPayload,
    CompiledInstructions,
    ContextSession,
    ContextTurn,
    ConversationBuildOptions,
    ConversationContext,
)


def context_snapshot_hash(instructions: str, input_messages: list[dict[str, Any]]) -> str:
    """上下文快照指纹，用于 trace 关联与缓存键。"""
    blob = json.dumps(
        {"instructions": instructions, "input": input_messages},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class ContextCompiler:
    """多轮上下文构造器。

    该类是 `ava.multi_turn_context_builder` 的唯一正式实现入口，
    只负责围绕标准会话消息做本轮上下文编译。

    核心职责：
    - 规范化当前轮 `user message`
    - 拼装可见历史消息
    - 编译 router / responder 阶段的 `instructions`
    - 输出最终传给模型的 `input` 消息数组

    输入约定：
    - 当前轮输入只接受标准 `user message`
    - 不再负责附件 DTO 装配
    - 不再负责任何旧输入对象到上下文的正式转换

    输出约定：
    - 统一输出 `ConversationContext`
    - 统一输出 `CompiledConversationPayload`
    """

    @staticmethod
    def _safe_text(value: Any) -> str:
        """安全地把任意值转成去首尾空白后的字符串。

        参数：
        - value：任意输入值，允许为 `None`、字符串或其他对象

        返回：
        - `str`：清洗后的字符串；当输入为空时返回空字符串
        """
        return str(value or "").strip()

    @staticmethod
    def _text_block(text: str, *, output: bool = False) -> dict[str, str] | None:
        """构造标准文本内容块。

        参数：
        - text：文本内容
        - output：是否构造成 assistant 侧输出块；
          `False` 表示 `input_text`，`True` 表示 `output_text`

        返回：
        - `dict[str, str] | None`：
          - 有效文本时返回标准 content block
          - 文本为空时返回 `None`
        """
        value = str(text or "").strip()
        if not value:
            return None
        return {
            "type": "output_text" if output else "input_text",
            "text": value,
        }

    @staticmethod
    def _normalize_user_message(user_message: dict[str, Any]) -> dict[str, Any]:
        """规范化当前轮标准 `user message`。

        该方法只保留当前系统允许的 block 结构，并清洗空值：
        - `input_text`
        - `input_image`
        - `input_audio`
        - `input_file`

        参数：
        - user_message：外层传入的标准 user message 字典

        返回：
        - `dict[str, Any]`：规范化后的 user message
        """
        role = str(user_message.get("role", "user") or "user").strip() or "user"
        content = list(user_message.get("content") or [])
        normalized_content: list[dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type", "") or "").strip()

            if block_type == "input_text":
                text = str(block.get("text", "") or "").strip()
                if text:
                    normalized_content.append({"type": "input_text", "text": text})
                continue

            if block_type == "input_image":
                image_url = str(block.get("image_url", "") or "").strip()
                if image_url:
                    normalized_content.append({"type": "input_image", "image_url": image_url})
                continue

            if block_type == "input_audio":
                payload = dict(block.get("input_audio") or {})
                audio_data = str(payload.get("data", "") or "").strip()
                audio_format = str(payload.get("format", "") or "").strip()
                if audio_data and audio_format:
                    normalized_content.append(
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_data,
                                "format": audio_format,
                            },
                        }
                    )
                continue

            if block_type == "input_file":
                normalized_block = {"type": "input_file"}
                for key in ("file_id", "file_data", "file_url", "filename"):
                    value = block.get(key)
                    if value not in (None, ""):
                        normalized_block[key] = value
                if len(normalized_block) > 1:
                    normalized_content.append(normalized_block)

        return {
            "role": role,
            "content": normalized_content,
        }

    @staticmethod
    def _message_user_text(message: dict[str, Any]) -> str:
        """从标准消息中提取所有 `input_text` 文本并拼接。"""
        parts: list[str] = []
        for block in list(message.get("content") or []):
            if not isinstance(block, dict):
                continue
            if str(block.get("type", "") or "").strip() == "input_text":
                text = str(block.get("text", "") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()

    @classmethod
    def _record_to_messages(cls, record: dict[str, object]) -> list[dict[str, Any]]:
        """把历史 turn_record 转成标准消息数组。"""
        messages: list[dict[str, Any]] = []

        user_message = record.get("user_message")
        if isinstance(user_message, dict):
            normalized_content = cls._normalize_user_message(user_message).get("content") or []
            if normalized_content:
                messages.append({"role": "user", "content": normalized_content})

        assistant_message = record.get("assistant_message")
        if isinstance(assistant_message, dict) and str(record.get("turn_status", "completed") or "completed").strip() == "completed":
            assistant_blocks: list[dict[str, Any]] = []
            for block in list(assistant_message.get("content") or []):
                if not isinstance(block, dict):
                    continue
                if str(block.get("type", "") or "").strip() != "output_text":
                    continue
                text = str(block.get("text", "") or "").strip()
                if text:
                    assistant_blocks.append({"type": "output_text", "text": text})
            if assistant_blocks:
                messages.append({"role": "assistant", "content": assistant_blocks})

        return messages

    def build_conversation_context(
        self,
        *,
        state: ConversationState,
        user_message: dict[str, Any],
        options: ConversationBuildOptions,
    ) -> ConversationContext:
        """构建最小会话上下文。"""
        max_messages = max(2, int(options.max_context_messages or (options.history_window * 2)))
        if options.current_turn_id is None:
            selected_records = list(state.turn_records[-max_messages:])
        else:
            selected_records = [
                item
                for item in state.turn_records
                if item.get("turn_id") != options.current_turn_id
            ][-max_messages:]

        conversation: list[dict[str, Any]] = []
        for record in selected_records:
            conversation.extend(self._record_to_messages(record))
        conversation = conversation[-max_messages:]

        normalized_message = self._normalize_user_message(user_message)
        return ConversationContext(
            session=ContextSession(
                session_id=state.session_id,
                session_scene=state.session_scene,
                turn_scene=state.turn_scene,
                profile=options.profile,
            ),
            current=ContextTurn(
                user_message=normalized_message,
            ),
            conversation=conversation,
        )

    @staticmethod
    def _include_history(strategy: Any | None) -> bool:
        """判断 responder 阶段是否需要带入历史消息。"""
        if strategy is None:
            return True
        analysis = dict(getattr(strategy, "analysis", {}) or {})
        policy = dict(analysis.get("prompt_context_policy", {}) or {})
        return bool(policy.get("include_history_messages", True))

    @classmethod
    def _trim_history_artifacts(
        cls,
        conversation: list[dict[str, Any]],
        *,
        state: ConversationState | None = None,
        summarize: bool = False,
    ) -> list[dict[str, Any]]:
        """历史冗余上下文裁剪：历史附件块替换为占位/摘要文本，当前轮附件保持原样。"""
        trimmed: list[dict[str, Any]] = []
        for message in conversation:
            content = message.get("content")
            if not isinstance(content, list):
                trimmed.append(dict(message))
                continue
            new_content: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict) or str(block.get("type", "") or "").strip() not in ARTIFACT_BLOCK_TYPES:
                    new_content.append(block)
                    continue
                block_type = str(block.get("type", "") or "").strip()
                summary = ""
                if summarize and state is not None:
                    artifacts = blocks_to_artifacts([block])
                    analysis = state.memory.cached_or_metadata_block_analysis(artifacts)
                    summary = str(analysis.get("summary", "") or "").strip()
                label = {"input_image": "图片", "input_audio": "音频", "input_file": "文件"}.get(block_type, "附件")
                text = f"[历史{label}摘要] {summary}" if summary else f"[历史{label}附件]"
                new_content.append({"type": "input_text", "text": text})
            if new_content:
                trimmed.append({**message, "content": new_content})
        return trimmed

    @classmethod
    def _flatten_current_artifacts(
        cls,
        state: ConversationState | None,
        user_message: dict[str, Any],
    ) -> dict[str, Any]:
        """当前轮附件块转为缓存视觉/附件分析文本，供纯文本云模型消费。

        原始多模态块已在 turn intake 由端侧视觉分析消费并缓存；
        云侧（text-only）不能直接 fetch 本地/私有 image_url，故编译为分析文本。
        """
        content = user_message.get("content")
        if not isinstance(content, list):
            return dict(user_message)
        new_content: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict) or str(block.get("type", "") or "").strip() not in ARTIFACT_BLOCK_TYPES:
                new_content.append(block)
                continue
            block_type = str(block.get("type", "") or "").strip()
            summary = ""
            if state is not None:
                analysis = state.memory.cached_or_metadata_block_analysis(blocks_to_artifacts([block]))
                summary = str(analysis.get("summary", "") or "").strip()
            label = {"input_image": "图片", "input_audio": "音频", "input_file": "文件"}.get(block_type, "附件")
            text = f"[{label}分析] {summary}" if summary else f"[{label}附件]"
            new_content.append({"type": "input_text", "text": text})
        return {**user_message, "content": new_content}

    def build_router_input(
        self,
        *,
        context: ConversationContext,
    ) -> list[dict[str, Any]]:
        """构造 router 阶段输入消息数组（历史附件裁剪为占位，当前轮保留原始多模态块）。"""
        return [
            *self._trim_history_artifacts(list(context.conversation)),
            dict(context.current.user_message),
        ]

    def build_responder_input(
        self,
        *,
        context: ConversationContext,
        strategy: Any | None,
        state: ConversationState | None = None,
    ) -> list[dict[str, Any]]:
        """构造 responder 阶段输入消息数组（历史附件裁剪为缓存摘要）。"""
        if not self._include_history(strategy):
            return [dict(context.current.user_message)]
        return [
            *self._trim_history_artifacts(list(context.conversation), state=state, summarize=True),
            dict(context.current.user_message),
        ]

    @staticmethod
    def _build_instructions(
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
        strategy: Any | None,
        decision: Any | None,
        task: str,
    ) -> CompiledInstructions:
        """编译当前阶段系统指令。"""
        sections: dict[str, str] = {}
        active_skills: list[str] = []

        if task == "router":
            instructions = build_router_system_prompt(prompt_center)
            sections["router"] = instructions
            return CompiledInstructions(
                phase="router",
                text=instructions,
                sections=sections,
                active_skills=active_skills,
            )

        if strategy is None:
            raise ValueError("responder 阶段缺少 strategy，无法构造正式系统指令")

        prompt_package = build_responder_prompt_package(
            prompt_center=prompt_center,
            strategy=strategy,
        )
        instructions = build_responder_system_prompt(
            prompt_center=prompt_center,
            context=context,
            strategy=strategy,
        )
        sections["responder"] = instructions
        active_skills = [skill.name for skill in prompt_package.skills]
        return CompiledInstructions(
            phase="responder",
            text=instructions,
            sections=sections,
            active_skills=active_skills,
        )

    def compile_router_payload(
        self,
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
        state: ConversationState | None = None,
    ) -> CompiledConversationPayload:
        """编译 router 阶段完整载荷（system + developer runtime + history + user）。"""
        instructions = self._build_instructions(
            prompt_center=prompt_center,
            context=context,
            strategy=None,
            decision=None,
            task="router",
        )
        developer = self._runtime_section(state=state, context=context, profile="router")
        sections = dict(instructions.sections)
        if developer:
            sections["runtime"] = developer
        layered = CompiledContext(
            system=instructions.text,
            developer=developer,
            history=self._trim_history_artifacts(list(context.conversation)),
            user=self._flatten_current_artifacts(state, context.current.user_message),
        )
        return CompiledConversationPayload(
            instructions=layered.render_instructions(),
            input=layered.render_input(),
            context=context,
            sections=sections,
            active_skills=instructions.active_skills,
            layers=layered.to_layers(),
        )

    def compile_responder_payload(
        self,
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
        strategy: Any | None,
        decision: Any | None,
        state: ConversationState | None = None,
    ) -> CompiledConversationPayload:
        """编译 responder 阶段完整载荷（system + developer runtime + history + user）。"""
        instructions = self._build_instructions(
            prompt_center=prompt_center,
            context=context,
            strategy=strategy,
            decision=decision,
            task="responder",
        )
        developer = self._runtime_section(
            state=state,
            context=context,
            profile="responder",
            decision=decision,
            strategy=strategy,
        )
        sections = dict(instructions.sections)
        if developer:
            sections["runtime"] = developer
        history = (
            self._trim_history_artifacts(list(context.conversation), state=state, summarize=True)
            if self._include_history(strategy)
            else []
        )
        layered = CompiledContext(
            system=instructions.text,
            developer=developer,
            history=history,
            user=self._flatten_current_artifacts(state, context.current.user_message),
        )
        return CompiledConversationPayload(
            instructions=layered.render_instructions(),
            input=layered.render_input(),
            context=context,
            sections=sections,
            active_skills=instructions.active_skills,
            layers=layered.to_layers(),
        )

    @staticmethod
    def _runtime_section(
        *,
        state: ConversationState | None,
        context: ConversationContext,
        profile: str,
        decision: Any | None = None,
        strategy: Any | None = None,
    ) -> str:
        if state is None or not settings.runtime.context_runtime_injection:
            return ""
        try:
            payload = build_runtime_payload(
                state=state,
                context=context,
                profile=profile,
                decision=decision,
                strategy=strategy,
            )
            return render_runtime_section(payload)
        except Exception:
            return ""
