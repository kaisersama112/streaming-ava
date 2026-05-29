"""Prompt capability facade."""

from .branch_runtime import BranchPromptRuntime
from .factories import build_prompt_center
from .education_catalog import EducationPromptAssets, EducationPromptCatalog
from .education_runtime import EducationPromptRuntime
from .prompt_builder import (
    build_responder_system_prompt,
    build_router_system_prompt,
    build_router_user_message,
)
from .prompt_config import PromptCenterConfig
from .prompt_loader import PromptCenter
from .prompt_runtime import ModeSpec, ModuleSpec, PedagogySpec, PluginSpec, SubjectSpec

__all__ = [
    "BranchPromptRuntime",
    "EducationPromptAssets",
    "EducationPromptCatalog",
    "EducationPromptRuntime",
    "ModeSpec",
    "ModuleSpec",
    "PedagogySpec",
    "PromptCenter",
    "PromptCenterConfig",
    "PluginSpec",
    "SubjectSpec",
    "build_prompt_center",
    "build_responder_system_prompt",
    "build_router_system_prompt",
    "build_router_user_message",
]
