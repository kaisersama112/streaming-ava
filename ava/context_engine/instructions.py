"""Compiled high-priority instruction assembly for context-engine phases."""

from __future__ import annotations

import json

from ava.capabilities.prompt.prompt_builder import (
    PromptCenter,
    build_responder_system_prompt,
    build_router_system_prompt,
)
from ava.context_engine.skills import SkillRegistry
from ava.context_engine.types import CompiledInstructions, ContextSnapshot
from ava.domain.conversation.strategy import BranchStrategy
from ava.domain.routing.schema import RouteDecision


class InstructionsCompiler:
    """Compile system-grade instructions from prompt shells, skills, and runtime."""

    def __init__(self, skill_registry: SkillRegistry | None = None) -> None:
        self.skill_registry = skill_registry or SkillRegistry()

    def compile_router(
        self,
        *,
        prompt_center: PromptCenter,
        snapshot: ContextSnapshot,
        runtime_context: dict,
    ) -> CompiledInstructions:
        """Compile router-phase instructions."""

        base_prompt = build_router_system_prompt(prompt_center)
        active_skills = self.skill_registry.select(
            prompt_center=prompt_center,
            phase="router",
            snapshot=snapshot,
            strategy=None,
        )
        text = self._assemble_text(
            base_prompt=base_prompt,
            active_skills=active_skills,
            runtime_context=runtime_context,
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
        snapshot: ContextSnapshot,
        strategy: BranchStrategy,
        decision: RouteDecision | None,
        runtime_context: dict,
    ) -> CompiledInstructions:
        """Compile responder-phase instructions."""

        base_prompt = build_responder_system_prompt(
            prompt_center=prompt_center,
            snapshot=snapshot,
            strategy=strategy,
        )
        active_skills = self.skill_registry.select(
            prompt_center=prompt_center,
            phase="responder",
            snapshot=snapshot,
            strategy=strategy,
        )
        text = self._assemble_text(
            base_prompt=base_prompt,
            active_skills=active_skills,
            runtime_context=runtime_context,
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
        active_skills,
        runtime_context: dict,
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
        blocks.append(
            "Compiled runtime context (JSON, internal only):\n"
            + json.dumps(runtime_context, ensure_ascii=False)
        )
        return "\n\n".join(block for block in blocks if block).strip()
