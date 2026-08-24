"""Offline, injectable whole-order AI job orchestration for the desktop service."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from bedding_order_parser.ai_full_order.contracts import (
    AI_BUSINESS_FIELD_NAMES,
    V2_CONTRACT_VERSION,
)
from bedding_order_parser.ai_full_order.downstream import (
    DictionaryValidator,
    MaterialMatcher,
    PublishedBundle,
    publish_ready_batch,
    publish_ready_v2_batch,
)
from bedding_order_parser.ai_full_order.orchestration import (
    build_chunk_manifest,
    build_v2_extraction_units,
    formal_line_number_from_request,
)
from bedding_order_parser.ai_full_order.preprocessing import preprocess_workbook
from bedding_order_parser.ai_full_order.python_shadow import (
    build_deterministic_python_shadow,
)
from bedding_order_parser.ai_full_order.reliability import (
    OfflineReliabilityStore,
    OfflineReliableOrchestrator,
    ReliableRunResult,
    RunDisposition,
)
from bedding_order_parser.ai_full_order.resolution import (
    PythonShadowRecord,
    adapt_python_shadow_records,
)
from bedding_order_parser.ai_full_order.reliability_v2 import (
    V2ReliabilityStore,
    V2ReliableOrchestrator,
    V2RunDisposition,
)
from bedding_order_parser.ai_full_order.structure_manifest import (
    LAYOUT_PROMPT_VERSION,
    StructureManifestAdapterError,
    build_structure_manifest,
)
from bedding_order_parser.ai_full_order.structure_resolution import (
    StructureDecisionValidationError,
    apply_structure_decision,
    replayable_layout_output,
)


AI_JOB_STAGES = (
    "preprocessing",
    "structure_resolution",
    "python_shadow",
    "ai_extraction",
    "evidence_binding",
    "cache_revalidation",
    "publication",
    "completed",
    "python_shadow_parse",
    "local_structure_resolution",
    "ai_layout_recognition",
    "ai_block_extraction",
    "evidence_validation",
    "field_resolution",
    "dictionary_validation",
    "material_matching",
    "publishing",
    "awaiting_user_decision",
)


class AIEnhancedJobPause(RuntimeError):
    """An offline AI job needs an explicit user decision and has no publication."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        execution: Any | None = None,
        provider_calls: int = 0,
        layout_calls: int = 0,
        http_attempts: int = 0,
        usage: Mapping[str, int] | None = None,
        structure_summary: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.execution = execution
        self.provider_calls = provider_calls
        self.layout_calls = layout_calls
        self.http_attempts = http_attempts
        self.usage = dict(usage or {})
        self.structure_summary = dict(structure_summary or {})


@dataclass(frozen=True)
class AIEnhancedDependencies:
    """All whole-order dependencies are supplied by the desktop composition root."""

    provider: Any
    dictionary_validator: DictionaryValidator | None = None
    material_matcher: MaterialMatcher | None = None
    provider_name: str = "fake_provider"
    model_name: str = "offline-test"
    max_logical_calls: int = 12
    contract_version: str = V2_CONTRACT_VERSION
    downstream_factory: Callable[
        [Path, Path], tuple[DictionaryValidator, MaterialMatcher]
    ] | None = None

    @property
    def downstream_ready(self) -> bool:
        return (
            self.dictionary_validator is not None
            and self.material_matcher is not None
        ) or self.downstream_factory is not None

    def bind_for_job(
        self, input_path: str | Path, runtime_root: str | Path
    ) -> "AIEnhancedDependencies":
        if self.downstream_factory is None:
            return self
        dictionary_validator, material_matcher = self.downstream_factory(
            Path(input_path), Path(runtime_root)
        )
        return replace(
            self,
            dictionary_validator=dictionary_validator,
            material_matcher=material_matcher,
            downstream_factory=None,
        )


@dataclass(frozen=True)
class AIEnhancedJobResult:
    execution: Any
    bundle: PublishedBundle
    structure_status: str
    total_chunks: int
    provider_name: str
    model_name: str
    request_id: str = ""
    usage: Mapping[str, int] | None = None
    http_attempt_count: int = 0
    layout_call_count: int = 0
    isolated_field_count: int = 0
    contract_version: str = "1.0"
    structure_summary: Mapping[str, Any] | None = None


