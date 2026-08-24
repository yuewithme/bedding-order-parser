"""Provider construction without import-time credential validation."""

from __future__ import annotations

from bedding_order_parser.llm.null_provider import NullLLMProvider
from bedding_order_parser.llm.provider import LLMProvider
from bedding_order_parser.llm.settings import (
    LLMSettings,
    VOLCENGINE_ARK_PROVIDER,
)
from bedding_order_parser.llm.transport import JSONTransport
from bedding_order_parser.llm.volcengine_ark import VolcengineArkProvider


def build_provider(
    settings: LLMSettings,
    *,
    transport: JSONTransport | None = None,
) -> LLMProvider:
    if settings.provider == VOLCENGINE_ARK_PROVIDER:
        return VolcengineArkProvider(settings, transport=transport)
    return NullLLMProvider()
