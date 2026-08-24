"""Lazy desktop adapters for the existing dictionary and material matching boundaries."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from bedding_order_parser.ai_full_order.downstream import (
    MaterialMatchOutput,
    MaterialSelection,
)
from bedding_order_parser.ai_full_order.resolution import ResolvedRecord
from bedding_order_parser.desktop.resource_paths import ApplicationPaths
from bedding_order_parser.diagnostics.models import (
    DERIVED,
    EXTRACTED,
    FieldDiagnostic,
    ParseReport,
    RecordDiagnostic,
    SourceEvidence,
)
from bedding_order_parser.models.final_result import (
    FINAL_FIELD_NAMES,
    STRING_FIELD_NAMES,
    FinalResult,
)


@dataclass(frozen=True)
class DesktopV2DownstreamFactory:
    """Create per-job adapters without loading workbooks, BGE-M3, or FAISS at startup."""

    paths: ApplicationPaths

    def is_ready(self) -> bool:
        required = (
            self.paths.material_store,
            self.paths.faiss_index,
            self.paths.faiss_mapping,
            self.paths.vector_manifest,
            self.paths.rules_path,
            self.paths.styles_path,
        )
        return self.paths.model_cache.is_dir() and all(path.is_file() for path in required)

    def bind(
        self, input_path: Path, runtime_root: Path
    ) -> tuple["DesktopDictionaryValidator", "DesktopMaterialMatcher"]:
        if not self.is_ready():
            raise RuntimeError("desktop V2 downstream resources are not ready")
        return (
            DesktopDictionaryValidator(
                input_path=input_path,
                rules_path=self.paths.rules_path,
                styles_path=self.paths.styles_path,
            ),
            DesktopMaterialMatcher(
                input_path=input_path,
                runtime_root=runtime_root,
                store_path=self.paths.material_store,
                index_dir=self.paths.index_dir,
            ),
        )

    def __call__(
        self, input_path: Path, runtime_root: Path
    ) -> tuple["DesktopDictionaryValidator", "DesktopMaterialMatcher"]:
        return self.bind(input_path, runtime_root)


@dataclass(frozen=True)
class DesktopDictionaryValidator:
    """Adapt resolved V2 values to the existing validation-only dictionary entry point."""

    input_path: Path
    rules_path: Path
    styles_path: Path

    def validate(
        self,
        records: Sequence[ResolvedRecord],
        evidence: Mapping[str, Mapping[str, str]],
    ) -> Mapping[str, Any]:
        from bedding_order_parser.dictionaries.product_validation import (
            build_product_validation_report,
        )

        final_records = _provisional_records(records)
        report = _parse_report(self.input_path, records, evidence)
        return build_product_validation_report(
            input_path=self.input_path,
            records=final_records,
            parse_report=report,
            rules_path=self.rules_path,
            styles_path=self.styles_path,
        )


@dataclass(frozen=True)
class DesktopMaterialMatcher:
    """Use the current file-based matcher only after a V2 job reaches its matching stage."""

    input_path: Path
    runtime_root: Path
    store_path: Path
    index_dir: Path

    def match(
        self,
        records: Sequence[FinalResult],
        resolved: Sequence[ResolvedRecord],
    ) -> MaterialMatchOutput:
        from bedding_order_parser.materials.hybrid_matcher import match_orders

        self.runtime_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="ai-full-order-v2-", dir=self.runtime_root
        ) as temporary:
            root = Path(temporary)
            business_path = root / "ai_full_order_gate2d.json"
            report_path = root / "ai_full_order_gate2d_parse_report.json"
            business_path.write_text(
                json.dumps(
                    [record.to_json_dict() for record in records],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            report_path.write_text(
                json.dumps(
                    _matching_parse_report(self.input_path, records),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            matched = match_orders(
                root,
                root,
                self.store_path,
                self.index_dir,
                top_k=10,
                vector_recall_k=300,
                embedding_runtime_dir=root / "embedding",
            )

        # The current matching contract is manual-review-only. Keep the formal fields
        # empty until a separately approved material decision writes them back.
        selections = {
            record.source_record_id: MaterialSelection(record.source_record_id)
            for record in resolved
        }
        return MaterialMatchOutput(
            selections=selections,
            candidates_payload=matched.candidates_payload,
            summary_payload=matched.summary_payload,
        )


def _provisional_records(records: Sequence[ResolvedRecord]) -> tuple[FinalResult, ...]:
    values: list[FinalResult] = []
    for record in records:
        payload: dict[str, str | float] = {field: "" for field in STRING_FIELD_NAMES}
        payload.update(record.business_fields())
        payload["物料编码"] = ""
        payload["相似分数"] = 0.0
        values.append(FinalResult.from_mapping(payload))
    return tuple(values)


def _parse_report(
    input_path: Path,
    records: Sequence[ResolvedRecord],
    evidence: Mapping[str, Mapping[str, str]],
) -> ParseReport:
    report_records: list[RecordDiagnostic] = []
    for record in records:
        fields: dict[str, FieldDiagnostic] = {}
        for field_name in FINAL_FIELD_NAMES:
            decision = record.decisions.get(field_name)
            evidence_id = decision.evidence_ids[0] if decision and decision.evidence_ids else ""
            item = evidence.get(evidence_id, {})
            cells = item.get("cell_range", "") if isinstance(item, Mapping) else ""
            sheet = item.get("sheet_name", "") if isinstance(item, Mapping) else ""
            fields[field_name] = FieldDiagnostic(
                value=(decision.value if decision else ""),
                status=EXTRACTED if evidence_id else DERIVED,
                source=SourceEvidence(
                    sheet=str(sheet),
                    cells=(str(cells),) if cells else (),
                    region="ai_full_order_v2",
                ),
                rule="ai_full_order_v2.downstream_adapter",
            )
        report_records.append(RecordDiagnostic(record.line_number, fields))
    return ParseReport(
        input_file_name=input_path.name,
        input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
        sheet_name="multiple",
        result_json="ai_full_order_gate2d.json",
        parse_report_json="ai_full_order_gate2d_parse_report.json",
        records=tuple(report_records),
    )


def _matching_parse_report(
    input_path: Path, records: Sequence[FinalResult]
) -> dict[str, Any]:
    return {
        "input": {"file_name": input_path.name, "sheet_name": "ai_enhanced"},
        "records": [{"行号": str(record.values["行号"])} for record in records],
    }
