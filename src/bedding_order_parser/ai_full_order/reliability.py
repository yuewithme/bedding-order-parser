"""Local, versioned cache and recovery primitives for offline AI chunks."""

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
    FullOrderContractError,
    validate_full_order_output,
)
from bedding_order_parser.ai_full_order.orchestration import (
    BatchAggregate,
    ChunkManifestItem,
    ChunkOutcome,
    ChunkStatus,
    aggregate_batch,
    build_chunk_manifest,
    build_chunk_request,
)
from bedding_order_parser.ai_full_order.preprocessing import PreprocessedWorkbook
from bedding_order_parser.ai_full_order.resolution import (
    FieldResolutionError,
    PythonShadowRecord,
    resolve_records,
)


STATE_FORMAT_VERSION = "1"


class ChunkRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    VALIDATED = "validated"
    FAILED_TRANSIENT = "failed_transient"
    FAILED_DETERMINISTIC = "failed_deterministic"
    INTERRUPTED = "interrupted"


class RunDisposition(StrEnum):
    EXECUTED = "executed"
    CACHED = "cached"
    IN_PROGRESS = "in_progress"
    INTERRUPTED = "interrupted"
    ISOLATED = "isolated"


class ReliabilityError(RuntimeError):
    pass


class StateCorruptionError(ReliabilityError):
    pass


class StateTransitionError(ReliabilityError):
    pass


class IdempotencyConflictError(ReliabilityError):
    pass


class TransientProviderError(ReliabilityError):
    pass


@dataclass(frozen=True)
class CacheIdentity:
    source_file_sha256: str
    provider: str
    model: str
    extraction_schema_version: str
    prompt_version: str
    preprocessor_version: str
    normalization_rules_version: str
    canonical_chunk_manifest_sha256: str

    @property
    def cache_key(self) -> str:
        return _sha(_canonical(asdict(self)))


@dataclass(frozen=True)
class ChunkStateRecord:
    cache_key: str
    chunk_id: str
    state: ChunkRunState
    attempt_count: int = 0
    owner_token: str = ""
    updated_at_ms: int = 0
    error_code: str = ""
    retry_after_ms: int = 0
    validated_output: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_format_version": STATE_FORMAT_VERSION,
            "cache_key": self.cache_key,
            "chunk_id": self.chunk_id,
            "state": self.state.value,
            "attempt_count": self.attempt_count,
            "owner_token": self.owner_token,
            "updated_at_ms": self.updated_at_ms,
            "error_code": self.error_code,
            "retry_after_ms": self.retry_after_ms,
            "validated_output": self.validated_output,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ChunkStateRecord":
        required = {
            "state_format_version", "cache_key", "chunk_id", "state", "attempt_count",
            "owner_token", "updated_at_ms", "error_code", "retry_after_ms", "validated_output",
        }
        if set(raw) != required or raw.get("state_format_version") != STATE_FORMAT_VERSION:
            raise StateCorruptionError("状态文件字段或版本无效。")
        try:
            state = ChunkRunState(raw["state"])
        except (TypeError, ValueError) as exc:
            raise StateCorruptionError("状态文件包含未知状态。") from exc
        strings = ("cache_key", "chunk_id", "owner_token", "error_code")
        ints = ("attempt_count", "updated_at_ms", "retry_after_ms")
        if any(not isinstance(raw[key], str) for key in strings):
            raise StateCorruptionError("状态文件字符串字段无效。")
        if any(not isinstance(raw[key], int) or raw[key] < 0 for key in ints):
            raise StateCorruptionError("状态文件数字字段无效。")
        output = raw["validated_output"]
        if output is not None and not isinstance(output, dict):
            raise StateCorruptionError("严格验证结果无效。")
        if (state is ChunkRunState.VALIDATED) != (output is not None):
            raise StateCorruptionError("状态与严格验证结果不一致。")
        return cls(
            raw["cache_key"], raw["chunk_id"], state, raw["attempt_count"],
            raw["owner_token"], raw["updated_at_ms"], raw["error_code"],
            raw["retry_after_ms"], output,
        )


@dataclass(frozen=True)
class ExecutionRecord:
    client_idempotency_key: str
    business_key: str
    cache_key: str
    execution_id: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExecutionRecord":
        expected = {"client_idempotency_key", "business_key", "cache_key", "execution_id"}
        if set(raw) != expected or any(not isinstance(raw[key], str) for key in expected):
            raise StateCorruptionError("幂等记录无效。")
        return cls(**{key: raw[key] for key in expected})


