"""旧 instructions 入口，转发到 `ava.multi_turn_context_builder.instructions`。"""

from ava.multi_turn_context_builder.instructions import (
    BuiltinSkillSpec,
    InstructionSkillRegistry,
    InstructionsCompiler,
    PromptPluginSkillProvider,
)

__all__ = [
    "BuiltinSkillSpec",
    "InstructionSkillRegistry",
    "InstructionsCompiler",
    "PromptPluginSkillProvider",
]