def build_python_shadow(preprocessed) -> tuple[PythonShadowRecord, ...]:
    """Adapt only local formal line numbers and blank Python candidates for B2A."""
    request = preprocessed.to_request_dict()
    formal_records = [
        {
            **{field: "" for field in AI_BUSINESS_FIELD_NAMES},
            "行号": formal_line_number_from_request(record, request["evidence_catalog"]),
        }
        for record in request["records"]
    ]
    return adapt_python_shadow_records(preprocessed, formal_records)


def run_ai_enhanced_job(
    input_path: str | Path,
    *,
    job_id: str,
    runtime_root: str | Path,
    publish_root: str | Path,
    dependencies: AIEnhancedDependencies | None,
    on_stage: Callable[[str, int, int, int], None],
    force_deterministic_retry: bool = False,
) -> AIEnhancedJobResult:
    """Run the B1-B3 chain locally; it never constructs a real provider itself."""
    if dependencies is None:
        raise AIEnhancedJobPause("AI_NOT_READY", "AI增强整单解析尚未配置离线执行依赖。")

    dependencies = dependencies.bind_for_job(input_path, runtime_root)
    if not dependencies.downstream_ready:
        raise AIEnhancedJobPause("AI_NOT_READY", "AI增强整单解析下游依赖未就绪。")

    provider = dependencies.provider
    extraction_before = int(getattr(provider, "extraction_call_count", 0))
    layout_before = int(getattr(provider, "structure_call_count", 0))
    http_before = int(getattr(provider, "http_attempt_count", 0))
    usage_before = _provider_usage(provider)

    on_stage("preprocessing", 0, 0, 0)
    preprocessed = preprocess_workbook(input_path)
    manifest = build_chunk_manifest(preprocessed)
    if len(manifest) > dependencies.max_logical_calls:
        raise AIEnhancedJobPause(
            "TOKEN_BUDGET_EXCEEDED",
            "订单分块数量超过当前离线调用预算，尚未发起提取。",
        )

    on_stage("python_shadow_parse", 0, len(manifest), 0)
    shadow = build_python_shadow(preprocessed)
    on_stage("local_structure_resolution", 0, len(manifest), 0)
    if preprocessed.structure_status == "ambiguous":
        on_stage("ai_layout_recognition", 0, len(manifest), 0)
    on_stage("ai_block_extraction", 0, len(manifest), 0)
    orchestrator = OfflineReliableOrchestrator(OfflineReliabilityStore(Path(runtime_root) / "reliability"))
    execution = orchestrator.run(
        preprocessed,
        provider,
        shadow,
        client_idempotency_key=f"ai-full-order:{job_id}",
        business_key=f"desktop-job:{job_id}",
        force_deterministic_retry=force_deterministic_retry,
    )
    completed = sum(1 for item in execution.outcomes if item.status.value == "validated")
    extraction_calls = _counter_delta(provider, "extraction_call_count", extraction_before)
    layout_calls = _counter_delta(provider, "structure_call_count", layout_before)
    calls = extraction_calls + layout_calls
    http_attempts = _counter_delta(provider, "http_attempt_count", http_before)
    usage = _usage_delta(provider, usage_before)
    on_stage("evidence_validation", completed, len(manifest), calls)
    on_stage("field_resolution", completed, len(manifest), calls)
    if execution.disposition is RunDisposition.INTERRUPTED:
        raise AIEnhancedJobPause(
            "AI_INTERRUPTED",
            "AI整单解析已中断，可仅重试未完成分块。",
            execution=execution,
            provider_calls=extraction_calls,
            layout_calls=layout_calls,
            http_attempts=http_attempts,
            usage=usage,
        )
    if execution.disposition is RunDisposition.IN_PROGRESS:
        raise AIEnhancedJobPause(
            "AI_IN_PROGRESS",
            "同一AI整单任务仍在执行，请稍后查看。",
            execution=execution,
            provider_calls=extraction_calls,
            layout_calls=layout_calls,
            http_attempts=http_attempts,
            usage=usage,
        )
    if execution.disposition is RunDisposition.ISOLATED or not execution.batch.ready_for_downstream:
        error_codes = {item.error_code for item in execution.outcomes if item.error_code}
        if completed and any(code.startswith("transient") for code in error_codes):
            code = "AI_PARTIAL_RESULT"
            message = "部分AI分块已验证，其余分块尚未完成，结果保持隔离。"
        elif "transient_attempt_limit" in error_codes:
            code = "AI_TRANSIENT_FAILURE_EXHAUSTED"
            message = "AI整单瞬时失败已达到尝试上限，结果保持隔离。"
        else:
            code = "AI_SCHEMA_OR_EVIDENCE_FAILED"
            message = "AI整单结果未通过证据、字段裁决或整批隔离校验。"
        raise AIEnhancedJobPause(
            code,
            message,
            execution=execution,
            provider_calls=extraction_calls,
            layout_calls=layout_calls,
            http_attempts=http_attempts,
            usage=usage,
        )

    on_stage("dictionary_validation", completed, len(manifest), calls)
    on_stage("material_matching", completed, len(manifest), calls)
    on_stage("publishing", completed, len(manifest), calls)
    try:
        bundle = publish_ready_batch(
            execution,
            preprocessed=preprocessed,
            dictionary_validator=dependencies.dictionary_validator,
            material_matcher=dependencies.material_matcher,
            publish_root=publish_root,
        )
    except Exception as exc:
        raise AIEnhancedJobPause(
            "AI_DOWNSTREAM_FAILED",
            "AI整单结果未能完成字典、匹配或原子发布。",
            execution=execution,
            provider_calls=extraction_calls,
            layout_calls=layout_calls,
            http_attempts=http_attempts,
            usage=usage,
        ) from exc
    return AIEnhancedJobResult(
        execution=execution,
        bundle=bundle,
        structure_status=preprocessed.structure_status,
        total_chunks=len(manifest),
        provider_name=dependencies.provider_name,
        model_name=dependencies.model_name,
        request_id=str(getattr(getattr(provider, "latest_telemetry", None), "request_id", "")),
        usage=usage,
        http_attempt_count=http_attempts,
        layout_call_count=layout_calls,
        contract_version="1.0",
    )


