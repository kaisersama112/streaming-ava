"""上下文模块中的 instructions 组装器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from ava.capabilities.prompt.prompt_builder import (
    PromptCenter,
    build_responder_system_prompt,
    build_router_system_prompt,
)
from ava.multi_turn_context_builder.types import CompiledInstructions, ConversationContext, SkillSelection
from ava.domain.conversation.strategy import BranchStrategy
from ava.router_selector.schema import RouteDecision

if TYPE_CHECKING:
    from ava.capabilities.prompt import PromptCenter as PromptCenterType


@dataclass(frozen=True)
class BuiltinSkillSpec:
    """内置技能片段声明。"""

    skill_id: str
    title: str
    instruction_fragment: str
    phases: tuple[str, ...]
    matcher: Callable[[str, ConversationContext, BranchStrategy | None], bool]

    def is_active(
        self,
        *,
        phase: str,
        context: ConversationContext,
        strategy: BranchStrategy | None = None,
    ) -> bool:
        if phase not in self.phases:
            return False
        return bool(self.matcher(phase, context, strategy))


class PromptPluginSkillProvider:
    """从 `prompt-plugin` 资产中选择技能片段。"""

    _MODE_DEFAULTS = {
        "general_qa": "fact",
        "casual_chat": "smalltalk",
        "clarify": "subject",
    }

    def select(
        self,
        *,
        prompt_center: "PromptCenterType",
        phase: str,
        context: ConversationContext,
        strategy: BranchStrategy | None = None,
    ) -> list[SkillSelection]:
        del context
        if phase != "responder" or strategy is None:
            return []
        if getattr(strategy, "branch", "") == "education":
            return self._select_education_skills(prompt_center, strategy)
        return self._select_mode_skills(prompt_center, strategy)

    def _select_education_skills(
        self,
        prompt_center: "PromptCenterType",
        strategy: BranchStrategy,
    ) -> list[SkillSelection]:
        from ava.capabilities.prompt import EducationPromptCatalog

        catalog = EducationPromptCatalog(prompt_center)
        module = str(strategy.module or "solve").strip() or "solve"
        subject = str(strategy.subject or "general").strip() or "general"
        pedagogy = str(strategy.pedagogy or "step_by_step").strip() or "step_by_step"
        assets = catalog.load_assets(
            module=module,
            subject=subject,
            pedagogy=pedagogy,
        )
        plugin = assets.branch
        module_spec = assets.module
        subject_spec = assets.subject
        pedagogy_spec = assets.pedagogy
        return [
            SkillSelection(
                skill_id="plugin.education",
                title=f"Plugin 路径 {plugin.name}",
                instruction_fragment=self._plugin_fragment(plugin.purpose, plugin.rules),
                source_kind="prompt_plugin",
                source_path="prompt-plugin/education/branch.md",
            ),
            SkillSelection(
                skill_id=f"module.education.{module_spec.asset_id}",
                title=f"Module 路径 {module_spec.name}",
                instruction_fragment=self._module_fragment(module_spec),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/education/modules/{module_spec.asset_id}.md",
            ),
            SkillSelection(
                skill_id=f"subject.education.{subject_spec.asset_id}",
                title=f"Subject 路径 {subject_spec.name}",
                instruction_fragment=self._subject_fragment(subject_spec),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/education/subjects/{subject_spec.asset_id}.md",
            ),
            SkillSelection(
                skill_id=f"pedagogy.education.{pedagogy_spec.asset_id}",
                title=f"Pedagogy 路径 {pedagogy_spec.name}",
                instruction_fragment=self._pedagogy_fragment(pedagogy_spec),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/education/pedagogies/{pedagogy_spec.asset_id}.md",
            ),
        ]

    def _select_mode_skills(
        self,
        prompt_center: "PromptCenterType",
        strategy: BranchStrategy,
    ) -> list[SkillSelection]:
        from ava.capabilities.prompt import BranchPromptRuntime

        branch = str(strategy.branch or "").strip()
        if not branch:
            return []
        runtime = BranchPromptRuntime(prompt_center)
        plugin = runtime.load_plugin(branch)
        mode = str(strategy.mode or self._MODE_DEFAULTS.get(branch, "fact")).strip() or self._MODE_DEFAULTS.get(branch, "fact")
        mode_spec = runtime.load_mode(branch, mode)
        return [
            SkillSelection(
                skill_id=f"plugin.{branch}",
                title=f"Plugin 路径 {plugin.name}",
                instruction_fragment=self._plugin_fragment(plugin.purpose, plugin.rules),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/plugins/{branch}/plugin.md",
            ),
            SkillSelection(
                skill_id=f"mode.{branch}.{mode_spec.asset_id}",
                title=f"Mode 路径 {mode_spec.name}",
                instruction_fragment=self._mode_fragment(mode_spec),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/plugins/{branch}/modes/{mode_spec.asset_id}.md",
            ),
        ]

    @staticmethod
    def _join_bullets(items: tuple[str, ...] | list[str], *, prefix: str = "- ") -> str:
        return "\n".join(f"{prefix}{item}" for item in items if str(item).strip())

    def _plugin_fragment(self, purpose: str, rules: tuple[str, ...]) -> str:
        blocks = [f"Purpose: {purpose.strip()}"] if str(purpose).strip() else []
        if rules:
            blocks.append("Rules:\n" + self._join_bullets(rules))
        return "\n".join(blocks).strip()

    def _module_fragment(self, spec) -> str:
        blocks: list[str] = []
        if spec.goal:
            blocks.append(f"Goal: {spec.goal}")
        if spec.applies_to:
            blocks.append("Applies to: " + " / ".join(spec.applies_to))
        if spec.response_structure:
            blocks.append("Response structure: " + " / ".join(spec.response_structure))
        if spec.global_rules:
            blocks.append("Global rules:\n" + self._join_bullets(spec.global_rules))
        if spec.interaction_policy:
            blocks.append("Interaction policy:\n" + self._join_bullets(spec.interaction_policy))
        if spec.instructions:
            blocks.append("Instructions:\n" + self._join_bullets(spec.instructions))
        return "\n\n".join(blocks).strip()

    def _subject_fragment(self, spec) -> str:
        blocks: list[str] = []
        if spec.focus:
            blocks.append("Focus: " + " / ".join(spec.focus))
        if spec.explanation_strategy:
            blocks.append("Explanation strategy: " + " / ".join(spec.explanation_strategy))
        if spec.evidence_preference:
            blocks.append("Evidence preference: " + " / ".join(spec.evidence_preference))
        if spec.common_mistakes:
            blocks.append("Common mistakes:\n" + self._join_bullets(spec.common_mistakes))
        if spec.instructions:
            blocks.append("Instructions:\n" + self._join_bullets(spec.instructions))
        return "\n\n".join(blocks).strip()

    def _pedagogy_fragment(self, spec) -> str:
        blocks: list[str] = []
        if spec.tone:
            blocks.append(f"Tone: {spec.tone}")
        if spec.constraints:
            blocks.append("Constraints:\n" + self._join_bullets(spec.constraints))
        if spec.output_adjustments:
            blocks.append(
                "Output adjustments:\n"
                + self._join_bullets([f"{key} = {value}" for key, value in dict(spec.output_adjustments).items()])
            )
        if spec.instructions:
            blocks.append("Instructions:\n" + self._join_bullets(spec.instructions))
        return "\n\n".join(blocks).strip()

    def _mode_fragment(self, spec) -> str:
        blocks: list[str] = []
        if spec.description:
            blocks.append(f"Description: {spec.description}")
        if spec.objective:
            blocks.append(f"Objective: {spec.objective}")
        if spec.response_shape:
            blocks.append(f"Response shape: {spec.response_shape}")
        if spec.instructions:
            blocks.append("Instructions:\n" + self._join_bullets(spec.instructions))
        if spec.interaction_rules:
            blocks.append("Interaction rules:\n" + self._join_bullets(spec.interaction_rules))
        return "\n\n".join(blocks).strip()


class InstructionSkillRegistry:
    """选择当前阶段生效的内置技能与 prompt-plugin 技能。"""

    def __init__(
        self,
        skills: list[BuiltinSkillSpec] | None = None,
        prompt_plugin_provider: PromptPluginSkillProvider | None = None,
    ) -> None:
        self.skills = skills or self._default_skills()
        self.prompt_plugin_provider = prompt_plugin_provider or PromptPluginSkillProvider()

    def select(
        self,
        *,
        prompt_center: "PromptCenterType",
        phase: str,
        context: ConversationContext,
        strategy: BranchStrategy | None = None,
    ) -> list[SkillSelection]:
        selected: list[SkillSelection] = []
        for skill in self.skills:
            if skill.is_active(phase=phase, context=context, strategy=strategy):
                selected.append(
                    SkillSelection(
                        skill_id=skill.skill_id,
                        title=skill.title,
                        instruction_fragment=skill.instruction_fragment,
                        source_kind="builtin",
                    )
                )
        selected.extend(
            self.prompt_plugin_provider.select(
                prompt_center=prompt_center,
                phase=phase,
                context=context,
                strategy=strategy,
            )
        )
        return selected

    @staticmethod
    def _default_skills() -> list[BuiltinSkillSpec]:
        return [
            BuiltinSkillSpec(
                skill_id="teaching_continuity",
                title="教学连续性",
                instruction_fragment=(
                    "Preserve teaching continuity when the current turn is a follow-up. "
                    "Prefer continuing the same learning object unless the current input clearly switches topic."
                ),
                phases=("router", "responder"),
                matcher=lambda _phase, context, strategy: (
                    context.session.session_scene == "education"
                    or context.session.turn_scene == "education"
                    or (strategy is not None and getattr(strategy, "branch", "") == "education")
                ),
            ),
            BuiltinSkillSpec(
                skill_id="multimodal_grounding",
                title="多模态对齐",
                instruction_fragment=(
                    "Ground decisions and answers in the provided multimodal artifacts. "
                    "Do not ignore images, audio, video, or referenced files when they are present."
                ),
                phases=("router", "responder"),
                matcher=lambda _phase, context, _strategy: bool(context.current.artifacts),
            ),
            BuiltinSkillSpec(
                skill_id="artifact_followup",
                title="附件追问延续",
                instruction_fragment=(
                    "When the current turn follows up on a previously analyzed artifact, "
                    "reuse the structured artifact understanding and re-read the original media only if necessary."
                ),
                phases=("responder",),
                matcher=lambda _phase, context, _strategy: False,
            ),
            BuiltinSkillSpec(
                skill_id="history_grounding",
                title="历史对话对齐",
                instruction_fragment=(
                    "Use recent conversation history to resolve short follow-ups, pronouns, and omitted context. "
                    "Do not ask the user to repeat context that is already available."
                ),
                phases=("router", "responder"),
                matcher=lambda _phase, context, _strategy: bool(context.conversation),
            ),
        ]


class InstructionsCompiler:
    """编译模型使用的高优先级 instructions。"""

    def __init__(self, skill_registry: InstructionSkillRegistry | None = None) -> None:
        self.skill_registry = skill_registry or InstructionSkillRegistry()

    def compile_router(
        self,
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
    ) -> CompiledInstructions:
        """编译 router 阶段 instructions。"""
        base_prompt = build_router_system_prompt(prompt_center)
        active_skills = self.skill_registry.select(
            prompt_center=prompt_center,
            phase="router",
            context=context,
            strategy=None,
        )
        text = self._assemble_text(
            base_prompt=base_prompt,
            active_skills=active_skills,
        )
        return CompiledInstructions(
            phase="router",
            text=text,
            active_skills=[item.skill_id for item in active_skills],
            sections={
                "base_prompt": base_prompt,
                "active_skills": [item.skill_id for item in active_skills],
                "skill_sources": [
                    {
                        "skill_id": item.skill_id,
                        "source_kind": item.source_kind,
                        "source_path": item.source_path,
                    }
                    for item in active_skills
                ],
            },
        )

    def compile_responder(
        self,
        *,
        prompt_center: PromptCenter,
        context: ConversationContext,
        strategy: BranchStrategy,
        decision: RouteDecision | None,
    ) -> CompiledInstructions:
        """编译 responder 阶段 instructions。"""
        base_prompt = build_responder_system_prompt(
            prompt_center=prompt_center,
            context=context,
            strategy=strategy,
        )
        active_skills = self.skill_registry.select(
            prompt_center=prompt_center,
            phase="responder",
            context=context,
            strategy=strategy,
        )
        text = self._assemble_text(
            base_prompt=base_prompt,
            active_skills=active_skills,
        )
        return CompiledInstructions(
            phase="responder",
            text=text,
            active_skills=[item.skill_id for item in active_skills],
            sections={
                "base_prompt": base_prompt,
                "active_skills": [item.skill_id for item in active_skills],
                "skill_sources": [
                    {
                        "skill_id": item.skill_id,
                        "source_kind": item.source_kind,
                        "source_path": item.source_path,
                    }
                    for item in active_skills
                ],
                "strategy_id": strategy.strategy_id,
                "decision": (decision.model_dump() if decision is not None else {}),
            },
        )

    @staticmethod
    def _assemble_text(
        *,
        base_prompt: str,
        active_skills: list[SkillSelection],
    ) -> str:
        blocks: list[str] = []
        if base_prompt.strip():
            blocks.append(base_prompt.strip())
        if active_skills:
            blocks.append(
                "Active skills:\n" + "\n".join(
                    f"- {item.title}: {item.instruction_fragment}"
                    for item in active_skills
                )
            )
        return "\n\n".join(block for block in blocks if block).strip()
