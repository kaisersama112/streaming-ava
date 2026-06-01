"""Prompt capability facade."""

from .factories import build_prompt_center
from .loaders import BranchPromptLoader, EducationPromptAssets, EducationPromptLoader, PromptSkillAsset
from .parsers import MarkdownAsset
from .prompt_builder import (
    build_responder_system_prompt,
    build_router_system_prompt,
    build_router_user_message,
)
from .prompt_config import PromptCenterConfig
from .prompt_loader import PromptCenter
from .specs import (
    BranchSpec,
    ModeSpec,
    ModuleSpec,
    PedagogySpec,
    PromptReferenceEntry,
    PromptSkillCard,
    SubjectSpec,
)

__all__ = [
    "BranchPromptLoader",
    "BranchSpec",
    "EducationPromptAssets",
    "EducationPromptLoader",
    "MarkdownAsset",
    "ModeSpec",
    "ModuleSpec",
    "PedagogySpec",
    "PromptCenter",
    "PromptCenterConfig",
    "PromptReferenceEntry",
    "PromptSkillAsset",
    "PromptSkillCard",
    "SubjectSpec",
    "build_prompt_center",
    "build_responder_system_prompt",
    "build_router_system_prompt",
    "build_router_user_message",
]
