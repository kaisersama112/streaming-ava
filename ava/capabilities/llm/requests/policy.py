from ava.capabilities.llm.types import InferenceTask, LLMContext
from configs import settings


def resolve_model(context: LLMContext) -> str:
    override = str((context.metadata or {}).get("model_override", "") or "").strip()
    if override:
        return override
    if context.task == InferenceTask.ROUTE:
        chosen = str((context.routing or {}).get("chosen_model", "") or "").strip()
        if chosen:
            return chosen
        return str(settings.runtime.router_model or settings.openai_config.model or settings.openai_config.intent_model).strip()

    has_multimodal = bool((context.multimodal or {}).get("artifacts_count", 0) or (context.multimodal or {}).get("reference_artifacts_count", 0))
    if has_multimodal:
        return str(settings.openai_config.multimodal_model or settings.openai_config.model).strip()
    return str(settings.openai_config.model or settings.openai_config.multimodal_model).strip()


def resolve_timeout(context: LLMContext) -> int:
    override = (context.metadata or {}).get("timeout")
    if override is not None:
        return int(override)
    if context.task == InferenceTask.ROUTE:
        return int(settings.runtime.router_timeout or settings.openai_config.intent_timeout or settings.openai_config.timeout)
    return int(settings.openai_config.timeout or 60)


def resolve_temperature(context: LLMContext) -> float:
    if context.task == InferenceTask.ROUTE:
        return 0.1
    return 0.7

