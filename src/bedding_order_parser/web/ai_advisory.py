"""Single-record AI advisory orchestration for completed local jobs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from bedding_order_parser.llm.advisory_schema import validate_final_advisory
from bedding_order_parser.llm.contracts import LLMEnhancementRequest
from bedding_order_parser.llm.errors import LLMProviderError
from bedding_order_parser.llm.service import LLMService
from bedding_order_parser.web.job_persistence import write_json_atomic


PRODUCT_FIELDS = (
    "物料名称",
    "规格",
    "颜色",
    "面料",
    "面料-涤棉成分",
    "款式",
    "加标方式",
    "尺寸类型",
    "行备注",
    "包装方式",
    "是否绣花",
)
VALIDATION_FIELDS = ("物料名称", "规格", "颜色")
STATUS_VERSION = "1.0"
ADVISORY_STATES = frozenset(
    {"not_requested", "running", "completed", "failed", "cached"}
)
SENSITIVE_LABEL_PATTERN = re.compile(
    r"(?:\b(?:address|ship\s*to|contact|phone|tel(?:ephone)?|e-?mail)\b|"
    r"地址|联系人|电话|邮箱)",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"
)
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)"
)
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class AIAdvisoryError(RuntimeError):
    """Base error for safe, user-initiated advisory operations."""


class AIAdvisoryConflict(AIAdvisoryError):
    """Another record is already queued or running."""


class AIAdvisoryUnavailable(AIAdvisoryError):
    """The job, record, or provider cannot currently run an advisory."""


class AIAdvisoryManager:
    """Persist one-record advisory state without changing main job results."""

    def __init__(
        self,
        jobs_root: Path,
        llm_service: LLMService,
        executor: Any,
    ) -> None:
        self.jobs_root = jobs_root
        self.llm_service = llm_service
        self.executor = executor
        self._guard = threading.Lock()
        self._active: tuple[str, int] | None = None
        self._completed_this_session: set[tuple[str, int]] = set()
        self._accepting = True

    def stop_accepting(self) -> None:
        self._accepting = False

    def active(self) -> list[dict[str, Any]]:
        with self._guard:
            active = self._active
        if active is None:
            return []
        job_id, index = active
        try:
            return [self.status(job_id, index)]
        except AIAdvisoryError:
            return [{"job_id": job_id, "record_index": index, "state": "running"}]

    def status(self, job_id: str, index: int) -> dict[str, Any]:
        context = self._context(job_id, index)
        identity = context["identity"]
        key = (job_id, index)
        status_path = self._status_path(
            job_id, identity["source_record_id"]
        )
        stored: dict[str, Any] = {}
        if status_path.is_file():
            try:
                stored = self._read_object(status_path)
            except (OSError, ValueError, AIAdvisoryError):
                return self._failed_public(
                    context,
                    "STATUS_INVALID",
                    "AI复核状态文件无法读取。",
                )
            stored_state = str(stored.get("state", "failed"))
            if stored_state not in ADVISORY_STATES:
                return self._failed_public(
                    context,
                    "STATUS_INVALID",
                    "AI复核状态文件包含未知状态。",
                )
            if stored_state == "running":
                with self._guard:
                    active = self._active
                if active == key:
                    return self._public(context, state="running")
                stored = {
                    **stored,
                    "state": "failed",
                    "error": {
                        "code": "INTERRUPTED",
                        "message": "上次AI复核调用未完成，请手动重试。",
                    },
                }
                self._write_status(
                    context,
                    state="failed",
                    operation=str(
                        stored.get("operation", "generate_chinese")
                    ),
                    error=stored["error"],
                )

        sidecar_path = self._sidecar_path(job_id, identity["source_record_id"])
        if sidecar_path.is_file():
            try:
                result = self._read_object(sidecar_path)
                validate_final_advisory(result)
                if result["source_record_id"] != identity["source_record_id"]:
                    raise ValueError("source_record_id mismatch")
            except (OSError, ValueError, AIAdvisoryError) as exc:
                return self._failed_public(
                    context,
                    "SIDECAR_INVALID",
                    f"AI复核文件校验失败：{type(exc).__name__}",
                )
            state = (
                "completed"
                if key in self._completed_this_session
                else "cached"
            )
            error = None
            if (
                stored.get("state") == "failed"
                and stored.get("operation") == "regenerate_chinese"
            ):
                raw_error = stored.get("error")
                error = raw_error if isinstance(raw_error, dict) else None
            return self._public(
                context,
                state=state,
                result=result,
                error=error,
            )

        if not stored:
            return self._public(context, state="not_requested")
        state = str(stored.get("state", "failed"))
        if state == "failed":
            error = stored.get("error")
            safe_error = error if isinstance(error, dict) else {}
            public_error: dict[str, Any] = {
                "code": str(
                    safe_error.get("code", "AI_ADVISORY_FAILED")
                ),
                "message": str(
                    safe_error.get(
                        "message",
                        "AI复核建议生成失败，请手动重试。",
                    )
                ),
            }
            if "attempt_count" in safe_error:
                public_error["attempt_count"] = int(
                    safe_error.get("attempt_count", 0)
                )
            if safe_error.get("request_id"):
                public_error["request_id"] = str(
                    safe_error["request_id"]
                )
            diagnostics = self._safe_diagnostics(safe_error)
            if diagnostics:
                public_error.update(diagnostics)
            return self._public(
                context,
                state="failed",
                error=public_error,
            )
        return self._public(context, state=state)

    def start(
        self,
        job_id: str,
        index: int,
        submitted_identity: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._accepting:
            raise AIAdvisoryUnavailable("应用正在关闭，不能启动AI建议。")
        context = self._context(job_id, index)
        self._validate_start(context, submitted_identity)
        identity = context["identity"]
        regenerate_chinese = (
            submitted_identity.get("regenerate_chinese") is True
        )
        sidecar_path = self._sidecar_path(
            job_id, identity["source_record_id"]
        )
        operation = "generate_chinese"
        if sidecar_path.is_file():
            existing = self._read_object(sidecar_path)
            validate_final_advisory(existing)
            if (
                existing["source_record_id"]
                != identity["source_record_id"]
            ):
                raise AIAdvisoryUnavailable(
                    "历史AI复核文件与当前订单记录不一致。"
                )
            historical_english = not self._is_simplified_chinese_advisory(
                existing
            )
            if not historical_english or not regenerate_chinese:
                return self.status(job_id, index)
            operation = "regenerate_chinese"

        key = (job_id, index)
        with self._guard:
            if self._active == key:
                return self._public(context, state="running")
            if self._active is not None:
                raise AIAdvisoryConflict(
                    "已有一条AI复核建议正在生成，请完成后再处理其他记录。"
                )
            self._active = key
            self._write_status(
                context,
                state="running",
                operation=operation,
            )
            try:
                self.executor.submit(
                    self._run,
                    job_id,
                    index,
                    operation,
                )
            except Exception:
                self._active = None
                self._write_status(
                    context,
                    state="failed",
                    operation=operation,
                    error={
                        "code": "QUEUE_FAILED",
                        "message": "AI复核任务无法启动，请稍后手动重试。",
                    },
                )
                raise
        return self._public(context, state="running")

    def _run(self, job_id: str, index: int, operation: str) -> None:
        context: dict[str, Any] | None = None
        try:
            context = self._context(job_id, index)
            request = self._build_request(context)
            response = self.llm_service.enhance_record(request)
            payload = response.to_dict()
            if payload["source_record_id"] != request.source_record_id:
                raise AIAdvisoryError("AI复核记录身份校验失败。")
            if not self._is_simplified_chinese_advisory(payload):
                raise AIAdvisoryError(
                    "模型未返回合格的简体中文业务说明。"
                )
            sidecar_path = self._sidecar_path(
                job_id, request.source_record_id
            )
            sidecar_path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(sidecar_path, payload)
            try:
                core_zip_refreshed = self._refresh_bundle(context)
            except (OSError, ValueError, AIAdvisoryError):
                core_zip_refreshed = False
            self._completed_this_session.add((job_id, index))
            self._write_status(
                context,
                state="completed",
                operation=operation,
                core_zip_refreshed=core_zip_refreshed,
            )
        except Exception as exc:
            if context is None:
                try:
                    context = self._context(job_id, index)
                except Exception:
                    context = None
            if context is not None:
                self._write_status(
                    context,
                    state="failed",
                    operation=operation,
                    error=self._safe_error(exc),
                )
        finally:
            with self._guard:
                if self._active == (job_id, index):
                    self._active = None

    def _validate_start(
        self,
        context: dict[str, Any],
        submitted: dict[str, Any],
    ) -> None:
        job = context["job"]
        if job.get("status") != "completed":
            raise AIAdvisoryUnavailable(
                "订单任务尚未完成，不能生成AI复核建议。"
            )
        if not self.llm_service.settings.is_ready():
            raise AIAdvisoryUnavailable("豆包AI尚未配置完成。")
        identity = context["identity"]
        required = {
            "job_id": context["job_id"],
            "source_record_id": identity["source_record_id"],
            "source_file": identity["source_file"],
            "sheet": identity["sheet"],
            "line_number": identity["line_number"],
        }
        if any(str(submitted.get(key, "")) != value for key, value in required.items()):
            raise AIAdvisoryUnavailable(
                "记录身份与任务产物不一致，请刷新页面后重试。"
            )

    def _context(self, job_id: str, index: int) -> dict[str, Any]:
        self._require_job_id(job_id)
        job_root = (self.jobs_root / job_id).resolve()
        job_path = job_root / "job.json"
        if not job_path.is_file():
            raise AIAdvisoryUnavailable("未找到该订单任务。")
        job = self._read_object(job_path)
        if job.get("status") != "completed":
            raise AIAdvisoryUnavailable(
                "订单任务尚未完成，不能读取AI建议。"
            )
        records = self._match_records(job_root, job)
        if index < 0 or index >= len(records):
            raise AIAdvisoryUnavailable("未找到对应的订单记录。")
        record = records[index]
        if not isinstance(record, dict):
            raise AIAdvisoryUnavailable("匹配记录格式不正确。")
        identity = self._identity(records, record, index)
        decision = str(record.get("decision", {}).get("status", ""))
        return {
            "job_id": job_id,
            "job_root": job_root,
            "job": job,
            "record_index": index,
            "record": record,
            "identity": identity,
            "decision": decision,
        }

    def _build_request(
        self, context: dict[str, Any]
    ) -> LLMEnhancementRequest:
        job_root = context["job_root"]
        job = context["job"]
        record = context["record"]
        line_number = context["identity"]["line_number"]
        business = self._read_list_artifact(job_root, job, "business")
        parse_report = self._read_object_artifact(
            job_root, job, "diagnostic"
        )
        validation = self._read_object_artifact(
            job_root, job, "validation"
        )
        parsed_record = self._record_by_line(business, line_number)
        parse_record = self._record_by_line(
            parse_report.get("records", []), line_number
        )
        validation_record = self._record_by_line(
            validation.get("records", []), line_number
        )
        identity = context["identity"]
        return LLMEnhancementRequest(
            job_id=context["job_id"],
            source_record_id=identity["source_record_id"],
            source_file=identity["source_file"],
            sheet_name=identity["sheet"],
            source_row=line_number,
            raw_evidence=self._minimal_raw_evidence(validation_record),
            parsed_record={
                field: self._safe_text(parsed_record.get(field, ""))
                for field in PRODUCT_FIELDS
            },
            parse_diagnostics=self._minimal_parse_diagnostics(parse_record),
            dictionary_validation=self._minimal_validation(
                validation_record
            ),
            top_candidates=self._minimal_candidates(record),
            enhancement_reason=self._enhancement_reason(
                context["decision"]
            ),
        )

    @staticmethod
    def _minimal_raw_evidence(
        validation_record: dict[str, Any]
    ) -> dict[str, Any]:
        fields = validation_record.get("fields", {})
        evidence: dict[str, Any] = {}
        if not isinstance(fields, dict):
            return evidence
        for name in VALIDATION_FIELDS:
            item = fields.get(name)
            if not isinstance(item, dict):
                continue
            entry = {
                "source_cells": [
                    str(value) for value in item.get("source_cells", [])
                ],
                "source_text": AIAdvisoryManager._safe_text(
                    item.get("source_text", "")
                ),
            }
            if name == "物料名称":
                entry["detected_category"] = str(
                    item.get("detected_category", "")
                )
            evidence[name] = entry
        return evidence

    @staticmethod
    def _minimal_parse_diagnostics(
        parse_record: dict[str, Any]
    ) -> dict[str, Any]:
        fields = parse_record.get("fields", {})
        if not isinstance(fields, dict):
            return {}
        result: dict[str, Any] = {}
        for name in PRODUCT_FIELDS:
            item = fields.get(name)
            if not isinstance(item, dict):
                continue
            source = item.get("source")
            source = source if isinstance(source, dict) else {}
            result[name] = {
                "status": str(item.get("status", "")),
                "rule": AIAdvisoryManager._safe_text(
                    item.get("rule", "")
                ),
                "source_cells": [
                    str(value) for value in source.get("cells", [])
                ],
            }
        return result

    @staticmethod
    def _minimal_validation(
        validation_record: dict[str, Any]
    ) -> dict[str, Any]:
        fields = validation_record.get("fields", {})
        if not isinstance(fields, dict):
            return {}
        result: dict[str, Any] = {}
        for name in VALIDATION_FIELDS:
            item = fields.get(name)
            if not isinstance(item, dict):
                continue
            result[name] = {
                "validation_status": str(
                    item.get("validation_status", "")
                ),
                "dictionary_candidates": [
                    AIAdvisoryManager._safe_text(value)
                    for value in item.get("dictionary_candidates", [])
                ][:10],
                "detected_category": str(
                    item.get("detected_category", "")
                ),
                "source_cells": [
                    str(value) for value in item.get("source_cells", [])
                ],
            }
        return result

    @staticmethod
    def _minimal_candidates(record: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = record.get("candidates", [])
        if not isinstance(candidates, list):
            return []
        result = []
        for candidate in candidates[:3]:
            if not isinstance(candidate, dict):
                continue
            fields = candidate.get("fields", {})
            fields = fields if isinstance(fields, dict) else {}
            result.append(
                {
                    "rank": candidate.get("rank", len(result) + 1),
                    "material_code": AIAdvisoryManager._safe_text(
                        candidate.get("material_code", "")
                    ),
                    "prototype_match_score": float(
                        candidate.get("prototype_match_score", 0.0)
                    ),
                    "comparable_field_count": int(
                        candidate.get("comparable_field_count", 0)
                    ),
                    "field_comparisons": {
                        name: {
                            "candidate_value": AIAdvisoryManager._safe_text(
                                value.get("candidate_value", "")
                            ),
                            "status": str(value.get("status", "")),
                        }
                        for name, value in fields.items()
                        if isinstance(value, dict) and name != "vector"
                    },
                }
            )
        return result

    @staticmethod
    def _enhancement_reason(decision: str) -> str:
        if decision in {
            "insufficient_evidence",
            "ambiguous_tie",
            "no_candidate",
        }:
            return decision
        return "user_requested"

    @staticmethod
    def _safe_text(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if SENSITIVE_LABEL_PATTERN.search(text):
            return "[redacted]"
        text = EMAIL_PATTERN.sub("[redacted-email]", text)
        text = PHONE_PATTERN.sub("[redacted-phone]", text)
        return text[:1200]

    def _public(
        self,
        context: dict[str, Any],
        *,
        state: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        identity = context["identity"]
        language_status = (
            self._language_status(result)
            if result is not None
            else "not_available"
        )
        return {
            "job_id": context["job_id"],
            "record_index": context["record_index"],
            "source_record_id": identity["source_record_id"],
            "source_file": identity["source_file"],
            "sheet": identity["sheet"],
            "line_number": identity["line_number"],
            "decision_status": context["decision"],
            "eligible": True,
            "state": state,
            "language_status": language_status,
            "historical_english": language_status == "historical_english",
            "can_regenerate_chinese": (
                language_status == "historical_english"
                and state in {"completed", "cached"}
            ),
            "result": result,
            "error": error,
            "technical_details": (
                self._technical_details(context)
                if result is not None
                else None
            ),
        }

    def _technical_details(
        self, context: dict[str, Any]
    ) -> dict[str, Any]:
        request = self._build_request(context)
        raw_evidence = [
            {
                "field": field,
                "source_cells": list(item.get("source_cells", [])),
                "source_text": str(item.get("source_text", "")),
            }
            for field, item in request.raw_evidence.items()
            if isinstance(item, dict)
        ]
        field_diagnostics = [
            {
                "field": field,
                "status": str(item.get("status", "")),
                "source_cells": list(item.get("source_cells", [])),
            }
            for field, item in request.parse_diagnostics.items()
            if isinstance(item, dict)
        ]
        candidates = []
        for candidate in request.top_candidates:
            comparisons = candidate.get("field_comparisons", {})
            candidates.append(
                {
                    "rank": int(candidate.get("rank", 0)),
                    "material_code": str(
                        candidate.get("material_code", "")
                    ),
                    "reference_score": float(
                        candidate.get("prototype_match_score", 0.0)
                    ),
                    "comparable_field_count": int(
                        candidate.get("comparable_field_count", 0)
                    ),
                    "field_comparisons": [
                        {
                            "field": field,
                            "candidate_value": str(
                                comparison.get("candidate_value", "")
                            ),
                            "status": str(
                                comparison.get("status", "")
                            ),
                        }
                        for field, comparison in comparisons.items()
                        if isinstance(comparison, dict)
                    ],
                }
            )
        return {
            "source": {
                "source_file": context["identity"]["source_file"],
                "sheet": context["identity"]["sheet"],
                "line_number": context["identity"]["line_number"],
            },
            "raw_evidence": raw_evidence,
            "field_diagnostics": field_diagnostics,
            "candidates": candidates,
        }

    @staticmethod
    def _language_status(result: dict[str, Any]) -> str:
        return (
            "zh_cn"
            if AIAdvisoryManager._is_simplified_chinese_advisory(result)
            else "historical_english"
        )

    @staticmethod
    def _is_simplified_chinese_advisory(
        result: dict[str, Any],
    ) -> bool:
        material_assessment = result.get("material_assessment", {})
        if not isinstance(material_assessment, dict):
            material_assessment = {}
        dynamic_texts = [
            str(result.get("reasoning_summary", "")),
            str(material_assessment.get("reason", "")),
        ]
        dynamic_texts.extend(
            str(item.get("reason", ""))
            for item in result.get("suggested_fields", [])
            if isinstance(item, dict)
        )
        dynamic_texts.extend(
            str(item) for item in result.get("warnings", [])
        )
        nonempty = [text.strip() for text in dynamic_texts if text.strip()]
        if not nonempty:
            return False
        # English evidence, product descriptions, codes, and model names may
        # remain verbatim, but every business explanation must include Chinese.
        return all(len(CJK_PATTERN.findall(text)) >= 2 for text in nonempty)

    def _failed_public(
        self,
        context: dict[str, Any],
        code: str,
        message: str,
    ) -> dict[str, Any]:
        return self._public(
            context,
            state="failed",
            error={"code": code, "message": message},
        )

    def _write_status(
        self,
        context: dict[str, Any],
        *,
        state: str,
        error: dict[str, Any] | None = None,
        operation: str = "generate_chinese",
        core_zip_refreshed: bool = False,
    ) -> None:
        identity = context["identity"]
        path = self._status_path(
            context["job_id"], identity["source_record_id"]
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            path,
            {
                "status_version": STATUS_VERSION,
                "state": state,
                "job_id": context["job_id"],
                "record_index": context["record_index"],
                "source_record_id": identity["source_record_id"],
                "updated_at": self._now(),
                "operation": operation,
                "zip_included": False,
                "core_zip_refreshed": core_zip_refreshed,
                "error": error or {},
            },
        )

    def _refresh_bundle(self, context: dict[str, Any]) -> bool:
        job = context["job"]
        root = context["job_root"]
        artifacts = job.get("artifacts", {})
        if not isinstance(artifacts, dict):
            return False
        required = {
            "正式业务.json": "business",
            "解析诊断.json": "diagnostic",
            "字典验证.json": "validation",
            "匹配候选.json": "matches",
            "匹配摘要.json": "match_summary",
        }
        stem = Path(str(job.get("file_name", "订单"))).stem
        files: dict[str, Path] = {}
        for suffix, key in required.items():
            relative = str(artifacts.get(key, ""))
            if not relative:
                return False
            files[f"{stem}_{suffix}"] = self._resolve(root, relative)
        bundle_relative = str(artifacts.get("zip", ""))
        if not bundle_relative:
            return False
        bundle = (root / bundle_relative).resolve()
        temporary = bundle.with_name(
            f".{bundle.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for archive_name, source in files.items():
                    archive.write(source, arcname=archive_name)
            os.replace(temporary, bundle)
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def _identity(
        self,
        records: list[Any],
        record: dict[str, Any],
        index: int,
    ) -> dict[str, str]:
        source_file = Path(str(record.get("source_file", ""))).name
        sheet = str(record.get("sheet", ""))
        line_number = str(record.get("行号", ""))
        if not source_file or not sheet or not line_number:
            raise AIAdvisoryUnavailable("订单记录缺少稳定来源身份。")
        canonical = f"{source_file}|{sheet}|{line_number}"
        duplicates = sum(
            1
            for item in records
            if isinstance(item, dict)
            and Path(str(item.get("source_file", ""))).name == source_file
            and str(item.get("sheet", "")) == sheet
            and str(item.get("行号", "")) == line_number
        )
        if duplicates > 1:
            canonical = f"{canonical}|{index}"
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "source_record_id": f"sha256:{digest}",
            "source_file": source_file,
            "sheet": sheet,
            "line_number": line_number,
        }

    def _match_records(
        self, root: Path, job: dict[str, Any]
    ) -> list[Any]:
        artifacts = job.get("artifacts", {})
        relative = (
            str(artifacts.get("matches", ""))
            if isinstance(artifacts, dict)
            else ""
        )
        if not relative:
            raise AIAdvisoryUnavailable("匹配结果尚未生成。")
        payload = self._read_object(self._resolve(root, relative))
        records = payload.get("records")
        if not isinstance(records, list):
            raise AIAdvisoryUnavailable("匹配结果格式不正确。")
        return records

    def _read_object_artifact(
        self,
        root: Path,
        job: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        relative = str(job.get("artifacts", {}).get(kind, ""))
        return self._read_object(self._resolve(root, relative))

    def _read_list_artifact(
        self,
        root: Path,
        job: dict[str, Any],
        kind: str,
    ) -> list[Any]:
        relative = str(job.get("artifacts", {}).get(kind, ""))
        value = self._read_json(self._resolve(root, relative))
        if not isinstance(value, list):
            raise AIAdvisoryUnavailable("正式业务结果格式不正确。")
        return value

    @staticmethod
    def _record_by_line(records: Any, line_number: str) -> dict[str, Any]:
        if not isinstance(records, list):
            raise AIAdvisoryUnavailable("记录列表格式不正确。")
        for record in records:
            if isinstance(record, dict) and str(
                record.get("行号", "")
            ) == line_number:
                return record
        raise AIAdvisoryUnavailable("无法在任务产物中重新定位订单记录。")

    @staticmethod
    def _resolve(root: Path, relative: str) -> Path:
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise AIAdvisoryUnavailable("任务产物不存在或路径无效。")
        return path

    def _sidecar_path(self, job_id: str, source_record_id: str) -> Path:
        safe_id = source_record_id.replace(":", "_")
        return self.jobs_root / job_id / "ai-advisory" / f"{safe_id}.json"

    def _status_path(self, job_id: str, source_record_id: str) -> Path:
        safe_id = source_record_id.replace(":", "_")
        return (
            self.jobs_root
            / job_id
            / "ai-advisory"
            / f"{safe_id}.status.json"
        )

    @staticmethod
    def _safe_error(exc: Exception) -> dict[str, Any]:
        if isinstance(exc, LLMProviderError):
            labels = {
                "authentication_error": "模型身份验证未通过",
                "permission_error": "模型访问权限不足",
                "model_not_found": "模型配置不可用",
                "rate_limited": "模型服务当前繁忙",
                "timeout": "模型响应超时",
                "connection_error": "模型服务连接失败",
                "structured_output_error": "模型返回格式不符合要求",
            }
            return {
                "code": exc.code.value,
                "message": (
                    f"AI复核建议调用失败："
                    f"{labels.get(exc.code.value, '模型服务暂时不可用')}。"
                    "请检查配置或稍后手动重试。"
                ),
                "attempt_count": exc.attempts,
                "request_id": AIAdvisoryManager._masked_request_id(
                    exc.request_id
                ),
                **AIAdvisoryManager._safe_diagnostics(exc.diagnostics),
            }
        return {
            "code": "AI_ADVISORY_FAILED",
            "message": "AI复核建议生成失败，请手动重试。",
            "error_type": type(exc).__name__,
        }

    @staticmethod
    def _masked_request_id(value: str) -> str:
        if len(value) <= 10:
            return "<redacted>" if value else ""
        return f"{value[:6]}...{value[-4:]}"

    @staticmethod
    def _safe_diagnostics(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        allowed = {
            "error_stage",
            "error_code",
            "schema_path",
            "missing_keys",
            "extra_keys",
            "expected_type",
            "actual_type",
            "invalid_enum_value",
            "source_record_id_match",
            "response_item_types",
            "has_function_call",
            "has_output_text",
        }
        safe: dict[str, Any] = {}
        for key in allowed:
            if key not in value:
                continue
            item = value[key]
            if isinstance(item, (str, int, float, bool)) or item is None:
                safe[key] = item
            elif isinstance(item, list):
                safe[key] = [
                    str(entry)[:120]
                    for entry in item[:20]
                    if isinstance(entry, (str, int, float, bool))
                ]
        return safe

    @staticmethod
    def _read_object(path: Path) -> dict[str, Any]:
        value = AIAdvisoryManager._read_json(path)
        if not isinstance(value, dict):
            raise AIAdvisoryUnavailable("本地AI建议数据格式不正确。")
        return value

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _require_job_id(job_id: str) -> None:
        if len(job_id) != 32 or any(
            character not in "0123456789abcdef" for character in job_id
        ):
            raise AIAdvisoryUnavailable("订单任务编号无效。")

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
