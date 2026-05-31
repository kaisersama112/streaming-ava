"""多轮上下文构造主实现。"""

from __future__ import annotations

from typing import Any

from ava.capabilities.prompt import PromptCenter
from ava.domain.conversation.state import ConversationState

from .types import (
    CompiledConversationPayload,
    CompiledInstructions,
    ContextSession,
    ContextTurn,
    ConversationBuildOptions,
    ConversationContext,
)


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
    - 不再负责 `TurnInput` 到上下文的正式转换

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
        """从标准消息中提取所有 `input_text` 文本并拼接。

        参数：
        - message：标准消息对象，通常为 user message

        返回：
        - `str`：拼接后的纯文本；若不存在文本块则返回空字符串
        """
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

        if messages:
            return messages

        # 仅用于迁移旧存档：当历史记录尚未完成标准消息化时，临时从旧字段恢复。
        user_blocks: list[dict[str, Any]] = []
        user_text = cls._text_block(str(record.get("user_text", "") or ""))
        if user_text is not None:
            user_blocks.append(user_text)

        for item in list(record.get("artifacts") or []):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "file") or "file").strip()
            name = str(item.get("name", "") or "").strip()
            summary = str(item.get("summary", "") or "").strip()
            label = f"[{kind}] {name}".strip()
            if summary and summary != name:
                label = f"{label}: {summary}" if label else summary
            if label:
                user_blocks.append({"type": "input_text", "text": label})

        if not user_blocks:
            fallback = cls._text_block(str(record.get("multimodal_summary", "") or ""))
            if fallback is not None:
                user_blocks.append(fallback)

        if user_blocks:
            messages.append({"role": "user", "content": user_blocks})

        if str(record.get("turn_status", "completed") or "completed").strip() == "completed":
            assistant_text = cls._text_block(str(record.get("assistant_text", "") or ""), output=True)
            if assistant_text is not None:
                messages.append({"role": "assistant", "content": [assistant_text]})

        return messages

    def build_conversation_context(
        self,
        *,
        state: ConversationState,
        user_message: dict[str, Any],
        options: ConversationBuildOptions,
    ) -> ConversationContext:
        """构建最小会话上下文。

        参数：
        - state：当前会话状态对象，提供历史轮次、会话场景等信息
        - user_message：当前轮标准 user message
        - options：上下文构建选项，控制历史窗口、当前轮编号、profile 等

        返回：
        - `ConversationContext`：
          - `session`：当前会话级元信息
          - `current`：当前轮最小输入信息
          - `conversation`：截断后的可见历史消息数组
        """

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
        """判断 responder 阶段是否需要带入历史消息。

        参数：
        - strategy：当前轮策略对象；允许为 `None`

        返回：
        - `bool`：
          - `True`：在 responder `input` 中包含历史消息
          - `False`：只保留当前轮 user message
        """
        if strategy is None:
            return True
        analysis = dict(getattr(strategy, "analysis", {}) or {})
        policy = dict(analysis.get("prompt_context_policy", {}) or {})
        return bool(policy.get("include_history_messages", True))

    def build_router_input(
        self,
        *,
        context: ConversationContext,
    ) -> list[dict[str, Any]]:
        """构造 router 使用的 `input` 消息数组。

        参数：
        - context：当前轮会话上下文

        返回：
        - `list[dict[str, Any]]`：
          按对话顺序排列的消息数组，内容为：
          - 可见历史消息
          - 当前轮 user message
        """

        messages = list(context.conversation)
        messages.append(dict(context.current.user_message))
        return messages

    def build_responder_input(
        self,
        *,
        context: ConversationContext,
        strategy: Any | None = None,
    ) -> list[dict[str, Any]]:
        """构造 responder 使用的 `input` 消息数组。

        参数：
        - context：当前轮会话上下文
        - strategy：当前轮策略对象；用于决定是否携带历史消息

        返回：
        - `list[dict[str, Any]]`：
          responder 阶段传给模型的消息数组
        """

        messages: list[dict[str, Any]] = []
        if self._include_history(strategy):
            messages.extend(context.conversation)
        messages.append(dict(context.current.user_message))
        return messages

    @staticmethod
    def _safe_get(prompt_center: PromptCenter, name: str) -> str:
        """安全读取 prompt 文本。

        参数：
        - prompt_center：Prompt 管理中心
        - name：prompt 名称

        返回：
        - `str`：读取成功时返回 prompt 文本；失败时返回空字符串
        """
        try:
            return str(prompt_center.get(name) or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _render_resolved_prompt_spec(prompt_center: PromptCenter, strategy: Any) -> tuple[str, dict[str, Any]]:
        """渲染策略解析后的 prompt 规范。

        参数：
        - prompt_center：Prompt 管理中心
        - strategy：当前轮策略对象，内部应包含 `resolved_prompt_spec`

        返回：
        - `tuple[str, dict[str, Any]]`：
          - 第一个值：渲染后的完整 prompt 文本
          - 第二个值：渲染过程附加信息，例如已渲染路径列表
        """

        spec = getattr(strategy, "resolved_prompt_spec", None)
        if spec is None:
            return "", {}

        variables = dict(getattr(spec, "variables", {}) or {})
        blocks: list[str] = []
        rendered_paths: list[str] = []

        for path in tuple(getattr(spec, "base_files", ()) or ()):
            rendered = str(prompt_center.render_path(path, variables) or "").strip()
            if rendered:
                blocks.append(rendered)
                rendered_paths.append(path)

        contract_file = str(getattr(spec, "contract_file", "") or "").strip()
        if contract_file:
            rendered = str(prompt_center.render_path(contract_file, variables) or "").strip()
            if rendered:
                blocks.append(rendered)
                rendered_paths.append(contract_file)

        renderer_file = str(getattr(spec, "renderer_file", "") or "").strip()
        if renderer_file:
            rendered = str(prompt_center.render_path(renderer_file, variables) or "").strip()
            if rendered:
                blocks.append(rendered)
                rendered_paths.append(renderer_file)

        return "\n\n".join(item for item in blocks if item).strip(), {"rendered_paths": rendered_paths}

    @staticmethod
    def _profile_lines(context: ConversationContext, strategy: Any | None) -> str:
        """生成当前轮上下文摘要文本，追加到 instructions。

        参数：
        - context：当前轮会话上下文
        - strategy：当前轮策略对象；允许为 `None`

        返回：
        - `str`：适合直接拼接进 instructions 的 profile 文本
        """

        lines = [
            "Current turn context:",
            f"- session_scene = {context.session.session_scene}",
            f"- turn_scene = {context.session.turn_scene}",
            f"- profile = {context.session.profile}",
        ]
        current_user_text = self._message_user_text(context.current.user_message)
        if current_user_text:
            lines.append(f"- current_user_text = {current_user_text}")
        if strategy is not None:
            branch = str(getattr(strategy, "branch", "") or "").strip()
            strategy_id = str(getattr(strategy, "strategy_id", "") or "").strip()
            if branch:
                lines.append(f"- branch = {branch}")
            if strategy_id:
                lines.append(f"- strategy_id = {strategy_id}")
            for field_name in ("mode", "module", "subject", "pedagogy", "delivery_mode", "ui_mode"):
                value = str(getattr(strategy, field_name, "") or "").strip()
                if value:
                    lines.append(f"- {field_name} = {value}")
        return "\n".join(lines).strip()

    def compile_router_instructions(
        self,
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
    ) -> CompiledInstructions:
        """编译 router 阶段的 instructions。

        参数：
        - prompt_center：Prompt 管理中心
        - context：当前轮会话上下文

        返回：
        - `CompiledInstructions`：router 阶段的指令编译结果
        """

        base_prompt = self._safe_get(prompt_center, "router")
        profile = self._profile_lines(context, strategy=None)
        text = "\n\n".join(item for item in (base_prompt, profile) if item).strip()
        return CompiledInstructions(
            phase="router",
            text=text,
            active_skills=[],
            sections={"base_prompt": base_prompt},
        )

    def compile_responder_instructions(
        self,
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
        strategy: Any | None = None,
        decision: Any | None = None,
    ) -> CompiledInstructions:
        """编译 responder 阶段的 instructions。

        参数：
        - prompt_center：Prompt 管理中心
        - context：当前轮会话上下文
        - strategy：当前轮策略对象；允许为 `None`
        - decision：当前轮路由决策；允许为 `None`

        返回：
        - `CompiledInstructions`：responder 阶段的指令编译结果
        """

        rendered_prompt, render_sections = self._render_resolved_prompt_spec(prompt_center, strategy)
        fallback_prompt = self._safe_get(prompt_center, "responder")
        profile = self._profile_lines(context, strategy=strategy)
        decision_section = {}
        if decision is not None and hasattr(decision, "model_dump"):
            decision_section = decision.model_dump()

        text = "\n\n".join(item for item in (rendered_prompt or fallback_prompt, profile) if item).strip()
        return CompiledInstructions(
            phase="responder",
            text=text,
            active_skills=[],
            sections={
                "base_prompt": rendered_prompt or fallback_prompt,
                "render": render_sections,
                "decision": decision_section,
            },
        )

    def compile_router_payload(
        self,
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
    ) -> CompiledConversationPayload:
        """编译 router 阶段完整请求载荷。

        参数：
        - prompt_center：Prompt 管理中心
        - context：当前轮会话上下文

        返回：
        - `CompiledConversationPayload`：
          - `instructions`：router 指令文本
          - `input`：router 消息数组
          - `context`：本轮上下文对象
        """
        compiled = self.compile_router_instructions(
            prompt_center=prompt_center,
            context=context,
        )
        return CompiledConversationPayload(
            instructions=compiled.text,
            input=self.build_router_input(context=context),
            context=context,
            active_skills=list(compiled.active_skills),
            sections=dict(compiled.sections or {}),
        )

    def compile_responder_payload(
        self,
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
        strategy: Any | None = None,
        decision: Any | None = None,
    ) -> CompiledConversationPayload:
        """编译 responder 阶段完整请求载荷。

        参数：
        - prompt_center：Prompt 管理中心
        - context：当前轮会话上下文
        - strategy：当前轮策略对象；允许为 `None`
        - decision：当前轮路由决策；允许为 `None`

        返回：
        - `CompiledConversationPayload`：
          - `instructions`：responder 指令文本
          - `input`：responder 消息数组
          - `context`：本轮上下文对象
        """
        compiled = self.compile_responder_instructions(
            prompt_center=prompt_center,
            context=context,
            strategy=strategy,
            decision=decision,
        )
        return CompiledConversationPayload(
            instructions=compiled.text,
            input=self.build_responder_input(context=context, strategy=strategy),
            context=context,
            active_skills=list(compiled.active_skills),
            sections=dict(compiled.sections or {}),
        )
