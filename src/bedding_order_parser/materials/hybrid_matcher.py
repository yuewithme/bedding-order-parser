"""Hybrid structured/vector material matching prototype."""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from bedding_order_parser.exceptions import BeddingOrderParserError
from bedding_order_parser.materials.candidate_filter import (
    MaterialCandidate,
    OrderQuery,
    load_all_material_candidates,
    merge_candidate_codes,
    retrieve_structured_candidate_codes,
)
from bedding_order_parser.materials.embedding_model import EmbeddingAdapter
from bedding_order_parser.materials.field_comparator import (
    FIELD_STATUSES,
    CandidateEvaluation,
    compare_candidate,
)
from bedding_order_parser.materials.faiss_io import read_faiss_index
from bedding_order_parser.materials.loader import compute_sha256
from bedding_order_parser.materials.query_embedding_runner import (
    encode_queries_isolated,
)
from bedding_order_parser.materials.query_embedding_contract import (
    validate_normalized_float32_vectors,
)
from bedding_order_parser.materials.normalizer import (
    normalize_color,
    normalize_composition,
    normalize_density,
    normalize_product_category,
    normalize_text,
)
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES


class HybridMatchError(BeddingOrderParserError):
    """Raised when hybrid matching cannot preserve its input/output contract."""


MIN_COMPARABLE_FIELDS_FOR_RANKED_DECISION = 3
VALID_CANDIDATES_TOO_MANY_THRESHOLD = 100
DUVET_INDEX_NAME = "duvet_cover.faiss"
DUVET_MAPPING_NAME = "duvet_cover_mapping.jsonl"
MANIFEST_NAME = "vector_index_manifest.json"


@dataclass(frozen=True)
class HybridMatchResult:
    candidates_payload: dict[str, Any]
    summary_payload: dict[str, Any]
    order_result_hashes: dict[str, str]
    parse_report_hashes: dict[str, str]


@dataclass(frozen=True)
class _OrderInput:
    query: OrderQuery
    formal_result: dict[str, Any]


