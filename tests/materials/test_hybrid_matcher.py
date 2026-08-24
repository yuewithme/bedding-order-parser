from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Sequence

import numpy as np
import pytest

from bedding_order_parser.materials import hybrid_matcher
from bedding_order_parser.materials.hybrid_matcher import (
    build_order_query,
    match_orders,
)
from bedding_order_parser.materials.query_embedding_runner import (
    IsolatedEmbeddingResult,
)
from bedding_order_parser.materials.loader import compute_sha256
from bedding_order_parser.materials.match_writer import (
    CANDIDATES_NAME,
    SUMMARY_NAME,
    write_match_outputs,
)
from bedding_order_parser.materials.vector_index import build_vector_indexes
from bedding_order_parser.models.final_result import FINAL_FIELD_NAMES


class FakeEmbeddingAdapter:
    model_name = "fake/bge"
    revision = "fake-revision"
    device = "cpu"
    dimension = 3
    cache_path = ""

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        del batch_size
        vectors: list[np.ndarray] = []
        for text in texts:
            vector = np.array(
                [
                    1.0 if "240*260" in text or "260*240" in text else 0.0,
                    1.0 if "T300" in text else 0.0,
                    1.0 if "灰色" in text else 0.0,
                ],
                dtype=np.float32,
            )
            if not vector.any():
                vector[0] = 1.0
            vectors.append(vector / np.linalg.norm(vector))
        return np.asarray(vectors, dtype=np.float32)


def formal_result() -> dict[str, object]:
    values: dict[str, object] = {field: "" for field in FINAL_FIELD_NAMES}
    values.update(
        {
            "客户": "Example",
            "行号": "1",
            "物料名称": "Example 被套",
            "规格": "260*240cm",
            "颜色": "漂白色",
            "面料": "贡缎/T300/100C",
            "面料-涤棉成分": "100C",
            "款式": "无飞边",
            "加标方式": "客标",
            "尺寸类型": "交货尺寸",
            "相似分数": 0.0,
        }
    )
    return values


def material_rows() -> list[tuple[object, ...]]:
    shared_text = (
        "品类：被套；规格：240*260cm；颜色：漂白色；面料：贡缎；"
        "面料品类：贡缎；密度：T300；成分：C100；款式：无飞边；"
        "加标方式：客标；尺寸类型：交货尺寸"
    )
    return [
        (
            "MAT-A",
            2,
            "被套",
            "240*260cm",
            "漂白色",
            "贡缎",
            "贡缎",
            "T300",
            "C100",
            "无飞边",
            "客标",
            "交货尺寸",
            shared_text,
        ),
        (
            "MAT-B",
            3,
            "被套",
            "240*260cm",
            "漂白色",
            "贡缎",
            "贡缎",
            "T300",
            "C100",
            "无飞边",
            "客标",
            "交货尺寸",
            shared_text,
        ),
        (
            "MAT-C",
            4,
            "被套",
            "250*270cm",
            "灰色",
            "贡缎",
            "贡缎",
            "T400",
            "C80/T20",
            "",
            "",
            "",
            "品类：被套；规格：250*270cm；颜色：灰色；密度：T400",
        ),
    ]


