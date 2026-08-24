from __future__ import annotations

import pytest

from bedding_order_parser.llm.factory import build_provider
from bedding_order_parser.llm.null_provider import NullLLMProvider
from bedding_order_parser.llm.settings import (
    DEFAULT_ARK_BASE_URL,
    LLMSettings,
)
from bedding_order_parser.llm.volcengine_ark import VolcengineArkProvider


def environment(**overrides: str) -> dict[str, str]:
    values = {
        "LLM_ENABLED": "true",
        "LLM_PROVIDER": "volcengine_ark",
        "LLM_BASE_URL": "https://ark.test/api/v3",
        "LLM_MODEL": "test-model",
        "LLM_TIMEOUT_SECONDS": "12.5",
        "LLM_MAX_RETRIES": "1",
        "ARK_API_KEY": "test-secret",
    }
    values.update(overrides)
    return values


def test_environment_loads_ark_settings_without_old_key_name() -> None:
    settings = LLMSettings.from_environment(
        {
            **environment(ARK_API_KEY=""),
            "LLM_API_KEY": "legacy-key-must-be-ignored",
        }
    )

    assert settings.api_key == ""
    assert settings.configuration_status() == "api_key_missing"


def test_environment_defaults_base_url_timeout_and_retries() -> None:
    settings = LLMSettings.from_environment(
        environment(
            LLM_BASE_URL="",
            LLM_TIMEOUT_SECONDS="",
            LLM_MAX_RETRIES="",
        )
    )

    assert settings.base_url == DEFAULT_ARK_BASE_URL
    assert settings.timeout_seconds == 60.0
    assert settings.max_retries == 2


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"LLM_ENABLED": "false"}, "disabled"),
        ({"LLM_PROVIDER": ""}, "provider_not_configured"),
        ({"LLM_PROVIDER": "unknown"}, "unsupported_provider"),
        ({"ARK_API_KEY": ""}, "api_key_missing"),
        ({"LLM_MODEL": ""}, "model_missing"),
        ({"LLM_TIMEOUT_SECONDS": "zero"}, "configuration_error"),
        ({"LLM_MAX_RETRIES": "10"}, "configuration_error"),
        ({"LLM_BASE_URL": "http://remote.test"}, "configuration_error"),
        (
            {"LLM_BASE_URL": "https://user:pass@ark.test/api/v3"},
            "configuration_error",
        ),
    ],
)
def test_configuration_statuses(
    overrides: dict[str, str], expected: str
) -> None:
    settings = LLMSettings.from_environment(environment(**overrides))

    assert settings.configuration_status() == expected


def test_factory_builds_ark_provider_when_selected() -> None:
    settings = LLMSettings.from_environment(environment())

    assert isinstance(build_provider(settings), VolcengineArkProvider)


def test_factory_keeps_unknown_provider_offline() -> None:
    settings = LLMSettings.from_environment(
        environment(LLM_PROVIDER="unknown")
    )

    assert isinstance(build_provider(settings), NullLLMProvider)
