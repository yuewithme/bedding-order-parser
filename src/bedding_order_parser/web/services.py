"""Application services for local web parsing jobs."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from bedding_order_parser.ai_full_order.contracts import (
    FullOrderContractError,
    ParseMode,
    parse_mode_from_value,
    safe_contract_diagnostic,
    V2_CONTRACT_VERSION,
)
from bedding_order_parser.ai_full_order.structure_manifest import (
    LAYOUT_CONTRACT_VERSION,
    LAYOUT_PROMPT_VERSION,
    STRUCTURE_CONTEXT_VERSION,
)
from bedding_order_parser.ai_full_order.revisions import (
    RevisionAction,
    RevisionError,
    RevisionNotSupported,
    RevisionRequest,
    apply_revision,
    initialize_revision_history,
    resolve_current_bundle,
    revision_summary,
)
from bedding_order_parser.dictionaries.product_validation import (
    DEFAULT_RULES_PATH,
    DEFAULT_STYLES_PATH,
)
from bedding_order_parser.llm.service import LLMService
from bedding_order_parser.llm.settings import LLMSettings
from bedding_order_parser.llm.transport import JSONTransport
from bedding_order_parser.web.ai_advisory import AIAdvisoryManager
from bedding_order_parser.web.ai_full_order_dependencies import (
    build_ai_enhanced_dependencies,
)
from bedding_order_parser.web.ai_full_order_service import (
    AIEnhancedDependencies,
    AIEnhancedJobPause,
    AIEnhancedJobResult,
    AI_JOB_STAGES,
    run_ai_enhanced_job,
    run_ai_enhanced_v2_job,
)
from bedding_order_parser.web.ai_review import (
    ai_review_summary,
    build_ai_review_view,
    unavailable_ai_review,
)
from bedding_order_parser.web.job_persistence import (
    process_is_alive,
    write_json_atomic,
)


LOGGER = logging.getLogger("bedding_order_parser.web.services")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WEB_ROOT = PROJECT_ROOT / "data" / "output" / "web"
DEFAULT_STORE_PATH = (
    PROJECT_ROOT / "data" / "output" / "material_store" / "material_master.sqlite3"
)
DEFAULT_INDEX_DIR = PROJECT_ROOT / "data" / "output" / "material_vector_index"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
STAGE_NAMES = (
    "文件读取",
    "订单字段提取",
    "字典校验",
    "物料匹配",
    "结果生成",
)
ARTIFACT_LABELS = {
    "business": "正式业务 JSON",
    "diagnostic": "解析诊断 JSON",
    "validation": "字典验证 JSON",
}
ARTIFACT_ROLES = (
    "official_result",
    "parse_diagnostics",
    "dictionary_validation",
    "material_candidates",
    "material_summary",
)
ROLE_ALIASES = {
    "business": "official_result",
    "diagnostic": "parse_diagnostics",
    "validation": "dictionary_validation",
    "matches": "material_candidates",
    "match_summary": "material_summary",
    **{role: role for role in ARTIFACT_ROLES},
}
STANDARD_ROLE_ARTIFACTS = {
    "official_result": "business",
    "parse_diagnostics": "diagnostic",
    "dictionary_validation": "validation",
    "material_candidates": "matches",
    "material_summary": "match_summary",
}
AI_BUNDLE_ARTIFACTS = {
    "official_result": "ai_full_order.json",
    "parse_diagnostics": "ai_full_order_parse_report.json",
    "dictionary_validation": "ai_full_order_dictionary_validation.json",
    "material_candidates": "material_match_candidates.json",
    "material_summary": "material_match_summary.json",
}
PARSE_CONTRACT_VERSION = "1.0"
AI_CONTRACT_V1 = "1.0"
AI_CONTRACT_V2 = V2_CONTRACT_VERSION
AI_STAGE_PRESENTATION = {
    "preprocessing": (5, 0, "正在读取订单"),
    "structure_resolution": (12, 0, "正在确认表格结构"),
    "python_shadow": (22, 0, "正在执行本地解析对照"),
    "ai_extraction": (35, 1, "正在提取订单候选字段"),
    "evidence_binding": (58, 1, "正在绑定来源证据"),
    "field_resolution": (68, 1, "正在处理字段差异"),
    "cache_revalidation": (76, 1, "正在复核本地缓存"),
    "dictionary_validation": (82, 2, "正在验证业务字段"),
    "material_matching": (88, 3, "正在匹配参考物料"),
    "publication": (94, 4, "正在生成结果"),
    "completed": (100, 4, "解析完成"),
    "awaiting_user_decision": (95, 4, "等待你的处理决定"),
    # Legacy V1 whole-order stages retain the same five-step presentation.
    "python_shadow_parse": (22, 0, "正在执行本地解析对照"),
    "local_structure_resolution": (28, 0, "正在分析表格结构"),
    "ai_layout_recognition": (32, 0, "正在识别订单区域"),
    "ai_block_extraction": (35, 1, "正在提取订单字段"),
    "evidence_validation": (58, 1, "正在验证来源证据"),
    "publishing": (94, 4, "正在生成结果"),
}
DETAIL_FIELDS = (
    ("spec", "规格"),
    ("color", "颜色"),
    ("fabric", "面料"),
    ("composition", "成分"),
    ("style", "款式"),
)

ACTIVE_JOB_STATUSES = frozenset({"queued", "running", "processing"})
TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "interrupted"})
LEGACY_STALE_SECONDS = 30 * 60
RESTART_INTERRUPTION_MESSAGE = "上次运行异常结束，任务已标记为中断，请重新提交。"


class WebJobError(RuntimeError):
    """Raised when a local web job cannot be created or read."""


class JobInterrupted(WebJobError):
    """Raised internally when desktop shutdown interrupts a queued job."""


class DaemonJobExecutor:
    """Single-worker executor whose thread cannot keep the desktop process alive."""

    def __init__(self) -> None:
        self._queue: Queue[tuple[Any, tuple[Any, ...]] | None] = Queue()
        self._accepting = True
        self._worker_thread = threading.Thread(
            target=self._worker,
            name="bedding-web-worker",
            daemon=True,
        )
        self._worker_thread.start()

    def submit(self, function, *args) -> None:
        if not self._accepting:
            raise RuntimeError("任务执行器已经关闭。")
        self._queue.put((function, args))

    def shutdown(
        self, wait: bool = False, *, cancel_futures: bool = True
    ) -> None:
        self._accepting = False
        if cancel_futures:
            while True:
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except Empty:
                    break
        self._queue.put(None)
        if wait and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2)

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                function, args = item
                function(*args)
            finally:
                self._queue.task_done()


class JobService:
    """Persist and run local parsing jobs without changing business algorithms."""

    def __init__(
        self,
        root: str | Path = DEFAULT_WEB_ROOT,
        *,
        store_path: str | Path = DEFAULT_STORE_PATH,
        index_dir: str | Path = DEFAULT_INDEX_DIR,
        dictionary_rules_path: str | Path = DEFAULT_RULES_PATH,
        dictionary_styles_path: str | Path = DEFAULT_STYLES_PATH,
        executor: Any | None = None,
        llm_service: LLMService | None = None,
        desktop_mode: bool = False,
        ai_enhanced_dependencies: AIEnhancedDependencies | None = None,
        ai_enhanced_settings: LLMSettings | None = None,
        ai_enhanced_transport: JSONTransport | None = None,
        ai_enhanced_dictionary_validator: Any | None = None,
        ai_enhanced_material_matcher: Any | None = None,
        ai_enhanced_downstream_factory: Any | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.jobs_root = self.root / "jobs"
        self.store_path = Path(store_path).resolve()
        self.index_dir = Path(index_dir).resolve()
        self.dictionary_rules_path = Path(dictionary_rules_path).resolve()
        self.dictionary_styles_path = Path(dictionary_styles_path).resolve()
        self.llm_service = llm_service or LLMService()
        self.ai_enhanced_settings = ai_enhanced_settings or LLMSettings.from_environment()
        self.ai_enhanced_dependencies = ai_enhanced_dependencies or build_ai_enhanced_dependencies(
            settings=self.ai_enhanced_settings,
            transport=ai_enhanced_transport,
            dictionary_validator=ai_enhanced_dictionary_validator,
            material_matcher=ai_enhanced_material_matcher,
            downstream_factory=ai_enhanced_downstream_factory,
        )
        self.desktop_mode = desktop_mode
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._session_job_ids: set[str] = set()
        self.session_id = uuid.uuid4().hex
        self.owner_pid = os.getpid()
        self.recovery_errors: list[str] = []
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        if self.desktop_mode:
            self.recover_stale_jobs()
        self.accepting = True
        self._executor = executor or DaemonJobExecutor()
        self.ai_advisory = AIAdvisoryManager(
            self.jobs_root,
            self.llm_service,
            self._executor,
        )

    def create_job(
        self,
        file_name: str,
        content: bytes,
        *,
        parse_mode: str = ParseMode.STANDARD.value,
    ) -> dict[str, Any]:
        if not self.accepting:
            raise WebJobError("应用正在关闭，暂时不能创建新任务。")
        safe_name = Path(file_name).name.strip()
        if not safe_name or safe_name in {".", ".."}:
            raise WebJobError("请选择有效的 Excel 文件。")
        if Path(safe_name).suffix.lower() != ".xlsx":
            raise WebJobError("仅支持 .xlsx 格式的 Excel 文件。")
        if not content:
            raise WebJobError("上传文件为空，请重新选择。")
        if len(content) > MAX_UPLOAD_BYTES:
            raise WebJobError("文件超过 25 MB，请确认后重新上传。")
        if not content.startswith(b"PK"):
            raise WebJobError("文件不是有效的 .xlsx 工作簿。")
        try:
            mode = parse_mode_from_value(parse_mode)
        except (FullOrderContractError, TypeError) as exc:
            raise WebJobError("解析模式仅支持 standard 或 ai_enhanced。") from exc
        if mode is ParseMode.AI_ENHANCED:
            preflight = self.ai_enhanced_preflight()
            if preflight["provider_ready"] is not True:
                raise WebJobError(str(preflight["unavailable_reason_text"]))

        job_id = uuid.uuid4().hex
        job_root = self._job_root(job_id)
        input_dir = job_root / "input"
        result_dir = job_root / "results"
        match_dir = job_root / "match"
        input_dir.mkdir(parents=True)
        result_dir.mkdir()
        match_dir.mkdir()
        input_path = input_dir / safe_name
        self._write_bytes_atomic(input_path, content)

        now = self._now()
        source_sha256 = hashlib.sha256(content).hexdigest()
        ai_contract_version = (
            AI_CONTRACT_V2 if mode is ParseMode.AI_ENHANCED else ""
        )
        job = {
            "id": job_id,
            "file_name": safe_name,
            "file_size": len(content),
            "created_at": now,
            "completed_at": "",
            "elapsed_seconds": 0.0,
            "status": "queued",
            "progress": 0,
            "current_stage": "等待开始",
            "stages": [
                {"name": name, "status": "waiting"} for name in STAGE_NAMES
            ],
            "error": "",
            "worker_diagnostics": {},
            "sheet": "",
            "record_count": 0,
            "summary": {
                "high_match": 0,
                "partial_match": 0,
                "conflict": 0,
            },
            "artifacts": {},
            "artifact_roles": {},
            "input_sha256": source_sha256,
            "parse_mode": mode.value,
            "requested_parse_mode": mode.value,
            "effective_parse_mode": mode.value,
            "parse_contract_version": PARSE_CONTRACT_VERSION,
            "parse_mode_source": "explicit",
            "ai_contract_version": ai_contract_version,
            "ai_contract_source": (
                "new_job_v2" if ai_contract_version else "not_applicable"
            ),
            "source_identity": {
                "sha256": source_sha256,
                "size_bytes": len(content),
            },
            "client_idempotency_identity": (
                f"ai-full-order-v2:{job_id}" if ai_contract_version else ""
            ),
            "business_identity": (
                f"desktop-job-v2:{job_id}" if ai_contract_version else ""
            ),
            "runtime_cache_identity": {
                "cache_key": "",
                "manifest_sha256": "",
                "execution_id": "",
                "disposition": "",
            },
            "ai_user_decision": {
                "status": "not_required",
                "action": "",
                "decided_at": "",
            },
            "fallback": {
                "status": "not_requested",
                "reason": "",
                "user_confirmed_at": "",
            },
            "ai_execution": self._initial_ai_execution(),
            "owner_session_id": self.session_id,
            "owner_pid": self.owner_pid,
        }
        self._write_job(job)
        self._session_job_ids.add(job_id)
        return self.public_job(job)

    def start_job(self, job_id: str) -> None:
        if not self.accepting:
            raise WebJobError("应用正在关闭，暂时不能启动任务。")
        self._require_job_id(job_id)
        self._executor.submit(self._run_job, job_id)

    def reprocess_ai_job_as_standard(
        self, job_id: str, *, operation_id: str
    ) -> dict[str, Any]:
        """Create and start a separate Standard Job from an AI Job's original upload."""
        self._require_job_id(job_id)
        operation_id = self._validate_reprocess_operation_id(operation_id)
        with self._lock_for(job_id):
            existing = self._find_reprocess_operation(job_id, operation_id)
            if existing is not None:
                return {
                    "new_job_id": str(existing["id"]),
                    "reused": True,
                    "job": self.public_job(existing),
                }

            active_child = self._find_active_standard_reprocess(job_id)
            if active_child is not None:
                return {
                    "new_job_id": str(active_child["id"]),
                    "reused": True,
                    "job": self.public_job(active_child),
                }

            original = self._read_job(job_id)
            mode = self._mode_view(original)
            if (
                mode["parse_mode"] != ParseMode.AI_ENHANCED.value
                or mode["effective_parse_mode"] != ParseMode.AI_ENHANCED.value
            ):
                raise WebJobError("只有等待处理的AI增强任务可以使用标准解析重新处理。")
            if str(original.get("status", "")) != "awaiting_user_decision":
                raise WebJobError("当前任务不处于可使用标准解析重新处理的状态。")

            file_name, content, source_sha256 = self._trusted_original_upload(
                job_id, original
            )
            child = self.create_job(
                file_name, content, parse_mode=ParseMode.STANDARD.value
            )
            child_id = str(child["id"])
            try:
                stored_child = self._read_job(child_id)
                if str(stored_child.get("source_identity", {}).get("sha256", "")) != source_sha256:
                    raise WebJobError("新标准任务的原始文件身份校验失败。")
                self._update_job(
                    child_id,
                    {
                        "reprocess": {
                            "origin_job_id": job_id,
                            "reason": "standard_reprocess",
                            "operation_id": operation_id,
                            "created_at": self._now(),
                        }
                    },
                )
                self.start_job(child_id)
            except Exception as exc:
                self._update_job(
                    child_id,
                    {
                        "status": "failed",
                        "completed_at": self._now(),
                        "current_stage": "标准解析重新处理未启动",
                        "error": "标准解析重新处理未能启动，原AI任务保持不变。",
                    },
                )
                if isinstance(exc, WebJobError):
                    raise
                raise WebJobError("标准解析重新处理未能启动，原AI任务保持不变。") from exc
            return {
                "new_job_id": child_id,
                "reused": False,
                "job": self.get_job(child_id),
            }

    def capabilities(self) -> dict[str, Any]:
        llm = dict(self.llm_service.capabilities())
        llm.update(
            {
                "business_integration": True,
                "mode": "single_record_advisory",
                "manual_confirmation_required": True,
                "automatic_calls": False,
            }
        )
        return {
            "llm": llm,
            "desktop": {"mode": self.desktop_mode},
            "ai_full_order": self.ai_enhanced_preflight(),
        }

    def ai_enhanced_preflight(self) -> dict[str, Any]:
        """Return local-only V2 support, configuration, and run readiness separately."""
        dependencies = self.ai_enhanced_dependencies
        dependency_ready = (
            dependencies is not None
            and dependencies.contract_version == AI_CONTRACT_V2
            and dependencies.downstream_ready
        )
        if dependency_ready:
            reason_code = ""
            reason_text = ""
        else:
            reason_code, reason_text = self._ai_enhanced_unavailable_reason()
        configured = dependency_ready or self.ai_enhanced_settings.is_ready()
        return {
            # ready/reason remain for C2 compatibility; new callers use explicit fields.
            "ready": dependency_ready,
            "reason": reason_text,
            "v2_backend_available": True,
            "provider_configured": configured,
            "provider_ready": dependency_ready,
            "real_call_requires_user_confirmation": True,
            "unavailable_reason_code": reason_code,
            "unavailable_reason_text": reason_text,
            "provider": dependencies.provider_name if dependencies else "",
            "model": dependencies.model_name if dependencies else "",
            "max_logical_calls": dependencies.max_logical_calls if dependencies else 0,
            "token_estimate": None,
            "cost_estimate": None,
        }

    def _ai_enhanced_unavailable_reason(self) -> tuple[str, str]:
        """Map local-only readiness facts to a fixed, non-sensitive Chinese message."""

        status = self.ai_enhanced_settings.configuration_status()
        reasons = {
            "disabled": (
                "AI_PROVIDER_DISABLED",
                "AI整单解析尚未在本机启用，完成配置后即可提交。",
            ),
            "configuration_error": (
                "AI_PROVIDER_CONFIGURATION_INVALID",
                "AI整单解析本机配置无效，请检查已批准的配置项。",
            ),
            "provider_not_configured": (
                "AI_PROVIDER_NOT_CONFIGURED",
                "AI整单解析尚未配置服务提供方，当前不能启动任务。",
            ),
            "unsupported_provider": (
                "AI_PROVIDER_UNSUPPORTED",
                "AI整单解析当前服务提供方不受支持，当前不能启动任务。",
            ),
            "api_key_missing": (
                "AI_API_KEY_MISSING",
                "AI整单解析尚未配置 API Key，当前不能启动任务。",
            ),
            "model_missing": (
                "AI_MODEL_MISSING",
                "AI整单解析尚未配置模型，当前不能启动任务。",
            ),
        }
        if status == "ready":
            dependencies = self.ai_enhanced_dependencies
            if dependencies is not None:
                return (
                    "AI_V2_COMPOSITION_INVALID",
                    "AI整单解析内部协议未就绪，当前不能启动任务。",
                )
            return (
                "AI_DOWNSTREAM_NOT_READY",
                "AI整单解析下游校验或匹配组件尚未就绪，当前不能启动任务。",
            )
        return reasons.get(
            status,
            (
                "AI_PROVIDER_NOT_READY",
                "AI整单解析服务当前未就绪，完成配置后即可提交。",
            ),
        )

    def active_jobs(self) -> list[dict[str, Any]]:
        return [
            job
            for job in self.list_jobs()
            if job["id"] in self._session_job_ids
            and job["status"] in ACTIVE_JOB_STATUSES
        ]

    def stop_accepting(self) -> None:
        self.accepting = False
        self.ai_advisory.stop_accepting()

    def active_ai_advisories(self) -> list[dict[str, Any]]:
        return self.ai_advisory.active()

    def interrupt_active_jobs(self) -> None:
        for job in self.active_jobs():
            is_v2 = self._ai_contract_view(job).get("ai_contract_version") == AI_CONTRACT_V2
            if is_v2:
                execution = self._safe_ai_execution(job.get("ai_execution", {}))
                execution.update(
                    {
                        "stage": "awaiting_user_decision",
                        "safe_error_code": "AI_V2_INTERRUPTED",
                        "has_publishable_result": False,
                    }
                )
                updates = {
                    "status": "awaiting_user_decision",
                    "current_stage": "awaiting_user_decision",
                    "error": "应用关闭，V2 任务已安全中断，可继续未验证单元。",
                    "interruption_reason": "application_closed",
                    "previous_status": job["status"],
                    "ai_execution": execution,
                    "ai_user_decision": {
                        "status": "pending",
                        "action": "",
                        "decided_at": "",
                    },
                }
            else:
                updates = {
                    "status": "interrupted",
                    "current_stage": "任务已中断",
                    "completed_at": self._now(),
                    "error": "应用关闭，任务已安全中断。",
                    "interruption_reason": "application_closed",
                    "previous_status": job["status"],
                }
            self._update_job(
                job["id"],
                updates,
            )

    def close(self) -> None:
        self.stop_accepting()
        self.interrupt_active_jobs()
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=False)
        self.llm_service.close()
        provider = getattr(self.ai_enhanced_dependencies, "provider", None)
        close = getattr(provider, "close", None)
        if callable(close):
            close()

    def recover_stale_jobs(self) -> int:
        """Mark unsupported active jobs from an earlier desktop session interrupted."""
        recovered_count = 0
        for metadata_path in self.jobs_root.glob("*/job.json"):
            job_id = metadata_path.parent.name
            try:
                self._require_job_id(job_id)
                lock = self._lock_for(job_id)
                with lock:
                    job = self._read_json(metadata_path)
                    status = str(job.get("status", ""))
                    if status not in ACTIVE_JOB_STATUSES:
                        continue
                    if job_id in self._session_job_ids:
                        continue
                    if str(job.get("owner_session_id", "")) == self.session_id:
                        continue

                    owner_pid = self._valid_owner_pid(job.get("owner_pid"))
                    if owner_pid is not None:
                        if self._owner_process_alive(owner_pid):
                            continue
                    elif not self._legacy_job_is_stale(job):
                        continue

                    is_v2 = (
                        self._ai_contract_view(job).get("ai_contract_version")
                        == AI_CONTRACT_V2
                    )
                    if is_v2:
                        execution = self._safe_ai_execution(job.get("ai_execution", {}))
                        execution.update(
                            {
                                "stage": "awaiting_user_decision",
                                "safe_error_code": "AI_V2_INTERRUPTED",
                                "has_publishable_result": False,
                            }
                        )
                        job.update(
                            {
                                "status": "awaiting_user_decision",
                                "current_stage": "awaiting_user_decision",
                                "error": "上次 V2 运行异常结束，可继续未验证单元。",
                                "ai_execution": execution,
                                "ai_user_decision": {
                                    "status": "pending",
                                    "action": "",
                                    "decided_at": "",
                                },
                            }
                        )
                    else:
                        job.update(
                            {
                                "status": "interrupted",
                                "current_stage": "任务已中断",
                                "completed_at": self._now(),
                                "error": RESTART_INTERRUPTION_MESSAGE,
                            }
                        )
                    job.update(
                        {
                            "interruption_reason": "application_restarted",
                            "previous_status": status,
                            "recovered_at": self._now(),
                            "recovery_session_id": self.session_id,
                        }
                    )
                    self._write_json_atomic(metadata_path, job)
                    recovered_count += 1
            except (OSError, json.JSONDecodeError, WebJobError, ValueError) as exc:
                summary = f"{job_id}: {type(exc).__name__}"
                self.recovery_errors.append(summary)
                LOGGER.warning(
                    "Skipped unreadable job metadata during recovery: %s",
                    summary,
                )
        return recovered_count

    @staticmethod
    def _valid_owner_pid(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            pid = int(value)
        except (TypeError, ValueError):
            return None
        return pid if pid > 0 else None

    @staticmethod
    def _owner_process_alive(pid: int) -> bool:
        return process_is_alive(pid)

    @staticmethod
    def _legacy_job_is_stale(job: dict[str, Any]) -> bool:
        created_text = str(job.get("created_at", ""))
        if not created_text:
            return False
        created = datetime.fromisoformat(created_text)
        if created.tzinfo is None:
            created = created.astimezone()
        age_seconds = (datetime.now().astimezone() - created).total_seconds()
        return age_seconds >= LEGACY_STALE_SECONDS

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.public_job(self._read_job(job_id))

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        if not self.jobs_root.exists():
            return jobs
        for metadata_path in self.jobs_root.glob("*/job.json"):
            try:
                jobs.append(self.public_job(self._read_json(metadata_path)))
            except (OSError, json.JSONDecodeError, WebJobError):
                continue
        return sorted(jobs, key=lambda row: row["created_at"], reverse=True)

    def get_preview(self, job_id: str, kind: str) -> Any:
        path = self.artifact_path(job_id, kind)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WebJobError("结果文件暂时无法预览。") from exc

    def get_ai_review(self, job_id: str) -> dict[str, Any]:
        """Return a local-only, whitelisted AI/Python comparison view."""

        return self._ai_review_view(self._read_job(job_id))

    def revise_ai_result(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Create one immutable local publication revision for a completed V2 job."""

        allowed = {
            "expected_current_revision",
            "source_record_id",
            "field_name",
            "action",
            "manual_value",
        }
        if not isinstance(payload, Mapping) or set(payload) - allowed:
            raise WebJobError("结果修订请求包含不允许的字段。")
        if "manual_value" in payload and not isinstance(payload["manual_value"], str):
            raise WebJobError("手工修订值必须是字符串。")
        try:
            action = RevisionAction(str(payload.get("action", "")))
        except ValueError as exc:
            raise WebJobError("结果修订操作无效。") from exc
        request = RevisionRequest(
            expected_current_revision=str(
                payload.get("expected_current_revision", "")
            ),
            source_record_id=str(payload.get("source_record_id", "")),
            field_name=str(payload.get("field_name", "")),
            action=action,
            manual_value=(
                payload.get("manual_value", "")
                if isinstance(payload.get("manual_value", ""), str)
                else ""
            ),
        )
        lock = self._lock_for(job_id)
        with lock:
            job = self._read_job(job_id)
            mode = self._mode_view(job)
            contract = self._ai_contract_view(job)
            if (
                str(job.get("status", "")) != "completed"
                or mode["parse_mode"] != ParseMode.AI_ENHANCED.value
                or mode["effective_parse_mode"] != ParseMode.AI_ENHANCED.value
                or contract["ai_contract_version"] != AI_CONTRACT_V2
            ):
                raise RevisionNotSupported("只有已完成的 AI Enhanced V2 任务支持结果修订。")
            job_root = self._job_root(job_id)
            input_path = job_root / "input" / str(job["file_name"])
            dependencies = self.ai_enhanced_dependencies.bind_for_job(
                input_path, job_root / "ai-revision-runtime"
            )
            if not dependencies.downstream_ready:
                raise WebJobError("结果修订所需的本地下游依赖未就绪。")
            result = apply_revision(
                job_root / "ai-bundle",
                input_path,
                request,
                dictionary_validator=dependencies.dictionary_validator,
                material_matcher=dependencies.material_matcher,
            )
            summary = revision_summary(job_root / "ai-bundle")
            job["result_revision"] = summary
            self._write_json_atomic(job_root / "job.json", job)
        return {
            "job": self.get_job(job_id),
            "review": self.get_ai_review(job_id),
            "revision": {
                **summary,
                "parent_revision": result.parent_revision,
                "reused": result.reused,
            },
        }

    def artifact_path(self, job_id: str, kind: str) -> Path:
        role = ROLE_ALIASES.get(kind)
        if role is None:
            raise WebJobError("未知的结果文件类型。")
        job = self._read_job(job_id)
        if self._mode_view(job)["effective_parse_mode"] == ParseMode.AI_ENHANCED.value:
            return self._ai_bundle_artifact_path(job_id, job, role)
        legacy_key = STANDARD_ROLE_ARTIFACTS[role]
        relative = str(job.get("artifacts", {}).get(legacy_key, ""))
        if not relative:
            raise WebJobError("结果文件尚未生成。")
        return self._resolve_job_file(job_id, relative)

    def bundle_path(self, job_id: str) -> Path:
        job = self._read_job(job_id)
        relative = str(job.get("artifacts", {}).get("zip", ""))
        if not relative:
            raise WebJobError("打包文件尚未生成。")
        return self._resolve_job_file(job_id, relative)

    def list_matches(self, job_id: str) -> list[dict[str, Any]]:
        records = self._match_records(job_id)
        return [
            {
                "index": index,
                "line_number": str(record.get("行号", "")),
                "material_name": str(
                    record.get("query", {}).get("product_category", "")
                ),
                "spec": str(record.get("query", {}).get("spec", "")),
                "status": self._business_status(record),
                "summary_key": self._business_status_key(record),
                "candidate_count": len(record.get("candidates", [])),
            }
            for index, record in enumerate(records)
        ]

    def match_detail(self, job_id: str, index: int) -> dict[str, Any]:
        records = self._match_records(job_id)
        if index < 0 or index >= len(records):
            raise WebJobError("未找到对应的订单行。")
        record = records[index]
        candidates = record.get("candidates", [])
        top = candidates[0] if candidates else None
        fields = top.get("fields", {}) if top else {}
        comparisons = []
        for field_key, label in DETAIL_FIELDS:
            comparison = fields.get(field_key, {})
            comparisons.append(
                {
                    "field": label,
                    "order_value": str(
                        comparison.get(
                            "query_value",
                            record.get("query", {}).get(field_key, ""),
                        )
                    ),
                    "candidate_value": str(comparison.get("candidate_value", "")),
                    "status": self._comparison_status(
                        str(comparison.get("status", "not_comparable"))
                    ),
                }
            )
        top_five = [
            {
                "rank": candidate.get("rank", position),
                "material_code": str(candidate.get("material_code", "")),
                "score": round(
                    float(candidate.get("prototype_match_score", 0.0)) * 100, 1
                ),
                "reference_score": round(
                    float(candidate.get("prototype_match_score", 0.0)), 6
                ),
            }
            for position, candidate in enumerate(candidates[:5], start=1)
        ]
        job = self._read_job(job_id)
        advisory = (
            self.ai_advisory.status(job_id, index)
            if self._mode_view(job)["effective_parse_mode"] == ParseMode.STANDARD.value
            else {"state": "not_requested", "eligible": False}
        )
        return {
            "job_id": job_id,
            "file_name": job["file_name"],
            "index": index,
            "line_number": str(record.get("行号", "")),
            "material_name": str(
                record.get("query", {}).get("product_category", "")
            ),
            "spec": str(record.get("query", {}).get("spec", "")),
            "recommended_code": (
                str(top.get("material_code", "")) if top is not None else ""
            ),
            "score": (
                round(float(top.get("prototype_match_score", 0.0)) * 100, 1)
                if top is not None
                else 0.0
            ),
            "reference_score": (
                round(float(top.get("prototype_match_score", 0.0)), 6)
                if top is not None
                else 0.0
            ),
            "status": self._business_status(record),
            "comparisons": comparisons,
            "candidates": top_five,
            "ai_advisory": advisory,
        }

    def ai_advisory_status(
        self, job_id: str, index: int
    ) -> dict[str, Any]:
        return self.ai_advisory.status(job_id, index)

    def start_ai_advisory(
        self,
        job_id: str,
        index: int,
        submitted_identity: dict[str, Any],
    ) -> dict[str, Any]:
        return self.ai_advisory.start(
            job_id,
            index,
            submitted_identity,
        )

    def public_job(self, job: dict[str, Any]) -> dict[str, Any]:
        artifacts = job.get("artifacts", {})
        mode = self._mode_view(job)
        ai_execution = self._safe_ai_execution(job.get("ai_execution", {}))
        review = self._ai_review_view(job, mode=mode, ai_execution=ai_execution)
        result_revision = self._revision_view(job)
        return {
            "id": str(job["id"]),
            "file_name": str(job["file_name"]),
            "file_size": int(job.get("file_size", 0)),
            "created_at": str(job.get("created_at", "")),
            "completed_at": str(job.get("completed_at", "")),
            "elapsed_seconds": float(job.get("elapsed_seconds", 0.0)),
            "status": str(job.get("status", "queued")),
            "progress": int(job.get("progress", 0)),
            "current_stage": str(job.get("current_stage", "")),
            "stages": list(job.get("stages", [])),
            "error": str(job.get("error", "")),
            "worker_diagnostics": dict(
                job.get("worker_diagnostics", {})
            ),
            "sheet": str(job.get("sheet", "")),
            "record_count": int(job.get("record_count", 0)),
            "summary": dict(job.get("summary", {})),
            "artifacts": {
                name: bool(artifacts.get(name))
                for name in ("business", "diagnostic", "validation", "zip")
            },
            "artifact_roles": {
                role: self._has_artifact_role(str(job["id"]), job, role)
                for role in ARTIFACT_ROLES
            },
            "has_complete_five_results": all(
                self._has_artifact_role(str(job["id"]), job, role)
                for role in ARTIFACT_ROLES
            ),
            **mode,
            "ai_execution": ai_execution,
            "ai_review_summary": ai_review_summary(review),
            "result_revision": result_revision,
            "source_identity": self._safe_source_identity(job.get("source_identity")),
            "client_idempotency_identity": str(
                job.get("client_idempotency_identity", "")
            )[:160],
            "business_identity": str(job.get("business_identity", ""))[:160],
            "runtime_cache_identity": self._safe_runtime_cache_identity(
                job.get("runtime_cache_identity")
            ),
            "ai_user_decision": self._safe_user_decision(
                job.get("ai_user_decision")
            ),
        }

    def _ai_review_view(
        self,
        job: dict[str, Any],
        *,
        mode: dict[str, Any] | None = None,
        ai_execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mode = mode or self._mode_view(job)
        execution = ai_execution or self._safe_ai_execution(
            job.get("ai_execution", {})
        )
        historical_count = int(execution.get("isolated_field_count", 0))
        if mode["parse_mode"] != ParseMode.AI_ENHANCED.value:
            return unavailable_ai_review(
                applicable=False,
                message="标准解析不使用整单 AI/Python 对照。",
            )
        if mode["effective_parse_mode"] != ParseMode.AI_ENHANCED.value:
            return unavailable_ai_review(
                applicable=True,
                message="该历史 AI 任务已回退为标准解析，不提供整单字段对照。",
                historical_attention_count=historical_count,
            )
        if mode["ai_contract_version"] != AI_CONTRACT_V2:
            return unavailable_ai_review(
                applicable=True,
                message="该历史任务使用 Legacy V1，无法还原 V2 字段对照。",
                historical_attention_count=historical_count,
            )
        if str(job.get("status", "")) != "completed":
            return unavailable_ai_review(
                applicable=True,
                message="任务完成并发布五类结果后才会生成字段对照。",
                historical_attention_count=historical_count,
            )
        try:
            path = self._ai_bundle_artifact_path(
                str(job["id"]), job, "parse_diagnostics"
            )
            diagnostic = self._read_json(path)
        except (KeyError, OSError, json.JSONDecodeError, WebJobError):
            return unavailable_ai_review(
                applicable=True,
                message="该历史任务没有可安全读取的字段对照，五类结果仍可单独查看。",
                historical_attention_count=historical_count,
            )
        return build_ai_review_view(diagnostic)

    def _revision_view(self, job: Mapping[str, Any]) -> dict[str, Any]:
        mode = self._mode_view(dict(job))
        if (
            str(job.get("status", "")) != "completed"
            or mode["parse_mode"] != ParseMode.AI_ENHANCED.value
            or mode["effective_parse_mode"] != ParseMode.AI_ENHANCED.value
        ):
            return {
                "supported": False,
                "initial_revision": "",
                "current_revision": "",
                "revision_number": 0,
                "revision_count": 0,
            }
        try:
            return revision_summary(self._job_root(str(job["id"])) / "ai-bundle")
        except RevisionError:
            return {
                "supported": False,
                "initial_revision": "",
                "current_revision": "",
                "revision_number": 0,
                "revision_count": 0,
            }

    @staticmethod
    def _initial_ai_execution() -> dict[str, Any]:
        return {
            "stage": "preprocessing",
            "completed_chunks": 0,
            "total_chunks": 0,
            "logical_call_count": 0,
            "http_attempt_count": 0,
            "token_summary": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "provider": "",
            "model": "",
            "request_id": "",
            "has_publishable_result": False,
            "safe_error_code": "",
            "contract_diagnostic": {},
            "contract_version": "",
            "layout_call_count": 0,
            "cache_hit": False,
            "isolated_field_count": 0,
            "resume_count": 0,
            "last_resume_at": "",
            "stage_history": [],
            "structure_resolution": {},
        }

    @staticmethod
    def _safe_ai_execution(value: Any) -> dict[str, Any]:
        initial = JobService._initial_ai_execution()
        if not isinstance(value, dict):
            return initial
        stage = str(value.get("stage", initial["stage"]))
        initial["stage"] = stage if stage in AI_JOB_STAGES else "awaiting_user_decision"
        for name in (
            "completed_chunks",
            "total_chunks",
            "logical_call_count",
            "http_attempt_count",
            "layout_call_count",
            "isolated_field_count",
            "resume_count",
        ):
            raw = value.get(name, initial[name])
            initial[name] = int(raw) if isinstance(raw, int) and raw >= 0 else initial[name]
        tokens = value.get("token_summary", {})
        if isinstance(tokens, dict):
            initial["token_summary"] = {
                name: int(tokens.get(name, 0)) if isinstance(tokens.get(name, 0), int) and tokens.get(name, 0) >= 0 else 0
                for name in ("input_tokens", "output_tokens", "total_tokens")
            }
        initial["provider"] = str(value.get("provider", ""))[:120]
        initial["model"] = str(value.get("model", ""))[:120]
        initial["request_id"] = str(value.get("request_id", ""))[:160]
        initial["has_publishable_result"] = value.get("has_publishable_result") is True
        initial["safe_error_code"] = str(value.get("safe_error_code", ""))[:80]
        initial["contract_diagnostic"] = safe_contract_diagnostic(value.get("contract_diagnostic"))
        initial["contract_version"] = str(value.get("contract_version", ""))[:40]
        initial["cache_hit"] = value.get("cache_hit") is True
        initial["last_resume_at"] = str(value.get("last_resume_at", ""))[:80]
        history = value.get("stage_history", [])
        if isinstance(history, list):
            initial["stage_history"] = [
                str(item)
                for item in history[-32:]
                if str(item) in AI_JOB_STAGES
            ]
        initial["structure_resolution"] = JobService._safe_structure_resolution(
            value.get("structure_resolution")
        )
        return initial

    @staticmethod
    def _safe_structure_resolution(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        version = str(value.get("layout_contract_version", ""))[:40]
        context_version = str(value.get("structure_context_version", ""))[:40]
        context_sha = str(value.get("context_sha256", ""))
        operation_identity = str(value.get("operation_identity_sha256", ""))
        prompt_version = str(value.get("prompt_version", ""))[:40]
        status = str(value.get("status", ""))
        validation = str(value.get("validation_status", ""))
        if (
            version != LAYOUT_CONTRACT_VERSION
            or context_version != STRUCTURE_CONTEXT_VERSION
            or re.fullmatch(r"[0-9a-f]{64}", context_sha) is None
            or re.fullmatch(r"[0-9a-f]{64}", operation_identity) is None
            or prompt_version != LAYOUT_PROMPT_VERSION
            or status not in {"resolved", "ambiguous"}
            or validation not in {"applied", "unresolved"}
        ):
            return {}
        decisions = value.get("decisions")
        if not isinstance(decisions, list) or len(decisions) > 128:
            return {}
        safe_decisions: list[dict[str, str]] = []
        for item in decisions:
            if not isinstance(item, dict):
                return {}
            safe = {
                "sheet_id": str(item.get("sheet_id", ""))[:80],
                "role": str(item.get("role", ""))[:32],
                "candidate_id": str(item.get("candidate_id", ""))[:160],
                "reason": str(item.get("reason", ""))[:80],
            }
            if (
                re.fullmatch(r"s[1-9][0-9]*", safe["sheet_id"]) is None
                or safe["role"] not in {"order", "auxiliary", "unresolved"}
                or safe["reason"] not in {
                    "selected_local_order_candidate",
                    "auxiliary_non_order_content",
                    "insufficient_structure",
                    "conflicting_candidates",
                    "no_applicable_candidate",
                }
            ):
                return {}
            if safe["role"] == "unresolved":
                if safe["candidate_id"] or safe["reason"] not in {
                    "insufficient_structure",
                    "conflicting_candidates",
                    "no_applicable_candidate",
                }:
                    return {}
            else:
                expected_reason = (
                    "selected_local_order_candidate"
                    if safe["role"] == "order"
                    else "auxiliary_non_order_content"
                )
                if safe["reason"] != expected_reason or re.fullmatch(
                    rf"layout-candidate:{re.escape(safe['sheet_id'])}:[0-9a-f]{{20}}",
                    safe["candidate_id"],
                ) is None:
                    return {}
            safe_decisions.append(safe)
        has_unresolved = any(item["role"] == "unresolved" for item in safe_decisions)
        sheet_ids = [item["sheet_id"] for item in safe_decisions]
        if len(sheet_ids) != len(set(sheet_ids)):
            return {}
        if (status == "ambiguous") != has_unresolved:
            return {}
        if validation != ("unresolved" if has_unresolved else "applied"):
            return {}
        return {
            "structure_context_version": context_version,
            "layout_contract_version": version,
            "context_sha256": context_sha,
            "operation_identity_sha256": operation_identity,
            "prompt_version": prompt_version,
            "status": status,
            "validation_status": validation,
            "decisions": safe_decisions,
        }

    @staticmethod
    def _mode_label(value: str, *, legacy: bool = False) -> str:
        if value == ParseMode.AI_ENHANCED.value:
            return "AI增强整单解析"
        return "标准解析（历史任务）" if legacy else "标准解析"

    def _mode_view(self, job: dict[str, Any]) -> dict[str, Any]:
        raw_mode = job.get("parse_mode")
        if raw_mode is None:
            return {
                "parse_mode": ParseMode.STANDARD.value,
                "effective_parse_mode": ParseMode.STANDARD.value,
                "parse_contract_version": "",
                "parse_mode_source": "legacy_default",
                "parse_mode_label": self._mode_label(ParseMode.STANDARD.value, legacy=True),
                "effective_parse_mode_label": self._mode_label(ParseMode.STANDARD.value, legacy=True),
                "fallback": {"status": "legacy_default", "reason": "", "user_confirmed_at": ""},
                "requested_parse_mode": ParseMode.STANDARD.value,
                "ai_contract_version": "",
                "ai_contract_source": "legacy_standard_default",
                "ai_contract_label": "不适用",
            }
        try:
            mode = parse_mode_from_value(str(raw_mode)).value
            effective = parse_mode_from_value(str(job.get("effective_parse_mode", mode))).value
        except FullOrderContractError as exc:
            raise WebJobError("任务解析模式合同无效。") from exc
        fallback = job.get("fallback", {})
        if not isinstance(fallback, dict):
            fallback = {}
        ai_contract = self._ai_contract_view(job, mode)
        return {
            "parse_mode": mode,
            "requested_parse_mode": str(job.get("requested_parse_mode", mode)),
            "effective_parse_mode": effective,
            "parse_contract_version": str(job.get("parse_contract_version", "")),
            "parse_mode_source": str(job.get("parse_mode_source", "explicit")),
            "parse_mode_label": self._mode_label(mode),
            "effective_parse_mode_label": self._mode_label(effective),
            "fallback": {
                "status": str(fallback.get("status", "not_requested")),
                "reason": str(fallback.get("reason", ""))[:180],
                "user_confirmed_at": str(fallback.get("user_confirmed_at", "")),
            },
            **ai_contract,
        }

    @staticmethod
    def _ai_contract_view(job: dict[str, Any], mode: str | None = None) -> dict[str, str]:
        resolved_mode = mode or str(job.get("parse_mode", ParseMode.STANDARD.value))
        if resolved_mode != ParseMode.AI_ENHANCED.value:
            return {
                "ai_contract_version": "",
                "ai_contract_source": str(
                    job.get("ai_contract_source", "not_applicable")
                ),
                "ai_contract_label": "不适用",
            }
        raw = job.get("ai_contract_version")
        if raw is None or str(raw).strip() == "":
            return {
                "ai_contract_version": AI_CONTRACT_V1,
                "ai_contract_source": "legacy_missing_version",
                "ai_contract_label": "Legacy V1",
            }
        version = str(raw)
        if version == AI_CONTRACT_V2:
            return {
                "ai_contract_version": version,
                "ai_contract_source": str(
                    job.get("ai_contract_source", "explicit_v2")
                ),
                "ai_contract_label": "Contract V2",
            }
        if version == AI_CONTRACT_V1:
            return {
                "ai_contract_version": version,
                "ai_contract_source": str(
                    job.get("ai_contract_source", "explicit_legacy_v1")
                ),
                "ai_contract_label": "Legacy V1",
            }
        raise WebJobError("任务 AI 内部合同版本无效。")

    @staticmethod
    def _safe_source_identity(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {"sha256": "", "size_bytes": 0}
        sha = str(value.get("sha256", ""))
        size = value.get("size_bytes", 0)
        return {
            "sha256": sha if len(sha) == 64 else "",
            "size_bytes": int(size) if isinstance(size, int) and size >= 0 else 0,
        }

    @staticmethod
    def _safe_runtime_cache_identity(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            value = {}
        return {
            "cache_key": str(value.get("cache_key", ""))[:64],
            "manifest_sha256": str(value.get("manifest_sha256", ""))[:64],
            "execution_id": str(value.get("execution_id", ""))[:80],
            "disposition": str(value.get("disposition", ""))[:40],
        }

    @staticmethod
    def _safe_user_decision(value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            value = {}
        return {
            "status": str(value.get("status", "not_required"))[:40],
            "action": str(value.get("action", ""))[:80],
            "decided_at": str(value.get("decided_at", ""))[:80],
        }

    def _has_artifact_role(self, job_id: str, job: dict[str, Any], role: str) -> bool:
        try:
            self.artifact_path(job_id, role)
        except WebJobError:
            return False
        return True

    def _ai_bundle_artifact_path(self, job_id: str, job: dict[str, Any], role: str) -> Path:
        roles = job.get("artifact_roles", {})
        descriptor = roles.get(role) if isinstance(roles, dict) else None
        if not isinstance(descriptor, dict) or descriptor.get("source") != "ai_current_bundle":
            raise WebJobError("AI结果文件尚未生成。")
        root = self._job_root(job_id) / "ai-bundle"
        try:
            bundle, current_identity, revision_aware = resolve_current_bundle(root)
        except RevisionError as exc:
            raise WebJobError("AI结果入口身份无效。") from exc
        if root.resolve() not in bundle.parents:
            raise WebJobError("AI结果入口路径无效。")
        paths = {name: bundle / name for name in AI_BUNDLE_ARTIFACTS.values()}
        if not all(path.is_file() for path in paths.values()):
            raise WebJobError("AI结果Bundle不完整。")
        try:
            diagnostic = self._read_json(paths[AI_BUNDLE_ARTIFACTS["parse_diagnostics"]])
            ai = diagnostic.get("ai_enhanced", {})
        except (OSError, json.JSONDecodeError, WebJobError) as exc:
            raise WebJobError("AI结果诊断文件无法校验。") from exc
        if not isinstance(ai, dict) or ai.get("parse_mode") != "ai_enhanced":
            raise WebJobError("AI结果Bundle身份不一致。")
        if revision_aware:
            revision = ai.get("publication_revision", {})
            if (
                not isinstance(revision, dict)
                or revision.get("revision_id") != current_identity
            ):
                raise WebJobError("AI结果Revision身份不一致。")
        elif ai.get("cache_key") != current_identity:
            raise WebJobError("AI结果Bundle身份不一致。")
        contract = self._ai_contract_view(job)
        if contract["ai_contract_version"] == AI_CONTRACT_V2:
            versions = ai.get("contract_versions", {})
            if not isinstance(versions, dict):
                versions = {}
            # Compatibility reader for bundles published before D4A-2.
            legacy_identity = ai.get("cache_identity", {})
            if not isinstance(legacy_identity, dict):
                legacy_identity = {}
            contract_version = versions.get(
                "contract_version", legacy_identity.get("contract_version")
            )
            if (
                ai.get("protocol") != "v2"
                or contract_version != AI_CONTRACT_V2
            ):
                raise WebJobError("AI结果Bundle内部合同身份不一致。")
        return paths[AI_BUNDLE_ARTIFACTS[role]]

    def _run_job(self, job_id: str) -> None:
        job = self._read_job(job_id)
        if self._mode_view(job)["effective_parse_mode"] == ParseMode.AI_ENHANCED.value:
            self._run_ai_enhanced_job(job_id)
            return
        self._run_standard_job(job_id)

    def retry_missing_chunks(self, job_id: str) -> dict[str, Any]:
        job = self._read_job(job_id)
        mode = self._mode_view(job)
        if mode["parse_mode"] != ParseMode.AI_ENHANCED.value or mode["effective_parse_mode"] != ParseMode.AI_ENHANCED.value:
            raise WebJobError("只有等待处理的AI增强任务可以重试分块。")
        if str(job.get("status", "")) != "awaiting_user_decision":
            raise WebJobError("当前任务不处于可重试状态。")
        execution = self._safe_ai_execution(job.get("ai_execution", {}))
        execution.update(
            {
                "resume_count": execution["resume_count"] + 1,
                "last_resume_at": self._now(),
            }
        )
        self._update_job(
            job_id,
            {
                "ai_execution": execution,
                "ai_user_decision": {
                    "status": "confirmed",
                    "action": "retry_missing_units",
                    "decided_at": self._now(),
                },
            },
        )
        self._run_ai_enhanced_job(job_id)
        return self.get_job(job_id)

    def keep_failed(self, job_id: str) -> dict[str, Any]:
        job = self._read_job(job_id)
        if str(job.get("status", "")) != "awaiting_user_decision":
            raise WebJobError("当前任务没有待保留的AI失败状态。")
        self._update_job(
            job_id,
            {
                "status": "failed",
                "completed_at": self._now(),
                "current_stage": "awaiting_user_decision",
                "ai_user_decision": {
                    "status": "confirmed",
                    "action": "keep_failed",
                    "decided_at": self._now(),
                },
            },
        )
        return self.get_job(job_id)

    def _run_ai_enhanced_job(self, job_id: str) -> None:
        started = time.perf_counter()
        job_root = self._job_root(job_id)

        def stage_update(stage: str, completed: int, total: int, calls: int) -> None:
            self._set_ai_progress(job_id, stage, completed, total, calls)

        def structure_update(summary: Mapping[str, Any]) -> None:
            stored = self._read_job(job_id)
            execution = self._safe_ai_execution(stored.get("ai_execution", {}))
            execution["structure_resolution"] = self._safe_structure_resolution(summary)
            self._update_job(job_id, {"ai_execution": execution})

        try:
            job = self._read_job(job_id)
            input_path = job_root / "input" / str(job["file_name"])
            contract = self._ai_contract_view(job)
            if contract["ai_contract_version"] == AI_CONTRACT_V2:
                result = run_ai_enhanced_v2_job(
                    input_path,
                    runtime_root=job_root / "ai-runtime",
                    publish_root=job_root / "ai-bundle",
                    dependencies=self.ai_enhanced_dependencies,
                    client_idempotency_key=str(job["client_idempotency_identity"]),
                    business_key=str(job["business_identity"]),
                    on_stage=stage_update,
                    retry_corrupt_cache=(
                        self._safe_ai_execution(job.get("ai_execution", {}))[
                            "safe_error_code"
                        ]
                        == "AI_V2_CACHE_CORRUPT"
                    ),
                    persisted_structure_summary=self._safe_ai_execution(
                        job.get("ai_execution", {})
                    )["structure_resolution"],
                    on_structure_summary=structure_update,
                )
            else:
                result = run_ai_enhanced_job(
                    input_path,
                    job_id=job_id,
                    runtime_root=job_root / "ai-runtime",
                    publish_root=job_root / "ai-bundle",
                    dependencies=self.ai_enhanced_dependencies,
                    on_stage=stage_update,
                )
            self._complete_ai_job(job_id, result, started)
        except AIEnhancedJobPause as exc:
            execution = exc.execution
            outcomes = execution.outcomes if execution is not None else ()
            completed = sum(item.status.value == "validated" for item in outcomes)
            items = (
                getattr(execution, "extraction_units", ())
                or getattr(execution, "manifest", ())
            ) if execution is not None else ()
            total = len(items)
            contract = self._ai_contract_view(self._read_job(job_id))
            calls = exc.provider_calls + exc.layout_calls
            http_attempts = exc.http_attempts
            self._pause_ai_job(
                job_id,
                exc.code,
                completed,
                total,
                calls,
                http_attempts,
                started,
                execution=execution,
                layout_calls=exc.layout_calls,
                contract_version=contract["ai_contract_version"],
                usage=exc.usage,
                structure_summary=exc.structure_summary,
            )
        except JobInterrupted:
            return
        except Exception:
            contract_version = self._ai_contract_view(
                self._read_job(job_id)
            )["ai_contract_version"]
            self._pause_ai_job(
                job_id,
                "AI_INTERNAL_FAILURE",
                0,
                0,
                0,
                0,
                started,
                contract_version=contract_version,
            )

    def _set_ai_progress(self, job_id: str, stage: str, completed: int, total: int, calls: int) -> None:
        if stage not in AI_JOB_STAGES:
            raise WebJobError("AI执行阶段无效。")
        stored = self._read_job(job_id)
        current = self._safe_ai_execution(stored.get("ai_execution", {}))
        base_progress, active_stage, stage_label = AI_STAGE_PRESENTATION[stage]
        calculated = base_progress
        if stage == "ai_extraction" and total:
            calculated = min(57, calculated + int(22 * completed / total))
        progress = max(int(stored.get("progress", 0)), calculated)
        history = list(current.get("stage_history", []))
        if not history or history[-1] != stage:
            history.append(stage)
        current.update(
            {
                "stage": stage,
                "completed_chunks": completed,
                "total_chunks": total,
                "logical_call_count": calls,
                "http_attempt_count": 0,
                "has_publishable_result": False,
                "safe_error_code": "",
                "contract_diagnostic": {},
                "stage_history": history[-32:],
            }
        )
        self._update_job(
            job_id,
            {
                "status": "processing",
                "progress": progress,
                "current_stage": stage_label,
                "stages": self._ai_stage_rows(active_stage, stage == "completed"),
                "ai_execution": current,
            },
        )

    @staticmethod
    def _ai_stage_rows(active_stage: int, completed: bool = False) -> list[dict[str, str]]:
        return [
            {
                "name": name,
                "status": (
                    "completed"
                    if completed or index < active_stage
                    else "processing"
                    if index == active_stage
                    else "waiting"
                ),
            }
            for index, name in enumerate(STAGE_NAMES)
        ]

    def _pause_ai_job(
        self,
        job_id: str,
        code: str,
        completed: int,
        total: int,
        calls: int,
        http_attempts: int,
        started: float,
        *,
        execution: Any | None = None,
        layout_calls: int = 0,
        contract_version: str = "",
        usage: Mapping[str, int] | None = None,
        structure_summary: Mapping[str, Any] | None = None,
    ) -> None:
        current = self._safe_ai_execution(self._read_job(job_id).get("ai_execution", {}))
        provider = getattr(self.ai_enhanced_dependencies, "provider", None)
        telemetry = getattr(provider, "latest_telemetry", None)
        usage_values = dict(usage or {})
        current.update(
            {
                "stage": "awaiting_user_decision",
                "completed_chunks": completed,
                "total_chunks": total,
                "logical_call_count": calls,
                "http_attempt_count": http_attempts,
                "token_summary": {
                    name: int(usage_values.get(name, 0))
                    for name in ("input_tokens", "output_tokens", "total_tokens")
                },
                "provider": str(
                    getattr(self.ai_enhanced_dependencies, "provider_name", "")
                ),
                "model": str(
                    getattr(self.ai_enhanced_dependencies, "model_name", "")
                ),
                "request_id": str(getattr(telemetry, "request_id", "")),
                "has_publishable_result": False,
                "safe_error_code": code,
                "contract_diagnostic": safe_contract_diagnostic(
                    getattr(provider, "latest_contract_diagnostic", {})
                ),
                "contract_version": contract_version,
                "layout_call_count": layout_calls,
                "cache_hit": False,
                "structure_resolution": (
                    self._safe_structure_resolution(structure_summary)
                    or current.get("structure_resolution", {})
                ),
                "stage_history": [
                    *[
                        item
                        for item in current.get("stage_history", [])
                        if item != "awaiting_user_decision"
                    ],
                    "awaiting_user_decision",
                ][-32:],
            }
        )
        runtime_identity = self._runtime_identity_from_execution(execution)
        self._update_job(
            job_id,
            {
                "status": "awaiting_user_decision",
                "current_stage": "awaiting_user_decision",
                "error": "AI增强整单解析未发布，请选择重试、回退或保留失败。",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "ai_execution": current,
                "artifacts": {},
                "artifact_roles": {},
                "runtime_cache_identity": runtime_identity,
                "ai_user_decision": {
                    "status": "pending",
                    "action": "",
                    "decided_at": "",
                },
            },
        )

    def _complete_ai_job(self, job_id: str, result: AIEnhancedJobResult, started: float) -> None:
        expected_paths = set(AI_BUNDLE_ARTIFACTS.values())
        if set(result.bundle.paths) != expected_paths or not all(
            path.is_file() for path in result.bundle.paths.values()
        ):
            raise WebJobError("AI结果Bundle未通过五类角色完整性校验。")
        calls = result.execution.provider_calls + result.layout_call_count
        execution = self._safe_ai_execution(self._read_job(job_id).get("ai_execution", {}))
        history = list(execution.get("stage_history", []))
        if not history or history[-1] != "completed":
            history.append("completed")
        execution.update(
            {
                "stage": "completed",
                "completed_chunks": result.total_chunks,
                "total_chunks": result.total_chunks,
                "logical_call_count": calls,
                "http_attempt_count": result.http_attempt_count,
                "token_summary": dict(result.usage or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}),
                "model": result.model_name,
                "provider": result.provider_name,
                "request_id": result.request_id,
                "has_publishable_result": True,
                "safe_error_code": "",
                "contract_version": result.contract_version,
                "layout_call_count": result.layout_call_count,
                "cache_hit": result.execution.disposition.value == "cached",
                "isolated_field_count": result.isolated_field_count,
                "structure_resolution": self._safe_structure_resolution(
                    result.structure_summary
                ),
                "stage_history": history[-32:],
            }
        )
        runtime_identity = self._runtime_identity_from_execution(result.execution)
        result_revision = {
            "supported": False,
            "initial_revision": "",
            "current_revision": "",
            "revision_number": 0,
            "revision_count": 0,
        }
        if result.contract_version == AI_CONTRACT_V2:
            initialize_revision_history(
                self._job_root(job_id) / "ai-bundle", result.bundle
            )
            result_revision = revision_summary(
                self._job_root(job_id) / "ai-bundle"
            )
        self._update_job(
            job_id,
            {
                "completed_at": self._now(),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "status": "completed",
                "progress": 100,
                "current_stage": AI_STAGE_PRESENTATION["completed"][2],
                "stages": self._ai_stage_rows(4, completed=True),
                "record_count": len(result.execution.batch.records),
                "summary": {"high_match": 0, "partial_match": 0, "conflict": 0},
                "ai_execution": execution,
                "artifacts": {},
                "artifact_roles": {
                    role: {"source": "ai_current_bundle"}
                    for role in ARTIFACT_ROLES
                },
                "runtime_cache_identity": runtime_identity,
                "result_revision": result_revision,
            },
        )

    @staticmethod
    def _runtime_identity_from_execution(execution: Any | None) -> dict[str, str]:
        if execution is None:
            return {
                "cache_key": "",
                "manifest_sha256": "",
                "execution_id": "",
                "disposition": "",
            }
        identity = getattr(execution, "cache_identity", None)
        return {
            "cache_key": str(getattr(execution, "cache_key", ""))[:64],
            "manifest_sha256": str(
                getattr(identity, "canonical_extraction_manifest_sha256", "")
            )[:64],
            "execution_id": str(getattr(execution, "execution_id", ""))[:80],
            "disposition": str(
                getattr(getattr(execution, "disposition", None), "value", "")
            )[:40],
        }

    def _run_standard_job(self, job_id: str) -> None:
        from bedding_order_parser.materials.hybrid_matcher import match_orders
        from bedding_order_parser.materials.match_writer import (
            write_match_outputs,
        )
        from bedding_order_parser.pipeline.order_parser import parse_order

        started = time.perf_counter()
        job_root = self._job_root(job_id)
        embedding_diagnostics_path = (
            job_root / "runtime" / "embedding_diagnostics.json"
        )
        try:
            self._set_progress(
                job_id, 8, "正在读取订单文件...", active_stage=0
            )
            job = self._read_job(job_id)
            input_path = job_root / "input" / job["file_name"]
            stem = Path(job["file_name"]).stem
            result_dir = job_root / "results"
            result_path = result_dir / f"{stem}_gate2d.json"
            report_path = result_dir / f"{stem}_gate2d_parse_report.json"
            validation_path = (
                result_dir / f"{stem}_gate2d_dictionary_validation.json"
            )

            self._set_progress(
                job_id, 24, "正在提取订单字段...", active_stage=1
            )
            parse_summary = parse_order(
                input_path,
                result_path,
                report_path=report_path,
                dictionary_validate=True,
                validation_path=validation_path,
                dictionary_rules_path=self.dictionary_rules_path,
                dictionary_styles_path=self.dictionary_styles_path,
            )
            self._ensure_job_active(job_id)
            self._set_progress(
                job_id,
                62,
                "订单字段与字典校验已完成",
                completed_through=2,
            )
            self._set_progress(
                job_id,
                70,
                "正在进行物料匹配和相似度计算...",
                completed_through=2,
                active_stage=3,
            )
            match_result = match_orders(
                result_dir,
                result_dir,
                self.store_path,
                self.index_dir,
                top_k=10,
                vector_recall_k=300,
                cancel_check=lambda: self._ensure_job_active(job_id),
                embedding_runtime_dir=job_root / "runtime" / "embedding",
                embedding_diagnostics_path=embedding_diagnostics_path,
            )
            self._ensure_job_active(job_id)
            match_paths = write_match_outputs(
                match_result, job_root / "match-output"
            )
            self._set_progress(
                job_id,
                92,
                "正在整理结果文件...",
                completed_through=3,
                active_stage=4,
            )
            self._ensure_job_active(job_id)
            records = match_result.candidates_payload["records"]
            counts = {"high_match": 0, "partial_match": 0, "conflict": 0}
            for record in records:
                counts[self._business_status_key(record)] += 1
            bundle_path = job_root / f"{stem}_全部结果.zip"
            self._write_bundle(
                bundle_path,
                {
                    f"{stem}_正式业务.json": result_path,
                    f"{stem}_解析诊断.json": report_path,
                    f"{stem}_字典验证.json": validation_path,
                    f"{stem}_匹配候选.json": match_paths.candidates_path,
                    f"{stem}_匹配摘要.json": match_paths.summary_path,
                },
            )

            self._update_job(
                job_id,
                {
                    "completed_at": self._now(),
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "status": "completed",
                    "progress": 100,
                    "current_stage": "解析完成",
                    "stages": [
                        {"name": name, "status": "completed"}
                        for name in STAGE_NAMES
                    ],
                    "record_count": parse_summary.record_count,
                    "summary": counts,
                    "worker_diagnostics": self._worker_diagnostics(
                        None, embedding_diagnostics_path
                    ),
                    "input_sha256": parse_summary.input_sha256_before,
                    "artifacts": {
                        "business": self._relative(job_id, result_path),
                        "diagnostic": self._relative(job_id, report_path),
                        "validation": self._relative(job_id, validation_path),
                        "zip": self._relative(job_id, bundle_path),
                        "matches": self._relative(job_id, match_paths.candidates_path),
                        "match_summary": self._relative(
                            job_id, match_paths.summary_path
                        ),
                    },
                },
            )
        except JobInterrupted:
            return
        except Exception as exc:
            updates = {
                "status": "failed",
                "current_stage": "解析失败",
                "completed_at": self._now(),
                "error": self._friendly_error(exc),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
            diagnostics = self._worker_diagnostics(
                exc, embedding_diagnostics_path
            )
            if diagnostics:
                updates["worker_diagnostics"] = diagnostics
            self._update_job(
                job_id,
                updates,
            )

    def _ensure_job_active(self, job_id: str) -> None:
        if self._read_job(job_id).get("status") in TERMINAL_JOB_STATUSES:
            raise JobInterrupted("任务已中断。")

    def _set_progress(
        self,
        job_id: str,
        progress: int,
        current_stage: str,
        *,
        completed_through: int = -1,
        active_stage: int | None = None,
    ) -> None:
        stages = []
        for index, name in enumerate(STAGE_NAMES):
            if index <= completed_through:
                status = "completed"
            elif active_stage == index:
                status = "processing"
            else:
                status = "waiting"
            stages.append({"name": name, "status": status})
        self._update_job(
            job_id,
            {
                "status": "processing",
                "progress": progress,
                "current_stage": current_stage,
                "stages": stages,
            }
        )

    def _match_records(self, job_id: str) -> list[dict[str, Any]]:
        payload = self._read_json(self.artifact_path(job_id, "material_candidates"))
        records = payload.get("records")
        if not isinstance(records, list):
            raise WebJobError("匹配结果格式不正确。")
        return records

    @staticmethod
    def _business_status_key(record: dict[str, Any]) -> str:
        status = str(record.get("decision", {}).get("status", ""))
        if status == "unique_best_candidate":
            return "high_match"
        if status in {"insufficient_evidence", "ranked_candidates"}:
            return "partial_match"
        return "conflict"

    @staticmethod
    def _business_status(record: dict[str, Any]) -> dict[str, str]:
        decision = str(record.get("decision", {}).get("status", ""))
        statuses = {
            "unique_best_candidate": ("recommendation", "推荐明确"),
            "ranked_candidates": ("candidate", "存在候选"),
            "ambiguous_tie": ("tie", "候选并列"),
            "insufficient_evidence": ("insufficient", "证据不足"),
            "no_candidate": ("no_candidate", "无候选"),
        }
        key, label = statuses.get(decision, ("insufficient", "建议人工查看"))
        return {"key": key, "label": label}

    @staticmethod
    def _comparison_status(status: str) -> dict[str, str]:
        if status in {"exact_match", "equivalent_match"}:
            return {"key": "match", "label": "一致"}
        if status in {
            "partial_match",
            "missing_query",
            "missing_candidate",
            "not_comparable",
        }:
            return {"key": "partial", "label": "部分匹配"}
        return {"key": "conflict", "label": "冲突"}

    def _read_job(self, job_id: str) -> dict[str, Any]:
        self._require_job_id(job_id)
        path = self._job_root(job_id) / "job.json"
        if not path.is_file():
            raise WebJobError("未找到该解析任务。")
        return self._read_json(path)

    def _write_job(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job["id"])
        lock = self._lock_for(job_id)
        with lock:
            path = self._job_root(job_id) / "job.json"
            if path.is_file():
                current = self._read_json(path)
                if str(current.get("status", "")) in TERMINAL_JOB_STATUSES:
                    return current
            self._write_json_atomic(path, job)
            return job

    def _update_job(
        self, job_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        lock = self._lock_for(job_id)
        with lock:
            path = self._job_root(job_id) / "job.json"
            job = self._read_json(path)
            if str(job.get("status", "")) in TERMINAL_JOB_STATUSES:
                return job
            if "parse_mode" in updates and updates["parse_mode"] != job.get("parse_mode"):
                raise WebJobError("任务原始解析模式创建后不可修改。")
            job.update(updates)
            self._write_json_atomic(path, job)
            return job

    def _trusted_original_upload(
        self, job_id: str, job: Mapping[str, Any]
    ) -> tuple[str, bytes, str]:
        file_name = Path(str(job.get("file_name", ""))).name.strip()
        if not file_name or file_name != str(job.get("file_name", "")):
            raise WebJobError("原始上传文件身份无效，不能重新处理。")
        input_dir = self._job_root(job_id) / "input"
        input_path = (input_dir / file_name).resolve()
        if input_path.parent != input_dir.resolve() or not input_path.is_file():
            raise WebJobError("原始上传文件不存在，不能重新处理。")
        content = input_path.read_bytes()
        source_identity = job.get("source_identity")
        if not isinstance(source_identity, Mapping):
            raise WebJobError("原始上传文件身份无效，不能重新处理。")
        expected_sha256 = str(source_identity.get("sha256", ""))
        expected_size = source_identity.get("size_bytes")
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if (
            len(expected_sha256) != 64
            or actual_sha256 != expected_sha256
            or expected_size != len(content)
        ):
            raise WebJobError("原始上传文件身份不一致，不能重新处理。")
        return file_name, content, actual_sha256

    def _find_reprocess_operation(
        self, origin_job_id: str, operation_id: str
    ) -> dict[str, Any] | None:
        for job_path in self.jobs_root.glob("*/job.json"):
            try:
                candidate = self._read_json(job_path)
            except (OSError, json.JSONDecodeError):
                continue
            reprocess = candidate.get("reprocess")
            if not isinstance(reprocess, Mapping):
                continue
            if (
                str(reprocess.get("origin_job_id", "")) == origin_job_id
                and str(reprocess.get("operation_id", "")) == operation_id
            ):
                return candidate
        return None

    def _find_active_standard_reprocess(
        self, origin_job_id: str
    ) -> dict[str, Any] | None:
        for job_path in self.jobs_root.glob("*/job.json"):
            try:
                candidate = self._read_json(job_path)
            except (OSError, json.JSONDecodeError):
                continue
            reprocess = candidate.get("reprocess")
            if not isinstance(reprocess, Mapping):
                continue
            if (
                str(reprocess.get("origin_job_id", "")) == origin_job_id
                and str(candidate.get("parse_mode", "")) == ParseMode.STANDARD.value
                and str(candidate.get("status", "")) in ACTIVE_JOB_STATUSES
            ):
                return candidate
        return None

    @staticmethod
    def _validate_reprocess_operation_id(operation_id: str) -> str:
        value = str(operation_id).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,127}", value):
            raise WebJobError("标准解析重新处理操作身份无效。")
        return value

    def _resolve_job_file(self, job_id: str, relative: str) -> Path:
        root = self._job_root(job_id)
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise WebJobError("结果文件不存在。")
        return path

    def _relative(self, job_id: str, path: Path) -> str:
        return path.resolve().relative_to(self._job_root(job_id)).as_posix()

    def _job_root(self, job_id: str) -> Path:
        return (self.jobs_root / job_id).resolve()

    @staticmethod
    def _require_job_id(job_id: str) -> None:
        if len(job_id) != 32 or any(
            character not in "0123456789abcdef" for character in job_id
        ):
            raise WebJobError("解析任务编号无效。")

    def _lock_for(self, job_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(job_id, threading.Lock())

    @staticmethod
    def _write_bundle(path: Path, files: dict[str, Path]) -> None:
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(
                temp_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for archive_name, source in files.items():
                    archive.write(source, arcname=archive_name)
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _write_bytes_atomic(path: Path, content: bytes) -> None:
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_bytes(content)
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        write_json_atomic(path, payload)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise WebJobError("本地任务数据格式不正确。")
        return payload

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _worker_diagnostics(
        exc: Exception | None, path: Path
    ) -> dict[str, Any]:
        direct = getattr(exc, "diagnostics", None)
        if isinstance(direct, dict) and direct:
            return direct
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        text = str(exc).strip()
        if not text:
            return "解析未完成，请检查文件后重试。"
        if len(text) > 180:
            text = text[:177] + "..."
        return text
