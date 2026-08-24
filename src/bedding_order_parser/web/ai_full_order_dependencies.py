"""Desktop composition for the optional Ark whole-order provider."""

from __future__ import annotations

from bedding_order_parser.ai_full_order.contracts import V2_CONTRACT_VERSION
from bedding_order_parser.ai_full_order.downstream import DictionaryValidator, MaterialMatcher
from bedding_order_parser.ai_full_order.volcengine_ark import VolcengineArkFullOrderProvider
from bedding_order_parser.llm.settings import LLMSettings
from bedding_order_parser.llm.transport import JSONTransport
from bedding_order_parser.web.ai_full_order_service import AIEnhancedDependencies


def build_ai_enhanced_dependencies(
    *,
    dictionary_validator: DictionaryValidator | None = None,
    material_matcher: MaterialMatcher | None = None,
    downstream_factory=None,
    settings: LLMSettings | None = None,
    transport: JSONTransport | None = None,
    max_logical_calls: int = 12,
) -> AIEnhancedDependencies | None:
    """Build the production provider only when all local execution ports are ready."""
    resolved = settings or LLMSettings.from_environment()
    direct_downstream = dictionary_validator is not None and material_matcher is not None
    factory_ready = downstream_factory is not None and bool(
        getattr(downstream_factory, "is_ready", lambda: True)()
    )
    if not resolved.is_ready() or (not direct_downstream and not factory_ready):
        return None
    provider = VolcengineArkFullOrderProvider(resolved, transport=transport)
    return AIEnhancedDependencies(
        provider=provider,
        dictionary_validator=dictionary_validator,
        material_matcher=material_matcher,
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        max_logical_calls=max_logical_calls,
        contract_version=V2_CONTRACT_VERSION,
        downstream_factory=downstream_factory,
    )