@dataclass(frozen=True)
class ReliableRunResult:
    disposition: RunDisposition
    execution_id: str
    cache_key: str
    manifest: tuple[ChunkManifestItem, ...]
    outcomes: tuple[ChunkOutcome, ...]
    batch: BatchAggregate
    provider_calls: int


def canonical_manifest_sha256(manifest: Sequence[ChunkManifestItem]) -> str:
    return _sha(_canonical([item.to_dict() for item in sorted(manifest, key=lambda item: item.order)]))


def build_cache_identity(
    manifest: Sequence[ChunkManifestItem],
    *,
    provider: str = "fake_provider",
    model: str = "offline-test",
    extraction_schema_version: str = "1.0",
    prompt_version: str = "1.0",
    preprocessor_version: str = "1.0",
    normalization_rules_version: str = "1.0",
) -> CacheIdentity:
    sources = {item.source_file_sha256 for item in manifest}
    if len(sources) != 1:
        raise ReliabilityError("chunk manifest 源文件身份不一致。")
    return CacheIdentity(
        next(iter(sources)), provider, model, extraction_schema_version, prompt_version,
        preprocessor_version, normalization_rules_version, canonical_manifest_sha256(manifest),
    )


_TRANSITIONS: dict[ChunkRunState | None, frozenset[ChunkRunState]] = {
    None: frozenset({ChunkRunState.PENDING}),
    ChunkRunState.PENDING: frozenset({ChunkRunState.RUNNING, ChunkRunState.INTERRUPTED}),
    ChunkRunState.RUNNING: frozenset({
        ChunkRunState.RUNNING, ChunkRunState.SUCCEEDED, ChunkRunState.FAILED_TRANSIENT,
        ChunkRunState.FAILED_DETERMINISTIC, ChunkRunState.INTERRUPTED,
    }),
    ChunkRunState.SUCCEEDED: frozenset({ChunkRunState.VALIDATED, ChunkRunState.FAILED_DETERMINISTIC}),
    ChunkRunState.FAILED_TRANSIENT: frozenset({ChunkRunState.RUNNING, ChunkRunState.INTERRUPTED}),
    ChunkRunState.INTERRUPTED: frozenset({ChunkRunState.RUNNING}),
    ChunkRunState.VALIDATED: frozenset({ChunkRunState.VALIDATED}),
    ChunkRunState.FAILED_DETERMINISTIC: frozenset({ChunkRunState.FAILED_DETERMINISTIC}),
}


class FileLease:
    """Atomic create establishes a leader across processes sharing the same store."""

    def __init__(self, store: "OfflineReliabilityStore", cache_key: str, lease_ms: int) -> None:
        self.store, self.cache_key, self.lease_ms = store, cache_key, lease_ms
        self.owner_token = secrets.token_hex(16)
        self.acquired = False

    @property
    def path(self) -> Path:
        return self.store.lock_path(self.cache_key)

    def try_acquire(self) -> bool:
        try:
            _create_json(self.path, self._payload())
            self.acquired = True
            return True
        except FileExistsError:
            lease = self._read()
            if lease is None or self._healthy(lease):
                return False
            self._replace_expired(lease)
            try:
                _create_json(self.path, self._payload())
                self.acquired = True
                return True
            except FileExistsError:
                return False

    def heartbeat(self) -> None:
        if not self.acquired or not self._owned():
            raise StateTransitionError("single-flight lease 已不属于当前执行者。")
        _atomic_json(self.path, self._payload(), self.store.replace_retries)

    def release(self) -> None:
        if self.acquired and self._owned():
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.acquired = False

    def _payload(self) -> dict[str, Any]:
        return {"owner_token": self.owner_token, "heartbeat_at_ms": _now()}

    def _read(self) -> dict[str, Any] | None:
        try:
            raw = _read_json(self.path)
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict) or not isinstance(raw.get("owner_token"), str):
            return None
        if not isinstance(raw.get("heartbeat_at_ms"), int):
            return None
        return raw

    def _healthy(self, lease: Mapping[str, Any]) -> bool:
        return _now() - int(lease["heartbeat_at_ms"]) <= self.lease_ms

    def _owned(self) -> bool:
        lease = self._read()
        return lease is not None and lease["owner_token"] == self.owner_token

    def _replace_expired(self, observed: Mapping[str, Any]) -> None:
        try:
            before = self.path.read_bytes()
            current = self._read()
            if current != observed or current is None or self._healthy(current):
                return
            if self.path.read_bytes() != before:
                return
            os.replace(self.path, self.path.with_name(f"{self.path.name}.expired-{self.owner_token}"))
        except FileNotFoundError:
            return