def write_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    orders_dir = tmp_path / "orders"
    reports_dir = tmp_path / "reports"
    store_dir = tmp_path / "material_store"
    orders_dir.mkdir()
    reports_dir.mkdir()
    store_dir.mkdir()

    result_path = orders_dir / "sample_gate2d.json"
    result_path.write_text(
        json.dumps([formal_result()], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path = reports_dir / "sample_gate2d_parse_report.json"
    report_path.write_text(
        json.dumps(
            {
                "input": {"file_name": "sample.xlsx", "sheet_name": "PI"},
                "records": [{"行号": "1", "fields": {}, "warnings": []}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    store_path = store_dir / "material_master.sqlite3"
    with sqlite3.connect(store_path) as connection:
        connection.execute(
            """
            CREATE TABLE materials (
                material_code TEXT PRIMARY KEY,
                source_row INTEGER NOT NULL,
                product_category TEXT NOT NULL,
                spec_normalized TEXT NOT NULL,
                color_normalized TEXT NOT NULL,
                fabric_normalized TEXT NOT NULL,
                fabric_category_normalized TEXT NOT NULL,
                density_normalized TEXT NOT NULL,
                composition_normalized TEXT NOT NULL,
                style_normalized TEXT NOT NULL,
                label_method_normalized TEXT NOT NULL,
                size_type_normalized TEXT NOT NULL,
                embedding_text TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO materials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            material_rows(),
        )

    documents_path = store_dir / "material_documents.jsonl"
    documents = [
        {
            "id": row[0],
            "text": row[12],
            "metadata": {
                "source_row": row[1],
                "product_category": row[2],
                "spec": row[3],
                "color": row[4],
                "fabric_category": row[6],
                "density": row[7],
                "composition": row[8],
                "style": row[9],
                "size_type": row[11],
            },
        }
        for row in material_rows()
    ]
    documents_path.write_text(
        "".join(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
            for document in documents
        ),
        encoding="utf-8",
    )
    (store_dir / "material_store_manifest.json").write_text(
        json.dumps(
            {
                "source": {"sha256": "fixture-source"},
                "outputs": {"sqlite_records": 3, "jsonl_records": 3},
            }
        ),
        encoding="utf-8",
    )
    index_dir = tmp_path / "vector_index"
    build_vector_indexes(
        documents_path,
        store_path,
        index_dir,
        model_name="fake/bge",
        adapter=FakeEmbeddingAdapter(),
    )
    return orders_dir, reports_dir, store_path, index_dir


def test_hard_conflicts_are_removed_and_duplicate_top_is_ambiguous(tmp_path) -> None:
    orders, reports, store, index = write_fixture(tmp_path)

    result = match_orders(
        orders,
        reports,
        store,
        index,
        top_k=10,
        vector_recall_k=3,
        adapter=FakeEmbeddingAdapter(),
    )
    record = result.candidates_payload["records"][0]

    assert record["retrieval"] == {
        "structured_candidates": 2,
        "vector_candidates": 3,
        "union_candidates": 3,
        "hard_conflict_removed": 1,
        "hard_conflicts_by_field": {
            "color": 1,
            "composition": 1,
            "density": 1,
            "spec": 1,
        },
        "post_filter_candidates": 2,
    }
    assert record["decision"]["status"] == "ambiguous_tie"
    assert record["decision"]["action"] == "manual_review"
    assert record["decision"]["top1_margin"] == 0.0
    assert record["candidates"][0]["ambiguous_duplicate_group"] is True
    assert set(
        record["candidates"][0]["duplicate_group"]["duplicate_material_codes"]
    ) == {"MAT-A", "MAT-B"}


def test_formal_json_is_unchanged_and_outputs_are_atomic(tmp_path) -> None:
    orders, reports, store, index = write_fixture(tmp_path)
    official = orders / "sample_gate2d.json"
    before = compute_sha256(official)
    result = match_orders(
        orders,
        reports,
        store,
        index,
        top_k=10,
        vector_recall_k=3,
        adapter=FakeEmbeddingAdapter(),
    )

    paths = write_match_outputs(result, tmp_path / "output")

    assert compute_sha256(official) == before
    assert paths.candidates_path.name == CANDIDATES_NAME
    assert paths.summary_path.name == SUMMARY_NAME
    assert sorted(path.name for path in paths.output_dir.iterdir()) == [
        CANDIDATES_NAME,
        SUMMARY_NAME,
    ]
    assert result.summary_payload["summary"]["order_records"] == 1
    assert result.summary_payload["accuracy_statement"].startswith(
        "No Top-1 accuracy"
    )


def test_composition_number_is_not_inferred_as_density() -> None:
    result = formal_result()
    result["面料"] = "贡缎/100C"

    query = build_order_query(
        result,
        source_file="sample.xlsx",
        sheet="PI",
        result_json="sample_gate2d.json",
        parse_report_json="sample_gate2d_parse_report.json",
    )

    assert query.composition == "C100"
    assert query.density == ""


def test_isolated_embedding_finishes_before_search_runtime_load(
    tmp_path: Path, monkeypatch
) -> None:
    orders, reports, store, index = write_fixture(tmp_path)
    events: list[str] = []
    fake_adapter = FakeEmbeddingAdapter()
    original_candidates = hybrid_matcher.load_all_material_candidates
    original_runtime = hybrid_matcher._load_vector_search_runtime

    def encode(texts, **kwargs):
        del kwargs
        events.append("worker_exited")
        return IsolatedEmbeddingResult(
            vectors=fake_adapter.encode(texts, batch_size=1),
            worker_pid=123,
            started_at="start",
            completed_at="done",
        )

    def load_candidates(path):
        events.append("candidates")
        return original_candidates(path)

    def load_runtime(path):
        events.append("faiss_mapping")
        return original_runtime(path)

    monkeypatch.setattr(hybrid_matcher, "encode_queries_isolated", encode)
    monkeypatch.setattr(
        hybrid_matcher, "load_all_material_candidates", load_candidates
    )
    monkeypatch.setattr(
        hybrid_matcher, "_load_vector_search_runtime", load_runtime
    )

    result = match_orders(
        orders,
        reports,
        store,
        index,
        top_k=10,
        vector_recall_k=3,
        embedding_runtime_dir=tmp_path / "runtime",
    )

    assert events == ["worker_exited", "candidates", "faiss_mapping"]
    assert result.candidates_payload["record_count"] == 1


def test_parent_matcher_has_no_eager_model_or_faiss_import() -> None:
    source = Path(hybrid_matcher.__file__).read_text(encoding="utf-8")

    assert "SentenceTransformerEmbeddingAdapter" not in source
    assert "\nimport faiss" not in source


def test_cancel_after_worker_prevents_candidate_and_faiss_load(
    tmp_path: Path, monkeypatch
) -> None:
    orders, reports, store, index = write_fixture(tmp_path)
    checks = 0

    def cancel_check() -> None:
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise RuntimeError("interrupted")

    monkeypatch.setattr(
        hybrid_matcher,
        "encode_queries_isolated",
        lambda texts, **kwargs: IsolatedEmbeddingResult(
            vectors=FakeEmbeddingAdapter().encode(texts, batch_size=1),
            worker_pid=123,
            started_at="start",
            completed_at="done",
        ),
    )
    monkeypatch.setattr(
        hybrid_matcher,
        "load_all_material_candidates",
        lambda path: pytest.fail("candidates loaded after cancellation"),
    )
    monkeypatch.setattr(
        hybrid_matcher,
        "_load_vector_search_runtime",
        lambda path: pytest.fail("FAISS loaded after cancellation"),
    )

    with pytest.raises(RuntimeError, match="interrupted"):
        match_orders(
            orders,
            reports,
            store,
            index,
            top_k=10,
            vector_recall_k=3,
            cancel_check=cancel_check,
        )