def match_orders(
    orders_dir: str | Path,
    parse_reports_dir: str | Path,
    store_path: str | Path,
    index_dir: str | Path,
    *,
    top_k: int = 10,
    vector_recall_k: int = 300,
    adapter: EmbeddingAdapter | None = None,
    cancel_check: Callable[[], None] | None = None,
    embedding_runtime_dir: str | Path | None = None,
    embedding_diagnostics_path: str | Path | None = None,
) -> HybridMatchResult:
    """Match existing Gate 2D records without modifying formal results."""
    if top_k < 10:
        raise HybridMatchError("top_k must be at least 10.")
    if vector_recall_k <= 0:
        raise HybridMatchError("vector_recall_k must be greater than zero.")

    order_root = Path(orders_dir).expanduser().resolve()
    report_root = Path(parse_reports_dir).expanduser().resolve()
    store_file = Path(store_path).expanduser().resolve()
    index_root = Path(index_dir).expanduser().resolve()
    order_files = sorted(order_root.glob("*_gate2d.json"))
    report_files = sorted(report_root.glob("*_gate2d_parse_report.json"))
    if not order_files or not report_files:
        raise HybridMatchError("Gate 2D result or parse-report inputs are missing.")

    order_hashes = {path.name: compute_sha256(path) for path in order_files}
    report_hashes = {path.name: compute_sha256(path) for path in report_files}
    inputs = _load_order_inputs(order_files, report_files)
    manifest = _load_vector_manifest(index_root)
    model = manifest["model"]
    query_texts = [item.query.embedding_text for item in inputs]
    _check_cancel(cancel_check)
    if adapter is None:
        isolated = encode_queries_isolated(
            query_texts,
            model_name=str(model["name"]),
            revision=str(model.get("revision", "")),
            device=str(model["device"]),
            dimension=int(model["dimension"]),
            normalize=bool(model["normalized"]),
            runtime_root=embedding_runtime_dir,
            diagnostics_path=embedding_diagnostics_path,
            cancel_check=cancel_check,
        )
        query_vectors = isolated.vectors
    else:
        _validate_adapter_contract(adapter, model)
        query_vectors = adapter.encode(query_texts, batch_size=1)
    try:
        query_vectors = validate_normalized_float32_vectors(
            query_vectors,
            expected_rows=len(inputs),
            expected_dimension=int(model["dimension"]),
        )
    except ValueError as exc:
        raise HybridMatchError("Query vectors failed the embedding contract.") from exc
    _check_cancel(cancel_check)
    candidates = load_all_material_candidates(store_file)
    _check_cancel(cancel_check)
    index, mappings, loaded_manifest = _load_vector_search_runtime(index_root)
    if loaded_manifest != manifest:
        raise HybridMatchError("Vector index manifest changed during query encoding.")
    mapping_by_code = {str(row["material_code"]): row for row in mappings}
    if not set(mapping_by_code).issubset(candidates):
        raise HybridMatchError(
            "Duvet-cover vector mapping contains codes absent from SQLite."
        )
    if query_vectors.shape[1] != index.d:
        raise HybridMatchError("Query dimension does not match the FAISS index.")
    recall_count = min(vector_recall_k, int(index.ntotal))
    vector_scores, vector_positions = index.search(query_vectors, recall_count)
    position_by_code = {
        str(mapping["material_code"]): int(mapping["position"])
        for mapping in mappings
    }
    reconstructed_vectors: dict[int, np.ndarray] = {}

    records: list[dict[str, Any]] = []
    hard_conflict_totals: Counter[str] = Counter()
    field_status_totals: dict[str, Counter[str]] = defaultdict(Counter)
    for input_index, item in enumerate(inputs):
        _check_cancel(cancel_check)
        vector_recall = _vector_recall(
            mappings,
            vector_positions[input_index],
            vector_scores[input_index],
        )
        structured_codes = [
            code
            for code in retrieve_structured_candidate_codes(store_file, item.query)
            if code in mapping_by_code
        ]
        union_codes = merge_candidate_codes(structured_codes, vector_recall)
        evaluations: list[tuple[MaterialCandidate, CandidateEvaluation]] = []
        removed = 0
        record_hard_conflicts: Counter[str] = Counter()
        for code in union_codes:
            candidate = candidates.get(code)
            if candidate is None:
                raise HybridMatchError(f"Unknown candidate code in recall: {code}")
            raw_vector_score = vector_recall.get(code)
            if raw_vector_score is None:
                position = position_by_code[code]
                candidate_vector = reconstructed_vectors.get(position)
                if candidate_vector is None:
                    candidate_vector = np.asarray(
                        index.reconstruct(position), dtype=np.float32
                    )
                    reconstructed_vectors[position] = candidate_vector
                raw_vector_score = float(
                    np.dot(query_vectors[input_index], candidate_vector)
                )
            evaluation = compare_candidate(
                item.query, candidate, vector_score=raw_vector_score
            )
            if evaluation.hard_conflict_fields:
                removed += 1
                hard_conflict_totals.update(evaluation.hard_conflict_fields)
                record_hard_conflicts.update(evaluation.hard_conflict_fields)
                continue
            evaluations.append((candidate, evaluation))

        evaluations.sort(
            key=lambda pair: pair[1].prototype_match_score,
            reverse=True,
        )
        duplicate_groups = _duplicate_groups(evaluations)
        candidate_rows = _candidate_rows(
            evaluations[:top_k],
            duplicate_groups=duplicate_groups,
            field_status_totals=field_status_totals,
        )
        decision = _decision(evaluations, duplicate_groups)
        records.append(
            {
                "source_file": item.query.source_file,
                "sheet": item.query.sheet,
                "行号": item.query.line_number,
                "result_json": item.query.result_json,
                "parse_report_json": item.query.parse_report_json,
                "query": item.query.to_dict(),
                "retrieval": {
                    "structured_candidates": len(structured_codes),
                    "vector_candidates": len(vector_recall),
                    "union_candidates": len(union_codes),
                    "hard_conflict_removed": removed,
                    "hard_conflicts_by_field": dict(
                        sorted(record_hard_conflicts.items())
                    ),
                    "post_filter_candidates": len(evaluations),
                },
                "decision": decision,
                "candidates": candidate_rows,
            }
        )

    _assert_hashes_unchanged(order_files, order_hashes, "formal result")
    _assert_hashes_unchanged(report_files, report_hashes, "parse report")
    _check_cancel(cancel_check)
    score_contract = _score_contract()
    candidates_payload = {
        "prototype_version": "1.0",
        "mode": "manual_review_only",
        "score_contract": score_contract,
        "vector_index": {
            "model": manifest["model"]["name"],
            "revision": manifest["model"].get("revision", ""),
            "dimension": manifest["model"]["dimension"],
            "scope": "duvet_cover",
            "records": manifest["index"]["duvet_cover_records"],
        },
        "record_count": len(records),
        "records": records,
    }
    summary_payload = _build_summary(
        records,
        hard_conflict_totals=hard_conflict_totals,
        field_status_totals=field_status_totals,
        score_contract=score_contract,
    )
    return HybridMatchResult(
        candidates_payload=candidates_payload,
        summary_payload=summary_payload,
        order_result_hashes=order_hashes,
        parse_report_hashes=report_hashes,
    )