class OfflineReliabilityStore:
    def __init__(self, root: str | Path, *, replace_retries: int = 3) -> None:
        self.root = Path(root).resolve()
        self.replace_retries = replace_retries

    def state_path(self, cache_key: str, chunk_id: str) -> Path:
        return self.root / "chunks" / cache_key / f"{_sha(chunk_id)}.json"

    def lock_path(self, cache_key: str) -> Path:
        return self.root / "locks" / f"{cache_key}.lease.json"

    def _idempotency_path(self, key: str) -> Path:
        return self.root / "idempotency" / f"{_sha(key)}.json"

    def read_state(self, cache_key: str, chunk_id: str) -> ChunkStateRecord | None:
        path = self.state_path(cache_key, chunk_id)
        if not path.exists():
            return None
        try:
            state = ChunkStateRecord.from_dict(_read_json(path))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise StateCorruptionError(f"状态文件损坏：{path.name}") from exc
        if state.cache_key != cache_key or state.chunk_id != chunk_id:
            raise StateCorruptionError("状态文件身份与路径不一致。")
        return state

    def write_state(self, record: ChunkStateRecord) -> None:
        existing = self.read_state(record.cache_key, record.chunk_id)
        previous = existing.state if existing else None
        if record.state not in _TRANSITIONS[previous]:
            raise StateTransitionError(f"禁止状态转换：{previous} -> {record.state}")
        if existing and existing.state in {
            ChunkRunState.VALIDATED, ChunkRunState.FAILED_DETERMINISTIC,
        } and existing != record:
            raise StateTransitionError("终态不能被旧写入覆盖。")
        _atomic_json(self.state_path(record.cache_key, record.chunk_id), record.to_dict(), self.replace_retries)

    def force_retry_deterministic_once(self, cache_key: str, chunk_id: str) -> ChunkStateRecord:
        """Explicit upper-layer override; it never lets a stale writer regress a terminal state."""
        current = self.read_state(cache_key, chunk_id)
        if current is None or current.state is not ChunkRunState.FAILED_DETERMINISTIC:
            raise StateTransitionError("只有确定性失败块可以强制重试。")
        if current.attempt_count != 1:
            raise StateTransitionError("同一确定性失败只允许显式强制重试一次。")
        pending = ChunkStateRecord(
            cache_key, chunk_id, ChunkRunState.PENDING, current.attempt_count,
            updated_at_ms=_now(), error_code="forced_retry_once",
        )
        # This is the sole audited terminal-state override, called by the lease leader.
        _atomic_json(self.state_path(cache_key, chunk_id), pending.to_dict(), self.replace_retries)
        return pending

    def claim_execution(self, client_key: str, business_key: str, cache_key: str) -> ExecutionRecord:
        execution_id = "exec:" + _sha(_canonical({
            "client_key": client_key, "business_key": business_key, "cache_key": cache_key,
        }))[:24]
        candidate = ExecutionRecord(client_key, business_key, cache_key, execution_id)
        path = self._idempotency_path(client_key)
        try:
            _create_json(path, candidate.to_dict())
            return candidate
        except FileExistsError:
            try:
                existing = ExecutionRecord.from_dict(_read_json(path))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise StateCorruptionError("幂等记录损坏。") from exc
            if existing != candidate:
                raise IdempotencyConflictError("同一客户端幂等键不能复用到其他合同或业务。")
            return existing

    def lease(self, cache_key: str, lease_ms: int) -> FileLease:
        return FileLease(self, cache_key, lease_ms)