def run_ai_enhanced_v2_job(
    input_path: str | Path,
    *,
    runtime_root: str | Path,
    publish_root: str | Path,
    dependencies: AIEnhancedDependencies | None,
    client_idempotency_key: str,
    business_key: str,
    on_stage: Callable[[str, int, int, int], None],
    retry_corrupt_cache: bool = False,
    persisted_structure_summary: Mapping[str, Any] | None = None,
    on_structure_summary: Callable[[Mapping[str, Any]], None] | None = None,
) -> AIEnhancedJobResult:
    """Run the explicit V2 desktop chain without falling back to V1 or standard."""

    if dependencies is None:
        raise AIEnhancedJobPause("AI_NOT_READY", "AI增强整单解析尚未配置离线执行依赖。")
    if dependencies.contract_version != V2_CONTRACT_VERSION:
        raise AIEnhancedJobPause(
            "AI_V2_COMPOSITION_INVALID",
            "AI增强整单解析依赖未声明 Contract V2。",
        )

    dependencies = dependencies.bind_for_job(input_path, runtime_root)
    if not dependencies.downstream_ready:
        raise AIEnhancedJobPause(
            "AI_V2_COMPOSITION_INVALID",
            "AI增强整单 V2 下游依赖未就绪。",
        )

    provider = dependencies.provider
    extraction_before = int(getattr(provider, "extraction_call_count", 0))
    layout_before = int(getattr(provider, "structure_call_count", 0))
    http_before = int(getattr(provider, "http_attempt_count", 0))
    usage_before = _provider_usage(provider)
    structure_summary: Mapping[str, Any] = {}

    on_stage("preprocessing", 0, 0, 0)
    preprocessed = preprocess_workbook(input_path)
    on_stage("structure_resolution", 0, 0, 0)
    if preprocessed.structure_status == "ambiguous":
        try:
            structure_manifest = build_structure_manifest(
                preprocessed, build_chunk_manifest(preprocessed)
            )
        except StructureManifestAdapterError as exc:
            raise AIEnhancedJobPause(
                "AI_V2_STRUCTURE_MANIFEST_INVALID",
                "本地订单结构清单无法通过安全校验。",
            ) from exc
        operation_identity = _layout_operation_identity(
            structure_manifest,
            provider_name=dependencies.provider_name,
            model_name=dependencies.model_name,
        )
        replay = replayable_layout_output(
            persisted_structure_summary,
            structure_manifest,
            operation_identity_sha256=operation_identity,
        )
        try:
            layout_output = replay or provider.resolve_structure(structure_manifest)
        except Exception as exc:
            raise AIEnhancedJobPause(
                "AI_V2_STRUCTURE_PROVIDER_FAILED",
                "AI结构识别服务未能安全完成。",
                layout_calls=_counter_delta(provider, "structure_call_count", layout_before),
                http_attempts=_counter_delta(provider, "http_attempt_count", http_before),
                usage=_usage_delta(provider, usage_before),
            ) from exc
        try:
            application = apply_structure_decision(
                preprocessed, structure_manifest, layout_output
            )
        except StructureDecisionValidationError as exc:
            raise AIEnhancedJobPause(
                "AI_V2_STRUCTURE_DECISION_INVALID",
                "AI结构决策未能绑定到本地安全候选。",
                layout_calls=_counter_delta(provider, "structure_call_count", layout_before),
                http_attempts=_counter_delta(provider, "http_attempt_count", http_before),
                usage=_usage_delta(provider, usage_before),
            ) from exc
        structure_summary = {
            **application.summary,
            "prompt_version": LAYOUT_PROMPT_VERSION,
            "operation_identity_sha256": operation_identity,
        }
        if on_structure_summary is not None:
            on_structure_summary(structure_summary)
        if not application.resolved:
            raise AIEnhancedJobPause(
                "AI_V2_STRUCTURE_UNRESOLVED",
                "结构识别仍无法在本地形成可靠订单提取单元。",
                layout_calls=_counter_delta(provider, "structure_call_count", layout_before),
                http_attempts=_counter_delta(provider, "http_attempt_count", http_before),
                usage=_usage_delta(provider, usage_before),
                structure_summary=structure_summary,
            )
        preprocessed = application.preprocessed

    units = build_v2_extraction_units(preprocessed)
    if not units:
        raise AIEnhancedJobPause(
            "AI_V2_STRUCTURE_UNRESOLVED",
            "本地未能构造可靠的订单提取单元。",
            layout_calls=_counter_delta(provider, "structure_call_count", layout_before),
            http_attempts=_counter_delta(provider, "http_attempt_count", http_before),
            usage=_usage_delta(provider, usage_before),
            structure_summary=structure_summary,
        )
    if len(units) > dependencies.max_logical_calls:
        raise AIEnhancedJobPause(
            "TOKEN_BUDGET_EXCEEDED",
            "订单提取单元超过当前离线调用预算，尚未发起提取。",
            layout_calls=_counter_delta(provider, "structure_call_count", layout_before),
            http_attempts=_counter_delta(provider, "http_attempt_count", http_before),
            usage=_usage_delta(provider, usage_before),
            structure_summary=structure_summary,
        )

    evidence = {
        item.evidence_id: item
        for unit in units
        for item in unit.evidence_catalog
    }
    on_stage("python_shadow", 0, len(units), 0)
    shadow = build_deterministic_python_shadow(
        input_path,
        preprocessed,
        target_records=[unit.target for unit in units],
        evidence_catalog=tuple(evidence.values()),
    )
    on_stage("ai_extraction", 0, len(units), 0)
    execution = V2ReliableOrchestrator(
        V2ReliabilityStore(Path(runtime_root) / "reliability")
    ).run(
        preprocessed,
        provider,
        shadow,
        client_idempotency_key=client_idempotency_key,
        business_key=business_key,
        provider_name=dependencies.provider_name,
        model_name=dependencies.model_name,
        retry_corrupt_cache=retry_corrupt_cache,
    )
    completed = sum(
        item.status.value == "validated" for item in execution.outcomes
    )
    extraction_calls = _counter_delta(provider, "extraction_call_count", extraction_before)
    layout_calls = _counter_delta(provider, "structure_call_count", layout_before)
    logical_calls = extraction_calls + layout_calls
    http_attempts = _counter_delta(provider, "http_attempt_count", http_before)
    on_stage("evidence_binding", completed, len(units), logical_calls)
    on_stage("field_resolution", completed, len(units), logical_calls)
    on_stage("cache_revalidation", completed, len(units), logical_calls)

    if execution.disposition is V2RunDisposition.INTERRUPTED:
        raise AIEnhancedJobPause(
            "AI_V2_INTERRUPTED",
            "AI整单 V2 执行已中断，可恢复未验证单元。",
            execution=execution,
            provider_calls=extraction_calls,
            layout_calls=layout_calls,
            http_attempts=http_attempts,
            usage=_usage_delta(provider, usage_before),
            structure_summary=structure_summary,
        )
    if execution.disposition is V2RunDisposition.IN_PROGRESS:
        raise AIEnhancedJobPause(
            "AI_V2_IN_PROGRESS",
            "相同 V2 提取任务仍在执行。",
            execution=execution,
            provider_calls=extraction_calls,
            layout_calls=layout_calls,
            http_attempts=http_attempts,
            usage=_usage_delta(provider, usage_before),
            structure_summary=structure_summary,
        )
    if execution.disposition is V2RunDisposition.ISOLATED or not execution.batch.ready_for_downstream:
        error_codes = {item.error_code for item in execution.outcomes if item.error_code}
        if "v2_cache_corrupt" in error_codes or "v2_cached_revalidation_failure" in error_codes:
            code = "AI_V2_CACHE_CORRUPT"
        elif any(code.startswith("v2_transient") for code in error_codes):
            code = "AI_V2_TRANSIENT_FAILURE"
        elif "high_risk_blocking_conflict" in execution.batch.reasons:
            code = "AI_V2_HIGH_RISK_CONFLICT"
        else:
            code = "AI_V2_CONTRACT_FAILED"
        raise AIEnhancedJobPause(
            code,
            "AI整单 V2 结果未通过安全发布门。",
            execution=execution,
            provider_calls=extraction_calls,
            layout_calls=layout_calls,
            http_attempts=http_attempts,
            usage=_usage_delta(provider, usage_before),
            structure_summary=structure_summary,
        )

    on_stage("dictionary_validation", completed, len(units), logical_calls)
    on_stage("material_matching", completed, len(units), logical_calls)
    on_stage("publication", completed, len(units), logical_calls)
    try:
        bundle = publish_ready_v2_batch(
            execution,
            preprocessed=preprocessed,
            dictionary_validator=dependencies.dictionary_validator,
            material_matcher=dependencies.material_matcher,
            publish_root=publish_root,
        )
    except Exception as exc:
        raise AIEnhancedJobPause(
            "AI_V2_PUBLICATION_FAILED",
            "AI整单 V2 五类结果未能完成原子发布。",
            execution=execution,
            provider_calls=extraction_calls,
            layout_calls=layout_calls,
            http_attempts=http_attempts,
            usage=_usage_delta(provider, usage_before),
            structure_summary=structure_summary,
        ) from exc

    on_stage("completed", len(units), len(units), logical_calls)
    telemetry = execution.provider_telemetry[-1] if execution.provider_telemetry else {}
    isolated_fields = sum(
        decision.ai_isolated or decision.status.value == "ai_isolated"
        for record in execution.batch.records
        for decision in record.decisions.values()
    )
    return AIEnhancedJobResult(
        execution=execution,
        bundle=bundle,
        structure_status=preprocessed.structure_status,
        total_chunks=len(units),
        provider_name=dependencies.provider_name,
        model_name=dependencies.model_name,
        request_id=str(telemetry.get("request_id", "")),
        usage=_usage_delta(provider, usage_before),
        http_attempt_count=http_attempts,
        layout_call_count=layout_calls,
        isolated_field_count=isolated_fields,
        contract_version=V2_CONTRACT_VERSION,
        structure_summary=structure_summary,
    )


def _provider_usage(provider: Any) -> Mapping[str, int]:
    summary = getattr(provider, "usage_summary", None)
    if isinstance(summary, Mapping):
        return {
            name: int(summary.get(name, 0))
            for name in ("input_tokens", "output_tokens", "total_tokens")
        }
    telemetry = getattr(provider, "latest_telemetry", None)
    return {
        name: int(getattr(telemetry, name, 0))
        for name in ("input_tokens", "output_tokens", "total_tokens")
    }


def _counter_delta(provider: Any, name: str, before: int) -> int:
    return max(0, int(getattr(provider, name, 0)) - before)


def _usage_delta(provider: Any, before: Mapping[str, int]) -> Mapping[str, int]:
    current = _provider_usage(provider)
    return {
        name: max(0, int(current.get(name, 0)) - int(before.get(name, 0)))
        for name in ("input_tokens", "output_tokens", "total_tokens")
    }


def _layout_operation_identity(
    manifest: Mapping[str, Any], *, provider_name: str, model_name: str
) -> str:
    payload = {
        "context_sha256": str(manifest["context_sha256"]),
        "provider": provider_name,
        "model": model_name,
        "prompt_version": LAYOUT_PROMPT_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