def build_order_query(
    formal_result: dict[str, Any],
    *,
    source_file: str,
    sheet: str,
    result_json: str,
    parse_report_json: str,
) -> OrderQuery:
    """Build a material-only query from one immutable formal result."""
    material_name = str(formal_result["物料名称"])
    product_category = normalize_product_category(material_name)
    fabric = normalize_text(formal_result["面料"])
    fabric_components = _query_fabric_components(fabric)
    composition = normalize_composition(
        str(formal_result["面料-涤棉成分"])
        or fabric_components["composition"]
    )
    density = fabric_components["density"]
    values = {
        "product_category": product_category,
        "spec": normalize_text(formal_result["规格"]),
        "color": normalize_color(str(formal_result["颜色"])),
        "fabric": fabric,
        "fabric_category": fabric_components["category"],
        "density": density,
        "composition": composition,
        "style": normalize_text(formal_result["款式"]),
        "label_method": normalize_text(formal_result["加标方式"]),
        "size_type": normalize_text(formal_result["尺寸类型"]),
        "line_note": normalize_text(formal_result["行备注"]),
    }
    embedding_text = "；".join(
        f"{label}：{values[key]}"
        for label, key in (
            ("品类", "product_category"),
            ("规格", "spec"),
            ("颜色", "color"),
            ("面料", "fabric"),
            ("面料品类", "fabric_category"),
            ("密度", "density"),
            ("成分", "composition"),
            ("款式", "style"),
            ("加标方式", "label_method"),
            ("尺寸类型", "size_type"),
            ("工艺备注", "line_note"),
        )
        if values[key]
    )
    return OrderQuery(
        source_file=source_file,
        sheet=sheet,
        line_number=str(formal_result["行号"]),
        result_json=result_json,
        parse_report_json=parse_report_json,
        embedding_text=embedding_text,
        **values,
    )


def _load_order_inputs(
    order_files: list[Path],
    report_files: list[Path],
) -> list[_OrderInput]:
    reports_by_stem = {
        path.name.removesuffix("_gate2d_parse_report.json"): path
        for path in report_files
    }
    if len(reports_by_stem) != len(report_files):
        raise HybridMatchError("Duplicate parse-report names detected.")

    inputs: list[_OrderInput] = []
    used_reports: set[Path] = set()
    for order_path in order_files:
        stem = order_path.name.removesuffix("_gate2d.json")
        report_path = reports_by_stem.get(stem)
        if report_path is None:
            raise HybridMatchError(
                f"Missing parse report for formal result: {order_path.name}"
            )
        used_reports.add(report_path)
        results = _read_json_list(order_path)
        report = _read_json_object(report_path)
        report_records = report.get("records")
        if not isinstance(report_records, list) or len(report_records) != len(results):
            raise HybridMatchError(
                f"Formal result/parse report count mismatch: {order_path.name}"
            )
        source_file = str(report.get("input", {}).get("file_name", ""))
        sheet = str(report.get("input", {}).get("sheet_name", ""))
        if not source_file or not sheet:
            raise HybridMatchError(f"Incomplete report input metadata: {report_path.name}")
        for formal_result, report_record in zip(
            results, report_records, strict=True
        ):
            _validate_formal_result(formal_result, order_path)
            if str(report_record.get("行号", "")) != str(formal_result["行号"]):
                raise HybridMatchError(
                    f"Line-number mismatch in {order_path.name}: "
                    f"{formal_result['行号']}"
                )
            inputs.append(
                _OrderInput(
                    query=build_order_query(
                        formal_result,
                        source_file=source_file,
                        sheet=sheet,
                        result_json=order_path.name,
                        parse_report_json=report_path.name,
                    ),
                    formal_result=formal_result,
                )
            )
    if used_reports != set(report_files):
        unused = sorted(path.name for path in set(report_files) - used_reports)
        raise HybridMatchError(f"Unpaired parse reports: {unused}")
    return inputs