class OfflineReliableOrchestrator:
    def __init__(
        self,
        store: OfflineReliabilityStore,
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
        cache_identity: CacheIdentity | None = None,
        wait_timeout_ms: int = 0,
        interrupt_after_validated_chunks: int | None = None,
        force_deterministic_retry: bool = False,
    ) -> ReliableRunResult:
        manifest = build_chunk_manifest(preprocessed)
        identity = cache_identity or build_cache_identity(manifest)
        if identity.source_file_sha256 != preprocessed.source_file_sha256:
            raise ReliabilityError("缓存身份与预处理源文件不一致。")
        cache_key = identity.cache_key
        execution = self.store.claim_execution(client_idempotency_key, business_key, cache_key)
        cached = self._all_validated(cache_key, manifest, preprocessed, python_shadow)
        if cached is not None:
            return self._result(RunDisposition.CACHED, execution, cache_key, manifest, cached, provider)

        lease = self.store.lease(cache_key, self.lease_ms)
        if not lease.try_acquire():
            waited = self._wait(cache_key, manifest, preprocessed, python_shadow, wait_timeout_ms)
            if waited is not None:
                return self._result(RunDisposition.CACHED, execution, cache_key, manifest, waited, provider)
            return self._result(RunDisposition.IN_PROGRESS, execution, cache_key, manifest, (), provider)

        try:
            # Only the lease owner may classify an abandoned running state.
            self._recover_running(cache_key, manifest)
            cached = self._all_validated(cache_key, manifest, preprocessed, python_shadow)
            if cached is not None:
                return self._result(
                    RunDisposition.CACHED, execution, cache_key, manifest, cached, provider,
                )
            if preprocessed.structure_status == "ambiguous":
                provider.resolve_structure({"cache_key": cache_key, "chunks": [item.to_dict() for item in manifest]})
            outcomes: list[ChunkOutcome] = []
            completed_here = 0
            for item in manifest:
                lease.heartbeat()
                outcome = self._run_chunk(
                    cache_key, item, preprocessed, provider, python_shadow, lease.owner_token, force_deterministic_retry,
                )
                outcomes.append(outcome)
                if outcome.status is ChunkStatus.VALIDATED:
                    completed_here += 1
                if interrupt_after_validated_chunks is not None and completed_here >= interrupt_after_validated_chunks:
                    return self._result(
                        RunDisposition.INTERRUPTED, execution, cache_key, manifest, outcomes, provider,
                        aggregate_batch(manifest, outcomes),
                    )
            batch = aggregate_batch(manifest, outcomes)
            return self._result(
                RunDisposition.EXECUTED if batch.ready_for_downstream else RunDisposition.ISOLATED,
                execution, cache_key, manifest, outcomes, provider, batch,
            )
        finally:
            lease.release()

    def _run_chunk(
        self, cache_key: str, item: ChunkManifestItem, preprocessed: PreprocessedWorkbook,
        provider: Any, shadow: Sequence[PythonShadowRecord], owner_token: str, force_deterministic_retry: bool,
    ) -> ChunkOutcome:
        try:
            prior = self.store.read_state(cache_key, item.chunk_id)
        except StateCorruptionError as exc:
            return ChunkOutcome(item, ChunkStatus.FAILED, error_code="state_corrupt", error_message=str(exc))
        if prior and prior.state is ChunkRunState.VALIDATED:
            return self._from_validated(prior, item, preprocessed, shadow)
        if prior and prior.state is ChunkRunState.FAILED_DETERMINISTIC:
            if not force_deterministic_retry or prior.attempt_count != 1:
                return ChunkOutcome(item, ChunkStatus.FAILED, error_code=prior.error_code)
            prior = self.store.force_retry_deterministic_once(cache_key, item.chunk_id)
        if prior and prior.state is ChunkRunState.FAILED_TRANSIENT and prior.attempt_count >= self.max_transient_attempts:
            return ChunkOutcome(item, ChunkStatus.FAILED, error_code="transient_attempt_limit")
        attempts = (prior.attempt_count if prior else 0) + 1
        if prior is None:
            self.store.write_state(ChunkStateRecord(cache_key, item.chunk_id, ChunkRunState.PENDING, updated_at_ms=_now()))
        self.store.write_state(ChunkStateRecord(
            cache_key, item.chunk_id, ChunkRunState.RUNNING, attempts, owner_token, _now(),
        ))
        request = build_chunk_request(preprocessed, item)
        try:
            output = provider.extract(request)
            validate_full_order_output(output, request=request)
            result = resolve_records(output, request=request, python_shadow=_shadow_for(shadow, request))
        except (TransientProviderError, TimeoutError, ConnectionError) as exc:
            failed = ChunkStateRecord(
                cache_key, item.chunk_id, ChunkRunState.FAILED_TRANSIENT, attempts, owner_token, _now(),
                "transient_provider_failure", _now() + self.transient_backoff_ms,
            )
            self.store.write_state(failed)
            return ChunkOutcome(item, ChunkStatus.FAILED, error_code=failed.error_code, error_message=str(exc))
        except (FullOrderContractError, FieldResolutionError, ValueError, TypeError) as exc:
            failed = ChunkStateRecord(
                cache_key, item.chunk_id, ChunkRunState.FAILED_DETERMINISTIC, attempts, owner_token, _now(),
                "schema_or_evidence_failure",
            )
            self.store.write_state(failed)
            return ChunkOutcome(item, ChunkStatus.FAILED, error_code=failed.error_code, error_message=str(exc))
        self.store.write_state(ChunkStateRecord(
            cache_key, item.chunk_id, ChunkRunState.SUCCEEDED, attempts, owner_token, _now(),
        ))
        saved = ChunkStateRecord(
            cache_key, item.chunk_id, ChunkRunState.VALIDATED, attempts, owner_token, _now(),
            validated_output=dict(output),
        )
        self.store.write_state(saved)
        return ChunkOutcome(item, ChunkStatus.VALIDATED, tuple(result))

    def _from_validated(
        self, state: ChunkStateRecord, item: ChunkManifestItem, preprocessed: PreprocessedWorkbook,
        shadow: Sequence[PythonShadowRecord],
    ) -> ChunkOutcome:
        try:
            request = build_chunk_request(preprocessed, item)
            assert state.validated_output is not None
            validate_full_order_output(state.validated_output, request=request)
            return ChunkOutcome(
                item, ChunkStatus.VALIDATED,
                tuple(resolve_records(state.validated_output, request=request, python_shadow=_shadow_for(shadow, request))),
            )
        except (AssertionError, FullOrderContractError, FieldResolutionError, ValueError, TypeError) as exc:
            return ChunkOutcome(item, ChunkStatus.FAILED, error_code="cached_validation_failure", error_message=str(exc))

    def _all_validated(
        self, cache_key: str, manifest: Sequence[ChunkManifestItem], preprocessed: PreprocessedWorkbook,
        shadow: Sequence[PythonShadowRecord],
    ) -> tuple[ChunkOutcome, ...] | None:
        outcomes: list[ChunkOutcome] = []
        for item in manifest:
            try:
                state = self.store.read_state(cache_key, item.chunk_id)
            except StateCorruptionError:
                return None
            if state is None or state.state is not ChunkRunState.VALIDATED:
                return None
            outcome = self._from_validated(state, item, preprocessed, shadow)
            if outcome.status is not ChunkStatus.VALIDATED:
                return None
            outcomes.append(outcome)
        return tuple(outcomes)

    def _recover_running(self, cache_key: str, manifest: Sequence[ChunkManifestItem]) -> None:
        for item in manifest:
            try:
                state = self.store.read_state(cache_key, item.chunk_id)
            except StateCorruptionError:
                continue
            if state and state.state is ChunkRunState.RUNNING:
                self.store.write_state(ChunkStateRecord(
                    cache_key, item.chunk_id, ChunkRunState.INTERRUPTED, state.attempt_count,
                    state.owner_token, _now(), "interrupted_recovery",
                ))

    def _wait(
        self, cache_key: str, manifest: Sequence[ChunkManifestItem], preprocessed: PreprocessedWorkbook,
        shadow: Sequence[PythonShadowRecord], timeout_ms: int,
    ) -> tuple[ChunkOutcome, ...] | None:
        deadline = _now() + max(timeout_ms, 0)
        while True:
            complete = self._all_validated(cache_key, manifest, preprocessed, shadow)
            if complete is not None:
                return complete
            if _now() >= deadline:
                return None
            time.sleep(min(0.02, max(0.001, (deadline - _now()) / 1000)))

    def _result(
        self, disposition: RunDisposition, execution: ExecutionRecord, cache_key: str,
        manifest: Sequence[ChunkManifestItem], outcomes: Sequence[ChunkOutcome], provider: Any,
        batch: BatchAggregate | None = None,
    ) -> ReliableRunResult:
        return ReliableRunResult(
            disposition, execution.execution_id, cache_key, tuple(manifest), tuple(outcomes),
            batch or aggregate_batch(manifest, outcomes),
            int(getattr(provider, "extraction_call_count", 0)),
        )


def _shadow_for(
    records: Sequence[PythonShadowRecord], request: Mapping[str, Any],
) -> tuple[PythonShadowRecord, ...]:
    expected = {record["record_local_id"] for record in request["records"]}
    selected = tuple(record for record in records if record.record_local_id in expected)
    if {record.record_local_id for record in selected} != expected:
        raise FieldResolutionError("Python shadow records do not match the chunk request.")
    return selected


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
    temp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(_canonical(dict(value)).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(retries + 1):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == retries:
                    raise
                time.sleep(0.005 * (attempt + 1))
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
