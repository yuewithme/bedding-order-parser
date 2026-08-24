"""Version-isolated cache, single-flight, and recovery for V2 extraction units."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from bedding_order_parser.ai_full_order.contracts import (
    AI_BUSINESS_FIELD_NAMES,
    NORMALIZATION_RULES_VERSION,
    V2_CONTRACT_VERSION,
    V2_SCHEMA_VERSION,
    FullOrderContractError,
    validate_full_order_v2_output,
)
from bedding_order_parser.ai_full_order.comparison import (
    COMPARISON_VERSION,
    V2TechnicalCandidateStatus,
)
from bedding_order_parser.ai_full_order.field_policy import (
    V2DecisionStatus,
    V2_FIELD_POLICY_VERSION,
    V2FieldPolicyError,
    resolve_v2_record,
)
from bedding_order_parser.ai_full_order.orchestration import (
    V2_CONTEXT_SELECTION_VERSION,
    V2BatchAggregate,
    V2ExtractionUnit,
    V2ExtractionUnitOutcome,
    V2ExtractionUnitStatus,
    aggregate_v2_batch,
    build_v2_extraction_request,
    build_v2_extraction_units,
    validate_v2_accepted_ai_provenance,
)
from bedding_order_parser.ai_full_order.normalization import NORMALIZATION_VERSION
from bedding_order_parser.ai_full_order.preprocessing import (
    PREPROCESSOR_VERSION,
    PreprocessedWorkbook,
)
from bedding_order_parser.ai_full_order.provenance import (
    V2_PROVENANCE_BINDING_VERSION,
    bind_v2_candidates,
)
from bedding_order_parser.ai_full_order.python_shadow import (
    V2_PYTHON_SHADOW_ADAPTER_VERSION,
)
from bedding_order_parser.ai_full_order.reliability import FileLease, TransientProviderError
from bedding_order_parser.ai_full_order.resolution import PythonShadowRecord
from bedding_order_parser.ai_full_order.volcengine_ark import FULL_ORDER_V2_PROMPT_VERSION


V2_STATE_FORMAT_VERSION = "2.0"


class V2UnitRunState(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VALIDATED = "validated"
    VALIDATED_WITH_CONTENT_ISSUE = "validated_with_content_issue"
    # Read-only compatibility for state written before technical review was separated.
    CANDIDATE_ISOLATED = "candidate_isolated"
    FAILED_TRANSIENT = "failed_transient"
    HARD_FAILED = "hard_failed"
    INTERRUPTED = "interrupted"


class V2RunDisposition(StrEnum):
    EXECUTED = "executed"
    CACHED = "cached"
    IN_PROGRESS = "in_progress"
    INTERRUPTED = "interrupted"
    ISOLATED = "isolated"


class V2ReliabilityError(RuntimeError):
    pass


class V2StateCorruptionError(V2ReliabilityError):
    pass


class V2StateTransitionError(V2ReliabilityError):
    pass


class V2IdempotencyConflictError(V2ReliabilityError):
    pass


@dataclass(frozen=True)
class V2CacheIdentity:
    source_file_sha256: str
    provider: str
    model: str
    contract_version: str
    schema_version: str
    prompt_version: str
    preprocessor_version: str
    context_selection_version: str
    normalization_version: str
    evidence_normalization_version: str
    comparison_version: str
    python_shadow_adapter_version: str
    field_policy_version: str
    provenance_binding_version: str
    canonical_extraction_manifest_sha256: str

    @property
    def cache_key(self) -> str:
        return _sha(_canonical(asdict(self)))


@dataclass(frozen=True)
class V2UnitStateRecord:
    cache_key: str
    extraction_unit_id: str
    unit_identity_sha256: str
    state: V2UnitRunState
    attempt_count: int = 0
    owner_token: str = ""
    updated_at_ms: int = 0
    error_code: str = ""
    retry_after_ms: int = 0
    validated_candidates: dict[str, Any] | None = None
    provider_telemetry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_format_version": V2_STATE_FORMAT_VERSION,
            "cache_key": self.cache_key,
            "extraction_unit_id": self.extraction_unit_id,
            "unit_identity_sha256": self.unit_identity_sha256,
            "state": self.state.value,
            "attempt_count": self.attempt_count,
            "owner_token": self.owner_token,
            "updated_at_ms": self.updated_at_ms,
            "error_code": self.error_code,
            "retry_after_ms": self.retry_after_ms,
            "validated_candidates": self.validated_candidates,
            "provider_telemetry": self.provider_telemetry,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "V2UnitStateRecord":
        expected = {
            "state_format_version",
            "cache_key",
            "extraction_unit_id",
            "unit_identity_sha256",
            "state",
            "attempt_count",
            "owner_token",
            "updated_at_ms",
            "error_code",
            "retry_after_ms",
            "validated_candidates",
            "provider_telemetry",
        }
        if set(raw) != expected or raw.get("state_format_version") != V2_STATE_FORMAT_VERSION:
            raise V2StateCorruptionError("V2 state fields or format version are invalid.")
        try:
            state = V2UnitRunState(raw["state"])
        except (TypeError, ValueError) as exc:
            raise V2StateCorruptionError("V2 state contains an unknown status.") from exc
        for name in ("cache_key", "extraction_unit_id", "unit_identity_sha256", "owner_token", "error_code"):
            if not isinstance(raw[name], str):
                raise V2StateCorruptionError("V2 state string field is invalid.")
        for name in ("attempt_count", "updated_at_ms", "retry_after_ms"):
            if isinstance(raw[name], bool) or not isinstance(raw[name], int) or raw[name] < 0:
                raise V2StateCorruptionError("V2 state numeric field is invalid.")
        output = raw["validated_candidates"]
        successful = state in {
            V2UnitRunState.VALIDATED,
            V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE,
            V2UnitRunState.CANDIDATE_ISOLATED,
        }
        if successful != isinstance(output, dict):
            raise V2StateCorruptionError("V2 state and validated candidates disagree.")
        telemetry = raw["provider_telemetry"]
        if telemetry is not None:
            telemetry = _validate_telemetry(telemetry)
        if successful and telemetry is None:
            raise V2StateCorruptionError("A successful V2 state must include safe telemetry.")
        return cls(
            cache_key=raw["cache_key"],
            extraction_unit_id=raw["extraction_unit_id"],
            unit_identity_sha256=raw["unit_identity_sha256"],
            state=state,
            attempt_count=raw["attempt_count"],
            owner_token=raw["owner_token"],
            updated_at_ms=raw["updated_at_ms"],
            error_code=raw["error_code"],
            retry_after_ms=raw["retry_after_ms"],
            validated_candidates=output,
            provider_telemetry=telemetry,
        )


@dataclass(frozen=True)
class V2ExecutionRecord:
    client_idempotency_key: str
    business_key: str
    cache_key: str
    execution_id: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class V2ReliableRunResult:
    disposition: V2RunDisposition
    execution_id: str
    cache_key: str
    cache_identity: V2CacheIdentity
    extraction_units: tuple[V2ExtractionUnit, ...]
    outcomes: tuple[V2ExtractionUnitOutcome, ...]
    batch: V2BatchAggregate
    provider_calls: int
    provider_telemetry: tuple[Mapping[str, Any], ...]


def extraction_unit_identity_sha256(unit: V2ExtractionUnit) -> str:
    return _sha(_canonical(build_v2_extraction_request(unit)))


def canonical_extraction_manifest_sha256(units: Sequence[V2ExtractionUnit]) -> str:
    manifest = [
        {
            "order": unit.order,
            "chunk_id": unit.chunk_id,
            "extraction_unit_id": unit.extraction_unit_id,
            "unit_identity_sha256": extraction_unit_identity_sha256(unit),
        }
        for unit in sorted(units, key=lambda item: item.order)
    ]
    return _sha(_canonical(manifest))


def build_v2_cache_identity(
    units: Sequence[V2ExtractionUnit],
    *,
    provider: str = "fake_provider",
    model: str = "offline-test",
    contract_version: str = V2_CONTRACT_VERSION,
    schema_version: str = V2_SCHEMA_VERSION,
    prompt_version: str = FULL_ORDER_V2_PROMPT_VERSION,
    preprocessor_version: str = PREPROCESSOR_VERSION,
    context_selection_version: str = V2_CONTEXT_SELECTION_VERSION,
    normalization_version: str = NORMALIZATION_VERSION,
    evidence_normalization_version: str = NORMALIZATION_RULES_VERSION,
    comparison_version: str = COMPARISON_VERSION,
    python_shadow_adapter_version: str = V2_PYTHON_SHADOW_ADAPTER_VERSION,
    field_policy_version: str = V2_FIELD_POLICY_VERSION,
    provenance_binding_version: str = V2_PROVENANCE_BINDING_VERSION,
) -> V2CacheIdentity:
    sources = {unit.source_file_sha256 for unit in units}
    if len(sources) != 1:
        raise V2ReliabilityError("V2 extraction manifest must have exactly one source SHA.")
    return V2CacheIdentity(
        source_file_sha256=next(iter(sources)),
        provider=provider,
        model=model,
        contract_version=contract_version,
        schema_version=schema_version,
        prompt_version=prompt_version,
        preprocessor_version=preprocessor_version,
        context_selection_version=context_selection_version,
        normalization_version=normalization_version,
        evidence_normalization_version=evidence_normalization_version,
        comparison_version=comparison_version,
        python_shadow_adapter_version=python_shadow_adapter_version,
        field_policy_version=field_policy_version,
        provenance_binding_version=provenance_binding_version,
        canonical_extraction_manifest_sha256=canonical_extraction_manifest_sha256(units),
    )


_V2_TRANSITIONS: dict[V2UnitRunState | None, frozenset[V2UnitRunState]] = {
    None: frozenset({V2UnitRunState.PENDING}),
    V2UnitRunState.PENDING: frozenset({V2UnitRunState.IN_PROGRESS, V2UnitRunState.INTERRUPTED}),
    V2UnitRunState.IN_PROGRESS: frozenset(
        {
            V2UnitRunState.VALIDATED,
            V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE,
            V2UnitRunState.CANDIDATE_ISOLATED,
            V2UnitRunState.FAILED_TRANSIENT,
            V2UnitRunState.HARD_FAILED,
            V2UnitRunState.INTERRUPTED,
        }
    ),
    V2UnitRunState.FAILED_TRANSIENT: frozenset(
        {V2UnitRunState.IN_PROGRESS, V2UnitRunState.INTERRUPTED}
    ),
    V2UnitRunState.INTERRUPTED: frozenset({V2UnitRunState.IN_PROGRESS}),
    V2UnitRunState.VALIDATED: frozenset({V2UnitRunState.VALIDATED}),
    V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE: frozenset(
        {V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE}
    ),
    V2UnitRunState.CANDIDATE_ISOLATED: frozenset({V2UnitRunState.CANDIDATE_ISOLATED}),
    V2UnitRunState.HARD_FAILED: frozenset({V2UnitRunState.HARD_FAILED}),
}


class V2ReliabilityStore:
    """V2 state lives below an explicit namespace and cannot collide with V1."""

    def __init__(self, root: str | Path, *, replace_retries: int = 3) -> None:
        self.root = Path(root).expanduser().resolve() / "v2"
        self.replace_retries = replace_retries

    def state_path(self, cache_key: str, extraction_unit_id: str) -> Path:
        return self.root / "units" / cache_key / f"{_sha(extraction_unit_id)}.json"

    def lock_path(self, cache_key: str) -> Path:
        return self.root / "locks" / f"{cache_key}.lease.json"

    def idempotency_path(self, client_key: str) -> Path:
        return self.root / "idempotency" / f"{_sha(client_key)}.json"

    def read_state(self, cache_key: str, unit: V2ExtractionUnit) -> V2UnitStateRecord | None:
        path = self.state_path(cache_key, unit.extraction_unit_id)
        if not path.exists():
            return None
        try:
            raw = _read_json(path)
            if not isinstance(raw, dict):
                raise V2StateCorruptionError("V2 state root must be an object.")
            record = V2UnitStateRecord.from_dict(raw)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise V2StateCorruptionError(f"V2 state is corrupt: {path.name}") from exc
        if (
            record.cache_key != cache_key
            or record.extraction_unit_id != unit.extraction_unit_id
            or record.unit_identity_sha256 != extraction_unit_identity_sha256(unit)
        ):
            raise V2StateCorruptionError("V2 state identity does not match its current extraction unit.")
        return record

    def write_state(self, record: V2UnitStateRecord) -> None:
        path = self.state_path(record.cache_key, record.extraction_unit_id)
        existing = self._read_path(path)
        if existing and (
            existing.cache_key != record.cache_key
            or existing.extraction_unit_id != record.extraction_unit_id
            or existing.unit_identity_sha256 != record.unit_identity_sha256
        ):
            raise V2StateCorruptionError("Existing V2 state identity does not match its path.")
        previous = existing.state if existing else None
        if record.state not in _V2_TRANSITIONS[previous]:
            raise V2StateTransitionError(f"Forbidden V2 state transition: {previous} -> {record.state}")
        if previous in {
            V2UnitRunState.VALIDATED,
            V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE,
            V2UnitRunState.CANDIDATE_ISOLATED,
            V2UnitRunState.HARD_FAILED,
        } and existing != record:
            raise V2StateTransitionError("A V2 terminal state cannot be overwritten by an older writer.")
        _atomic_json(path, record.to_dict(), self.replace_retries)

    def claim_execution(
        self, client_key: str, business_key: str, cache_key: str
    ) -> V2ExecutionRecord:
        execution_id = "v2-exec:" + _sha(
            _canonical(
                {"client_key": client_key, "business_key": business_key, "cache_key": cache_key}
            )
        )[:24]
        candidate = V2ExecutionRecord(client_key, business_key, cache_key, execution_id)
        path = self.idempotency_path(client_key)
        try:
            _create_json(path, candidate.to_dict())
            return candidate
        except FileExistsError:
            try:
                raw = _read_json(path)
                expected = {
                    "client_idempotency_key",
                    "business_key",
                    "cache_key",
                    "execution_id",
                }
                if not isinstance(raw, dict) or set(raw) != expected or any(
                    not isinstance(raw[name], str) for name in expected
                ):
                    raise V2StateCorruptionError("V2 idempotency fields are invalid.")
                existing = V2ExecutionRecord(**raw)
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise V2StateCorruptionError("V2 idempotency record is corrupt.") from exc
            if existing != candidate:
                raise V2IdempotencyConflictError(
                    "A V2 idempotency key cannot be reused for another business or contract identity."
                )
            return existing

    def lease(self, cache_key: str, lease_ms: int) -> FileLease:
        return FileLease(self, cache_key, lease_ms)

    def discard_corrupt_state(self, cache_key: str, unit: V2ExtractionUnit) -> None:
        """Explicit retry may discard one unreadable cache file; normal reads never do."""

        path = self.state_path(cache_key, unit.extraction_unit_id)
        for attempt in range(self.replace_retries + 1):
            try:
                path.unlink(missing_ok=True)
                return
            except PermissionError:
                if attempt == self.replace_retries:
                    raise
                time.sleep(0.005 * (attempt + 1))

    def _read_path(self, path: Path) -> V2UnitStateRecord | None:
        if not path.exists():
            return None
        try:
            raw = _read_json(path)
            if not isinstance(raw, dict):
                raise V2StateCorruptionError("V2 state root must be an object.")
            return V2UnitStateRecord.from_dict(raw)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise V2StateCorruptionError(f"V2 state is corrupt: {path.name}") from exc


class V2ReliableOrchestrator:
    def __init__(
        self,
        store: V2ReliabilityStore,
        *,
        max_transient_attempts: int = 2,
        transient_backoff_ms: int = 1,
        lease_ms: int = 30_000,
    ) -> None:
        self.store = store
        self.max_transient_attempts = max_transient_attempts
        self.transient_backoff_ms = transient_backoff_ms
        self.lease_ms = lease_ms

    def run(
        self,
        preprocessed: PreprocessedWorkbook,
        provider: Any,
        python_shadow: Sequence[PythonShadowRecord],
        *,
        client_idempotency_key: str,
        business_key: str,
        provider_name: str = "fake_provider",
        model_name: str = "offline-test",
        cache_identity: V2CacheIdentity | None = None,
        wait_timeout_ms: int = 0,
        interrupt_after_completed_units: int | None = None,
        interrupt_before_unit_order: int | None = None,
        retry_corrupt_cache: bool = False,
    ) -> V2ReliableRunResult:
        units = build_v2_extraction_units(preprocessed)
        identity = cache_identity or build_v2_cache_identity(
            units, provider=provider_name, model=model_name
        )
        if identity.source_file_sha256 != preprocessed.source_file_sha256:
            raise V2ReliabilityError("V2 cache identity does not match the preprocessed source.")
        if identity.canonical_extraction_manifest_sha256 != canonical_extraction_manifest_sha256(units):
            raise V2ReliabilityError("V2 cache identity does not match the extraction manifest.")
        shadow_by_id = _validate_shadow(units, python_shadow)
        cache_key = identity.cache_key
        execution = self.store.claim_execution(
            client_idempotency_key, business_key, cache_key
        )
        calls_before = _provider_calls(provider)
        cached = self._all_revalidated(cache_key, units, shadow_by_id)
        if cached is not None:
            return self._result(
                V2RunDisposition.CACHED,
                execution,
                identity,
                units,
                cached,
                provider,
                calls_before,
            )

        lease = self.store.lease(cache_key, self.lease_ms)
        if not lease.try_acquire():
            waited = self._wait(cache_key, units, shadow_by_id, wait_timeout_ms)
            if waited is not None:
                return self._result(
                    V2RunDisposition.CACHED,
                    execution,
                    identity,
                    units,
                    waited,
                    provider,
                    calls_before,
                )
            return self._result(
                V2RunDisposition.IN_PROGRESS,
                execution,
                identity,
                units,
                (),
                provider,
                calls_before,
            )

        try:
            self._recover_in_progress(cache_key, units)
            cached = self._all_revalidated(cache_key, units, shadow_by_id)
            if cached is not None:
                return self._result(
                    V2RunDisposition.CACHED,
                    execution,
                    identity,
                    units,
                    cached,
                    provider,
                    calls_before,
                )
            outcomes: list[V2ExtractionUnitOutcome] = []
            completed_here = 0
            for unit in sorted(units, key=lambda item: item.order):
                lease.heartbeat()
                if interrupt_before_unit_order == unit.order:
                    return self._result(
                        V2RunDisposition.INTERRUPTED,
                        execution,
                        identity,
                        units,
                        outcomes,
                        provider,
                        calls_before,
                    )
                outcome = self._run_unit(
                    cache_key,
                    unit,
                    provider,
                    shadow_by_id[unit.target.record_local_id],
                    lease.owner_token,
                    identity,
                    retry_corrupt_cache,
                )
                outcomes.append(outcome)
                if outcome.status is V2ExtractionUnitStatus.VALIDATED:
                    completed_here += 1
                if (
                    interrupt_after_completed_units is not None
                    and completed_here >= interrupt_after_completed_units
                ):
                    return self._result(
                        V2RunDisposition.INTERRUPTED,
                        execution,
                        identity,
                        units,
                        outcomes,
                        provider,
                        calls_before,
                    )
            batch = aggregate_v2_batch(units, outcomes)
            disposition = (
                V2RunDisposition.EXECUTED
                if batch.ready_for_downstream
                else V2RunDisposition.ISOLATED
            )
            return self._result(
                disposition,
                execution,
                identity,
                units,
                outcomes,
                provider,
                calls_before,
                batch,
            )
        finally:
            lease.release()

    def _run_unit(
        self,
        cache_key: str,
        unit: V2ExtractionUnit,
        provider: Any,
        shadow: PythonShadowRecord,
        owner_token: str,
        identity: V2CacheIdentity,
        retry_corrupt_cache: bool,
    ) -> V2ExtractionUnitOutcome:
        try:
            prior = self.store.read_state(cache_key, unit)
        except V2StateCorruptionError:
            if not retry_corrupt_cache:
                return _failed_outcome(unit, "v2_cache_corrupt")
            self.store.discard_corrupt_state(cache_key, unit)
            prior = None
        if prior and prior.state in {
            V2UnitRunState.VALIDATED,
            V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE,
            V2UnitRunState.CANDIDATE_ISOLATED,
        }:
            return self._from_validated(prior, unit, shadow)
        if prior and prior.state is V2UnitRunState.HARD_FAILED:
            return _failed_outcome(unit, prior.error_code or "v2_hard_failed")
        if prior and prior.state is V2UnitRunState.FAILED_TRANSIENT:
            if prior.attempt_count >= self.max_transient_attempts:
                return _failed_outcome(unit, "v2_transient_attempt_limit")
            if prior.retry_after_ms > _now():
                return _failed_outcome(unit, "v2_transient_retry_pending")
        attempts = (prior.attempt_count if prior else 0) + 1
        unit_hash = extraction_unit_identity_sha256(unit)
        if prior is None:
            self.store.write_state(
                V2UnitStateRecord(
                    cache_key,
                    unit.extraction_unit_id,
                    unit_hash,
                    V2UnitRunState.PENDING,
                    updated_at_ms=_now(),
                )
            )
        self.store.write_state(
            V2UnitStateRecord(
                cache_key,
                unit.extraction_unit_id,
                unit_hash,
                V2UnitRunState.IN_PROGRESS,
                attempts,
                owner_token,
                _now(),
            )
        )
        try:
            output = provider.extract_v2(build_v2_extraction_request(unit))
            validated = validate_full_order_v2_output(output)
            outcome = _revalidate_output(unit, validated, shadow)
        except (TransientProviderError, TimeoutError, ConnectionError):
            state = V2UnitStateRecord(
                cache_key,
                unit.extraction_unit_id,
                unit_hash,
                V2UnitRunState.FAILED_TRANSIENT,
                attempts,
                owner_token,
                _now(),
                "v2_transient_provider_failure",
                _now() + self.transient_backoff_ms,
            )
            self.store.write_state(state)
            return _failed_outcome(unit, state.error_code)
        except (FullOrderContractError, V2FieldPolicyError, ValueError, TypeError, KeyError):
            state = V2UnitStateRecord(
                cache_key,
                unit.extraction_unit_id,
                unit_hash,
                V2UnitRunState.HARD_FAILED,
                attempts,
                owner_token,
                _now(),
                "v2_hard_contract_or_resolution_failure",
            )
            self.store.write_state(state)
            return _failed_outcome(unit, state.error_code)
        except Exception:
            state = V2UnitStateRecord(
                cache_key,
                unit.extraction_unit_id,
                unit_hash,
                V2UnitRunState.HARD_FAILED,
                attempts,
                owner_token,
                _now(),
                "v2_provider_or_processing_failure",
            )
            self.store.write_state(state)
            return _failed_outcome(unit, state.error_code)
        has_content_issue = _has_candidate_content_issue(outcome)
        state = V2UnitStateRecord(
            cache_key,
            unit.extraction_unit_id,
            unit_hash,
            (
                V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE
                if has_content_issue
                else V2UnitRunState.VALIDATED
            ),
            attempts,
            owner_token,
            _now(),
            "v2_candidate_content_issue" if has_content_issue else "",
            validated_candidates=validated,
            provider_telemetry=_provider_telemetry(provider, identity, attempts),
        )
        self.store.write_state(state)
        return outcome

    def _from_validated(
        self,
        state: V2UnitStateRecord,
        unit: V2ExtractionUnit,
        shadow: PythonShadowRecord,
    ) -> V2ExtractionUnitOutcome:
        try:
            if state.validated_candidates is None:
                raise V2StateCorruptionError("Validated V2 cache has no candidate payload.")
            outcome = _revalidate_output(unit, state.validated_candidates, shadow)
            expected_content_issue = state.state in {
                V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE,
                V2UnitRunState.CANDIDATE_ISOLATED,
            }
            if _has_candidate_content_issue(outcome) != expected_content_issue:
                raise V2StateCorruptionError(
                    "Cached V2 candidate status changed without a version change."
                )
            return outcome
        except (FullOrderContractError, V2FieldPolicyError, V2StateCorruptionError, ValueError, TypeError, KeyError):
            return _failed_outcome(unit, "v2_cached_revalidation_failure")

    def _all_revalidated(
        self,
        cache_key: str,
        units: Sequence[V2ExtractionUnit],
        shadow_by_id: Mapping[str, PythonShadowRecord],
    ) -> tuple[V2ExtractionUnitOutcome, ...] | None:
        outcomes: list[V2ExtractionUnitOutcome] = []
        for unit in units:
            try:
                state = self.store.read_state(cache_key, unit)
            except V2StateCorruptionError:
                return None
            if state is None or state.state not in {
                V2UnitRunState.VALIDATED,
                V2UnitRunState.VALIDATED_WITH_CONTENT_ISSUE,
                V2UnitRunState.CANDIDATE_ISOLATED,
            }:
                return None
            outcome = self._from_validated(
                state, unit, shadow_by_id[unit.target.record_local_id]
            )
            if outcome.status is not V2ExtractionUnitStatus.VALIDATED:
                return None
            outcomes.append(outcome)
        return tuple(outcomes)

    def _recover_in_progress(
        self, cache_key: str, units: Sequence[V2ExtractionUnit]
    ) -> None:
        for unit in units:
            try:
                state = self.store.read_state(cache_key, unit)
            except V2StateCorruptionError:
                continue
            if state and state.state is V2UnitRunState.IN_PROGRESS:
                self.store.write_state(
                    V2UnitStateRecord(
                        cache_key,
                        unit.extraction_unit_id,
                        state.unit_identity_sha256,
                        V2UnitRunState.INTERRUPTED,
                        state.attempt_count,
                        state.owner_token,
                        _now(),
                        "v2_interrupted_recovery",
                    )
                )

    def _wait(
        self,
        cache_key: str,
        units: Sequence[V2ExtractionUnit],
        shadow_by_id: Mapping[str, PythonShadowRecord],
        timeout_ms: int,
    ) -> tuple[V2ExtractionUnitOutcome, ...] | None:
        deadline = _now() + max(0, timeout_ms)
        while True:
            complete = self._all_revalidated(cache_key, units, shadow_by_id)
            if complete is not None:
                return complete
            if _now() >= deadline:
                return None
            time.sleep(0.005)

    def _result(
        self,
        disposition: V2RunDisposition,
        execution: V2ExecutionRecord,
        identity: V2CacheIdentity,
        units: Sequence[V2ExtractionUnit],
        outcomes: Sequence[V2ExtractionUnitOutcome],
        provider: Any,
        calls_before: int,
        batch: V2BatchAggregate | None = None,
    ) -> V2ReliableRunResult:
        telemetry: list[Mapping[str, Any]] = []
        for unit in units:
            try:
                state = self.store.read_state(identity.cache_key, unit)
            except V2StateCorruptionError:
                continue
            if state and state.provider_telemetry:
                telemetry.append(state.provider_telemetry)
        return V2ReliableRunResult(
            disposition=disposition,
            execution_id=execution.execution_id,
            cache_key=identity.cache_key,
            cache_identity=identity,
            extraction_units=tuple(units),
            outcomes=tuple(outcomes),
            batch=batch or aggregate_v2_batch(units, outcomes),
            provider_calls=max(0, _provider_calls(provider) - calls_before),
            provider_telemetry=tuple(telemetry),
        )


def _validate_shadow(
    units: Sequence[V2ExtractionUnit], shadow: Sequence[PythonShadowRecord]
) -> dict[str, PythonShadowRecord]:
    by_id = {record.record_local_id: record for record in shadow}
    expected = {unit.target.record_local_id for unit in units}
    if len(by_id) != len(shadow) or set(by_id) != expected:
        raise V2ReliabilityError("Python shadow identities do not match V2 extraction units.")
    unit_by_record = {unit.target.record_local_id: unit for unit in units}
    for record_id, record in by_id.items():
        unit = unit_by_record[record_id]
        target = unit.target
        if (
            record.source_record_id != target.source_record_id
            or record.scope_id != target.scope_id
            or not isinstance(record.line_number, str)
            or not record.line_number
            or tuple(record.fields) != AI_BUSINESS_FIELD_NAMES
        ):
            raise V2ReliabilityError("Python shadow identity or canonical field set is invalid.")
        allowed_evidence = {item.evidence_id for item in unit.evidence_catalog}
        for candidate in record.fields.values():
            if (
                not isinstance(candidate.value, str)
                or not isinstance(candidate.status, str)
                or len(candidate.evidence_ids) != len(set(candidate.evidence_ids))
                or not set(candidate.evidence_ids) <= allowed_evidence
            ):
                raise V2ReliabilityError("Python shadow candidate provenance is invalid.")
    return by_id


def _revalidate_output(
    unit: V2ExtractionUnit,
    output: Any,
    shadow: PythonShadowRecord,
) -> V2ExtractionUnitOutcome:
    validated = validate_full_order_v2_output(output)
    bound = bind_v2_candidates(
        validated,
        target=unit.target,
        evidence_catalog=unit.evidence_catalog,
    )
    record = resolve_v2_record(unit.target, bound, shadow)
    validate_v2_accepted_ai_provenance(record)
    return V2ExtractionUnitOutcome(
        unit=unit,
        status=V2ExtractionUnitStatus.VALIDATED,
        record=record,
    )


def _has_candidate_content_issue(outcome: V2ExtractionUnitOutcome) -> bool:
    if outcome.record is None:
        return False
    return any(
        decision.technical_candidate_status is V2TechnicalCandidateStatus.CONTENT_ISSUE
        or decision.ai_isolated
        or decision.status is V2DecisionStatus.AI_ISOLATED
        for decision in outcome.record.decisions.values()
    )


def _failed_outcome(unit: V2ExtractionUnit, code: str) -> V2ExtractionUnitOutcome:
    return V2ExtractionUnitOutcome(
        unit=unit,
        status=V2ExtractionUnitStatus.FAILED,
        error_code=code,
    )


def _provider_calls(provider: Any) -> int:
    return int(getattr(provider, "extraction_call_count", 0))


def _provider_telemetry(
    provider: Any, identity: V2CacheIdentity, attempt_count: int
) -> dict[str, Any]:
    latest = getattr(provider, "latest_telemetry", None)
    usage = getattr(provider, "usage_summary", None)
    if not isinstance(usage, Mapping):
        usage = {}
    return _validate_telemetry(
        {
            "provider": identity.provider,
            "model": identity.model,
            "request_id": str(getattr(latest, "request_id", "")),
            "input_tokens": int(usage.get("input_tokens", getattr(latest, "input_tokens", 0))),
            "output_tokens": int(usage.get("output_tokens", getattr(latest, "output_tokens", 0))),
            "total_tokens": int(usage.get("total_tokens", getattr(latest, "total_tokens", 0))),
            "latency_ms": int(getattr(latest, "latency_ms", 0)),
            "attempt_count": int(getattr(latest, "attempt_count", attempt_count)),
        }
    )


def _validate_telemetry(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "provider",
        "model",
        "request_id",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "attempt_count",
    }
    if set(value) != expected:
        raise V2StateCorruptionError("V2 telemetry contains non-whitelisted fields.")
    if any(not isinstance(value[name], str) for name in ("provider", "model", "request_id")):
        raise V2StateCorruptionError("V2 telemetry string field is invalid.")
    for name in ("input_tokens", "output_tokens", "total_tokens", "latency_ms", "attempt_count"):
        if isinstance(value[name], bool) or not isinstance(value[name], int) or value[name] < 0:
            raise V2StateCorruptionError("V2 telemetry numeric field is invalid.")
    return dict(value)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> int:
    return time.time_ns() // 1_000_000


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _create_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_canonical(dict(value)).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_json(path: Path, value: Mapping[str, Any], retries: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(_canonical(dict(value)).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(retries + 1):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == retries:
                    raise
                time.sleep(0.005 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)