def _load_vector_manifest(index_root: Path) -> dict[str, Any]:
    manifest = _read_json_object(index_root / MANIFEST_NAME)
    _validate_vector_manifest(manifest)
    return manifest


def _load_vector_search_runtime(
    index_root: Path,
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    from bedding_order_parser.materials.vector_search import (
        _read_mapping,
        _validate_artifact,
    )

    manifest = _load_vector_manifest(index_root)
    index_path = index_root / DUVET_INDEX_NAME
    mapping_path = index_root / DUVET_MAPPING_NAME
    _validate_artifact(index_path, manifest, "duvet_index")
    _validate_artifact(mapping_path, manifest, "duvet_mapping")
    index = read_faiss_index(index_path)
    mappings = _read_mapping(mapping_path)
    if index.ntotal != len(mappings):
        raise HybridMatchError("FAISS/mapping record count mismatch.")
    model = manifest["model"]
    if index.d != int(model["dimension"]):
        raise HybridMatchError("FAISS dimension does not match manifest.")
    return index, mappings, manifest


def _validate_adapter_contract(
    adapter: EmbeddingAdapter, model: dict[str, Any]
) -> None:
    if (
        adapter.model_name != model["name"]
        or int(adapter.dimension) != int(model["dimension"])
        or (model.get("revision") and adapter.revision != model.get("revision"))
    ):
        raise HybridMatchError(
            "Embedding adapter does not match the vector index manifest."
        )


def _check_cancel(cancel_check: Callable[[], None] | None) -> None:
    if cancel_check is not None:
        cancel_check()


def _validate_vector_manifest(manifest: dict[str, Any]) -> None:
    model = manifest.get("model", {})
    index = manifest.get("index", {})
    if model.get("normalized") is not True:
        raise HybridMatchError("Manifest requires normalized embeddings.")
    if not model.get("name") or int(model.get("dimension", 0)) <= 0:
        raise HybridMatchError("Manifest embedding model contract is incomplete.")
    if index.get("type") != "IndexFlatIP":
        raise HybridMatchError("Manifest index type is not IndexFlatIP.")
    if index.get("metric") != "inner_product_on_normalized_vectors":
        raise HybridMatchError("Manifest vector metric is unsupported.")


def _vector_recall(
    mappings: list[dict[str, Any]],
    positions: np.ndarray,
    scores: np.ndarray,
) -> dict[str, float]:
    recalled: dict[str, float] = {}
    for position, score in zip(positions.tolist(), scores.tolist(), strict=True):
        if position < 0:
            continue
        mapping = mappings[position]
        if int(mapping["position"]) != position:
            raise HybridMatchError(f"Mapping position mismatch: {position}")
        recalled[str(mapping["material_code"])] = float(score)
    return recalled


def _duplicate_groups(
    evaluations: list[tuple[MaterialCandidate, CandidateEvaluation]],
) -> dict[str, dict[str, Any]]:
    by_text: dict[str, list[tuple[MaterialCandidate, CandidateEvaluation]]] = (
        defaultdict(list)
    )
    for candidate, evaluation in evaluations:
        by_text[candidate.embedding_text].append((candidate, evaluation))

    groups: dict[str, dict[str, Any]] = {}
    for embedding_text, members in by_text.items():
        if len(members) < 2:
            continue
        scores = [member[1].prototype_match_score for member in members]
        if max(scores) - min(scores) > 1e-6:
            continue
        codes = [member[0].material_code for member in members]
        comparable = [member[0].comparable_values() for member in members]
        keys = tuple(comparable[0])
        identical_fields = [
            key for key in keys if len({row[key] for row in comparable}) == 1
        ]
        differing_fields = [
            key for key in keys if len({row[key] for row in comparable}) > 1
        ]
        group = {
            "ambiguous_duplicate_group": True,
            "duplicate_group_size": len(members),
            "duplicate_material_codes": codes,
            "identical_fields": identical_fields,
            "differing_fields": differing_fields,
            "required_business_evidence": (
                differing_fields
                if differing_fields
                else [
                    "an approved material-code priority or external master-data key"
                ]
            ),
            "embedding_text": embedding_text,
        }
        for code in codes:
            groups[code] = group
    return groups


def _candidate_rows(
    evaluations: list[tuple[MaterialCandidate, CandidateEvaluation]],
    *,
    duplicate_groups: dict[str, dict[str, Any]],
    field_status_totals: dict[str, Counter[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_score: float | None = None
    previous_rank = 0
    for ordinal, (candidate, evaluation) in enumerate(evaluations, start=1):
        rank = (
            previous_rank
            if previous_score is not None
            and math.isclose(
                previous_score, evaluation.prototype_match_score, abs_tol=1e-6
            )
            else ordinal
        )
        previous_score = evaluation.prototype_match_score
        previous_rank = rank
        fields = {
            field_name: comparison.to_dict()
            for field_name, comparison in evaluation.fields.items()
        }
        for field_name, comparison in evaluation.fields.items():
            field_status_totals[field_name][comparison.status] += 1
        duplicate = duplicate_groups.get(candidate.material_code)
        rows.append(
            {
                "rank": rank,
                "material_code": candidate.material_code,
                "source_row": candidate.source_row,
                "prototype_match_score": evaluation.prototype_match_score,
                "structured_score": evaluation.structured_score,
                "vector_score": evaluation.vector_score,
                "vector_score_normalized": evaluation.vector_score_normalized,
                "comparable_field_count": evaluation.comparable_field_count,
                "duplicate_group_size": (
                    duplicate["duplicate_group_size"] if duplicate else 1
                ),
                "ambiguous_duplicate_group": bool(duplicate),
                "duplicate_group": duplicate,
                "fields": fields,
            }
        )
    return rows


def _decision(
    evaluations: list[tuple[MaterialCandidate, CandidateEvaluation]],
    duplicate_groups: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not evaluations:
        return {
            "status": "no_candidate",
            "action": "manual_review",
            "top1_margin": None,
            "comparable_field_count": 0,
            "reason": "All recalled candidates were removed by explicit hard conflicts.",
        }
    top = evaluations[0][1]
    margin = (
        None
        if len(evaluations) == 1
        else round(
            top.prototype_match_score
            - evaluations[1][1].prototype_match_score,
            6,
        )
    )
    top_code = evaluations[0][0].material_code
    if top.comparable_field_count < MIN_COMPARABLE_FIELDS_FOR_RANKED_DECISION:
        status = "insufficient_evidence"
        reason = (
            "Fewer than three weighted structured fields are comparable; "
            "the available evidence is insufficient for a ranked decision."
        )
    elif top_code in duplicate_groups:
        status = "ambiguous_tie"
        reason = (
            "The leading embedding text and structured evidence map to multiple "
            "indistinguishable material codes."
        )
    elif margin is not None and math.isclose(margin, 0.0, abs_tol=1e-6):
        status = "ambiguous_tie"
        reason = "The two leading candidates have the same prototype score."
    elif len(evaluations) == 1 or (margin is not None and margin > 1e-6):
        status = "unique_best_candidate"
        reason = (
            "One candidate has the highest prototype score; no automatic writeback "
            "threshold is approved."
        )
    else:
        status = "ranked_candidates"
        reason = "Candidates are ranked but the available evidence does not isolate one."
    return {
        "status": status,
        "action": "manual_review",
        "top1_margin": margin,
        "comparable_field_count": top.comparable_field_count,
        "reason": reason,
    }


def _build_summary(
    records: list[dict[str, Any]],
    *,
    hard_conflict_totals: Counter[str],
    field_status_totals: dict[str, Counter[str]],
    score_contract: dict[str, Any],
) -> dict[str, Any]:
    decisions = Counter(record["decision"]["status"] for record in records)
    top1_scores = [
        record["candidates"][0]["prototype_match_score"]
        for record in records
        if record["candidates"]
    ]
    margins = [
        record["decision"]["top1_margin"]
        for record in records
        if record["decision"]["top1_margin"] is not None
    ]
    ambiguous_duplicate = sum(
        bool(record["candidates"])
        and record["candidates"][0]["ambiguous_duplicate_group"]
        for record in records
    )
    required_owner_confirmation = [
        {
            "source_file": record["source_file"],
            "sheet": record["sheet"],
            "行号": record["行号"],
            "decision_status": record["decision"]["status"],
            "reason": (
                "No approved ground-truth material code exists for this order record."
            ),
        }
        for record in records
    ]
    retrieval_fields = (
        "structured_candidates",
        "vector_candidates",
        "union_candidates",
        "hard_conflict_removed",
        "post_filter_candidates",
    )
    return {
        "prototype_version": "1.0",
        "mode": "manual_review_only",
        "score_contract": score_contract,
        "summary": {
            "order_records": len(records),
            "records_with_candidates": sum(
                bool(record["candidates"]) for record in records
            ),
            "decision_statuses": dict(sorted(decisions.items())),
            "no_candidate": decisions["no_candidate"],
            "valid_candidates_too_many": sum(
                record["retrieval"]["post_filter_candidates"]
                > VALID_CANDIDATES_TOO_MANY_THRESHOLD
                for record in records
            ),
            "valid_candidates_too_many_threshold": (
                VALID_CANDIDATES_TOO_MANY_THRESHOLD
            ),
            "ambiguous_duplicate": ambiguous_duplicate,
            "unique_best_candidate": decisions["unique_best_candidate"],
            "top1_score_distribution": _distribution(top1_scores),
            "top1_margin_distribution": _distribution(margins),
            "field_statuses_top_k": {
                field: {
                    status: field_status_totals[field].get(status, 0)
                    for status in FIELD_STATUSES
                }
                for field in sorted(field_status_totals)
            },
            "hard_conflicts_removed_by_field": dict(
                sorted(hard_conflict_totals.items())
            ),
            "average_candidate_counts": {
                field: round(
                    statistics.fmean(
                        record["retrieval"][field] for record in records
                    ),
                    3,
                )
                for field in retrieval_fields
            },
        },
        "accuracy_statement": (
            "No Top-1 accuracy is reported because the 49 formal material-code "
            "ground truths are unavailable."
        ),
        "required_owner_confirmation": required_owner_confirmation,
    }


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
        }
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        quartiles = [ordered[0], ordered[0], ordered[0]]
    else:
        quartiles = statistics.quantiles(ordered, n=4, method="inclusive")
    return {
        "count": len(ordered),
        "min": round(ordered[0], 6),
        "q1": round(quartiles[0], 6),
        "median": round(statistics.median(ordered), 6),
        "q3": round(quartiles[2], 6),
        "max": round(ordered[-1], 6),
    }


def _score_contract() -> dict[str, Any]:
    return {
        "name": "hybrid_score_v1",
        "structured_weight": 0.75,
        "vector_weight": 0.25,
        "structured_field_weights": {
            "spec": 0.25,
            "composition": 0.18,
            "fabric": 0.17,
            "density": 0.15,
            "color": 0.10,
            "style": 0.08,
            "label_method": 0.04,
            "size_type": 0.03,
        },
        "status_scores": {
            "exact_match": 1.00,
            "equivalent_match": 0.95,
            "partial_match": 0.60,
            "no_match": 0.00,
        },
        "missing_policy": (
            "missing_query, missing_candidate, and not_comparable are excluded "
            "from the available structured-weight denominator"
        ),
        "vector_mapping": "(clamp(raw_vector_score, -1, 1) + 1) / 2",
        "calibration": "engineering baseline without approved ground truth",
        "decision_evidence_floor": {
            "minimum_comparable_weighted_fields": (
                MIN_COMPARABLE_FIELDS_FOR_RANKED_DECISION
            ),
            "effect": "below this floor the status is insufficient_evidence",
        },
    }


def _query_fabric_components(text: str) -> dict[str, str]:
    from bedding_order_parser.dictionaries.shadow_matcher import _fabric_components

    components = _fabric_components(text)
    return {
        "category": normalize_text(components.get("category", "")),
        "density": normalize_density(components.get("density", "")),
        "composition": normalize_composition(components.get("composition", "")),
    }


def _validate_formal_result(result: Any, path: Path) -> None:
    if not isinstance(result, dict) or tuple(result) != FINAL_FIELD_NAMES:
        raise HybridMatchError(f"Invalid formal 20-field schema: {path.name}")
    if str(result["物料编码"]):
        raise HybridMatchError(f"Formal material code is not empty: {path.name}")
    if float(result["相似分数"]) != 0.0:
        raise HybridMatchError(f"Formal similarity score is not zero: {path.name}")


def _assert_hashes_unchanged(
    paths: list[Path],
    expected: dict[str, str],
    label: str,
) -> None:
    actual = {path.name: compute_sha256(path) for path in paths}
    if actual != expected:
        raise HybridMatchError(f"{label} SHA-256 changed during matching.")


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HybridMatchError(f"Unable to read JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HybridMatchError(f"Expected JSON object: {path}")
    return payload


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HybridMatchError(f"Unable to read JSON list {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise HybridMatchError(f"Expected JSON list: {path}")
    return payload
