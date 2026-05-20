"""Standard skill registry for context-compiler instruction assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Callable

from ava.context_engine.types import ContextSnapshot, SkillSelection
from ava.domain.conversation.strategy import BranchStrategy

if TYPE_CHECKING:
    from ava.capabilities.prompt import PromptCenter


@dataclass(frozen=True)
class BuiltinSkillSpec:
    """Declarative built-in skill fragment activated at compile time."""

    skill_id: str
    title: str
    instruction_fragment: str
    phases: tuple[str, ...]
    matcher: Callable[[str, ContextSnapshot, BranchStrategy | None], bool]

    def is_active(
        self,
        *,
        phase: str,
        snapshot: ContextSnapshot,
        strategy: BranchStrategy | None = None,
    ) -> bool:
        if phase not in self.phases:
            return False
        return bool(self.matcher(phase, snapshot, strategy))


class PromptPluginSkillProvider:
    """Load standard skills from `prompt-plugin/plugins` markdown assets."""

    _MODE_DEFAULTS = {
        "general_qa": "fact",
        "casual_chat": "smalltalk",
        "clarify": "subject",
    }

    def select(
        self,
        *,
        prompt_center: "PromptCenter",
        phase: str,
        snapshot: ContextSnapshot,
        strategy: BranchStrategy | None = None,
    ) -> list[SkillSelection]:
        del snapshot
        if phase != "responder" or strategy is None:
            return []
        if getattr(strategy, "branch", "") == "education":
            return self._select_education_skills(prompt_center, strategy)
        return self._select_mode_skills(prompt_center, strategy)

    def _select_education_skills(
        self,
        prompt_center: "PromptCenter",
        strategy: BranchStrategy,
    ) -> list[SkillSelection]:
        from ava.capabilities.prompt import ComposedPromptRuntime

        runtime = ComposedPromptRuntime(prompt_center)
        module = str(strategy.module or "solve").strip() or "solve"
        subject = str(strategy.subject or "general").strip() or "general"
        style = str(strategy.style or "step_by_step").strip() or "step_by_step"
        plugin = runtime.load_plugin()
        module_spec = runtime.load_module(module)
        subject_spec = runtime.load_subject(module, subject)
        style_spec = runtime.load_style(module, style)
        return [
            SkillSelection(
                skill_id="plugin.education",
                title=f"Plugin · {plugin.name}",
                instruction_fragment=self._plugin_fragment(plugin.purpose, plugin.rules),
                source_kind="prompt_plugin",
                source_path="prompt-plugin/plugins/education/plugin.md",
            ),
            SkillSelection(
                skill_id=f"module.education.{module_spec.asset_id}",
                title=f"Module · {module_spec.name}",
                instruction_fragment=self._module_fragment(module_spec),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/plugins/education/modules/{module_spec.asset_id}/module.md",
            ),
            SkillSelection(
                skill_id=f"subject.education.{module_spec.asset_id}.{subject_spec.asset_id}",
                title=f"Subject · {subject_spec.name}",
                instruction_fragment=self._subject_fragment(subject_spec),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/plugins/education/modules/{module_spec.asset_id}/subjects/{subject_spec.asset_id}.md",
            ),
            SkillSelection(
                skill_id=f"style.education.{module_spec.asset_id}.{style_spec.asset_id}",
                title=f"Style · {style_spec.name}",
                instruction_fragment=self._style_fragment(style_spec),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/plugins/education/modules/{module_spec.asset_id}/styles/{style_spec.asset_id}.md",
            ),
        ]

    def _select_mode_skills(
        self,
        prompt_center: "PromptCenter",
        strategy: BranchStrategy,
    ) -> list[SkillSelection]:
        from ava.capabilities.prompt import SimpleBranchPromptRuntime

        branch = str(strategy.branch or "").strip()
        if not branch:
            return []
        runtime = SimpleBranchPromptRuntime(prompt_center)
        plugin = runtime.load_plugin(branch)
        mode = str(strategy.mode or self._MODE_DEFAULTS.get(branch, "fact")).strip() or self._MODE_DEFAULTS.get(branch, "fact")
        mode_spec = runtime.load_mode(branch, mode)
        return [
            SkillSelection(
                skill_id=f"plugin.{branch}",
                title=f"Plugin · {plugin.name}",
                instruction_fragment=self._plugin_fragment(plugin.purpose, plugin.rules),
                source_kind="prompt_plugin",
                source_path=f"prompt-plugin/plugins/{branch}/plugin.md",
            ),
            SkillSelection(
                skill_id=f"mode.{branch}.{mode_spec.asset_id}",
                title=f"Mode · {mode_spec.name}",
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

    def _style_fragment(self, spec) -> str:
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


class SkillRegistry:
    """Select active built-in and prompt-plugin skills."""

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
        prompt_center: "PromptCenter",
        phase: str,
        snapshot: ContextSnapshot,
        strategy: BranchStrategy | None = None,
    ) -> list[SkillSelection]:
        selected: list[SkillSelection] = []
        for skill in self.skills:
            if skill.is_active(phase=phase, snapshot=snapshot, strategy=strategy):
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
                snapshot=snapshot,
                strategy=strategy,
            )
        )
        return selected

    @staticmethod
    def _default_skills() -> list[BuiltinSkillSpec]:
        return [
            BuiltinSkillSpec(
                skill_id="teaching_continuity",
                title="Teaching Continuity",
                instruction_fragment=(
                    "Preserve teaching continuity when the current turn is a follow-up. "
                    "Prefer continuing the same learning object unless the current input clearly switches topic."
                ),
                phases=("router", "responder"),
                matcher=lambda _phase, snapshot, strategy: (
                    snapshot.session_scene == "education"
                    or snapshot.turn_scene == "education"
                    or (strategy is not None and getattr(strategy, "branch", "") == "education")
                ),
            ),
            BuiltinSkillSpec(
                skill_id="multimodal_grounding",
                title="Multimodal Grounding",
                instruction_fragment=(
                    "Ground decisions and answers in the provided multimodal artifacts. "
                    "Do not ignore images, audio, video, or referenced files when they are present."
                ),
                phases=("router", "responder"),
                matcher=lambda _phase, snapshot, _strategy: bool(snapshot.artifacts or snapshot.reference_artifacts),
            ),
            BuiltinSkillSpec(
                skill_id="artifact_followup",
                title="Artifact Follow-up",
                instruction_fragment=(
                    "When the current turn follows up on a previously analyzed artifact, "
                    "reuse the structured artifact understanding and re-read the original media only if necessary."
                ),
                phases=("responder",),
                matcher=lambda _phase, snapshot, _strategy: bool(
                    dict(getattr(snapshot, "router_artifact_brief", {}) or {}).get(
                        "followup_requires_visual_reread",
                        False,
                    )
                ),
            ),
            BuiltinSkillSpec(
                skill_id="memory_personalization",
                title="Memory Personalization",
                instruction_fragment=(
                    "Use stable user memory only when it improves relevance, tone, or continuity. "
                    "Do not overfit to memory when the current request clearly asks for something else."
                ),
                phases=("router", "responder"),
                matcher=lambda _phase, snapshot, _strategy: bool(
                    dict(dict(getattr(snapshot, "memory_projection", {}) or {}).get("facts") or {})
                ),
            ),
            BuiltinSkillSpec(
                skill_id="history_grounding",
                title="History Grounding",
                instruction_fragment=(
                    "Use recent conversation history to resolve short follow-ups, pronouns, and omitted context. "
                    "Do not ask the user to repeat context that is already available."
                ),
                phases=("router", "responder"),
                matcher=lambda _phase, snapshot, _strategy: bool(snapshot.history_messages),
            ),
        ]
