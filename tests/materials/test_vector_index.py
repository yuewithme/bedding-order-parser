from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Sequence

import faiss
import numpy as np
import pytest

from bedding_order_parser.materials.faiss_io import (
    read_faiss_index,
    write_faiss_index,
)
from bedding_order_parser.materials.loader import compute_sha256
from bedding_order_parser.materials.vector_index import (
    ALL_INDEX_NAME,
    ALL_MAPPING_NAME,
    DUVET_INDEX_NAME,
    DUVET_MAPPING_NAME,
    MANIFEST_NAME,
    VectorIndexError,
    build_vector_indexes,
)
from bedding_order_parser.materials.vector_search import search_vector_index


class FakeEmbeddingAdapter:
    model_name = "fake/bge"
    revision = "fake-revision"
    device = "cpu"
    dimension = 3
    cache_path = ""

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        del batch_size
        vectors = []
        for text in texts:
            vector = np.array(
                [
                    1.0 if "alpha" in text else 0.0,
                    1.0 if "beta" in text else 0.0,
                    1.0 if "gamma" in text else 0.0,
                ],
                dtype=np.float32,
            )
            if not vector.any():
                vector[0] = 1.0
            vectors.append(vector / np.linalg.norm(vector))
        return np.asarray(vectors, dtype=np.float32)


class InvalidEmbeddingAdapter(FakeEmbeddingAdapter):
    def __init__(self, invalid_value: float) -> None:
        self.invalid_value = invalid_value

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        vectors = super().encode(texts, batch_size=batch_size)
        vectors[0, 0] = self.invalid_value
        return vectors


class FailingEmbeddingAdapter(FakeEmbeddingAdapter):
    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        raise RuntimeError("fake encoding failure")


class CountingEmbeddingAdapter(FakeEmbeddingAdapter):
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.fail_on_call = fail_on_call
        self.batch_lengths: list[int] = []

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray:
        self.batch_lengths.append(len(texts))
        if self.fail_on_call == len(self.batch_lengths):
            raise RuntimeError("planned resumable encoding failure")
        return super().encode(texts, batch_size=batch_size)


def document(
    code: str,
    text: str,
    *,
    source_row: int,
    category: str,
) -> dict:
    return {
        "id": code,
        "text": text,
        "metadata": {
            "source_row": source_row,
            "product_category": category,
            "spec": "240*260cm",
            "color": "漂白色",
            "fabric_category": "贡缎",
            "density": "T300",
            "composition": "C100",
            "style": "",
            "size_type": "交货尺寸",
        },
    }


def write_inputs(root: Path, documents: list[dict]) -> tuple[Path, Path]:
    source_dir = root / "material_store"
    source_dir.mkdir()
    documents_path = source_dir / "material_documents.jsonl"
    documents_path.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
            for item in documents
        ),
        encoding="utf-8",
    )

    store_path = source_dir / "material_master.sqlite3"
    with sqlite3.connect(store_path) as connection:
        connection.execute(
            """
            CREATE TABLE materials (
                material_code TEXT PRIMARY KEY,
                source_row INTEGER NOT NULL,
                product_category TEXT NOT NULL,
                embedding_text TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO materials VALUES (?, ?, ?, ?)",
            [
                (
                    item["id"],
                    item["metadata"]["source_row"],
                    item["metadata"]["product_category"],
                    item["text"],
                )
                for item in documents
            ],
        )

    manifest = {
        "source": {"sha256": "source-csv-sha"},
        "outputs": {"sqlite_records": len(documents), "jsonl_records": len(documents)},
    }
    (source_dir / "material_store_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return documents_path, store_path


def sample_documents() -> list[dict]:
    return [
        document("001-A", "alpha", source_row=2, category="被套"),
        document("002-B", "beta", source_row=3, category="枕套"),
        document("003-C", "alpha beta", source_row=4, category="被套"),
    ]


def build_fake_index(tmp_path: Path) -> tuple[Path, dict]:
    documents_path, store_path = write_inputs(tmp_path, sample_documents())
    output_dir = tmp_path / "vector_index"
    result = build_vector_indexes(
        documents_path,
        store_path,
        output_dir,
        model_name="fake/bge",
        batch_size=2,
        adapter=FakeEmbeddingAdapter(),
    )
    return output_dir, result.manifest


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_faiss_io_supports_unicode_windows_paths(tmp_path) -> None:
    target = tmp_path / "中文资料库" / "被套索引.faiss"
    target.parent.mkdir()
    index = faiss.IndexFlatIP(3)
    vectors = np.asarray(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32
    )
    index.add(vectors)

    write_faiss_index(index, target)
    restored = read_faiss_index(target)
    scores, positions = restored.search(vectors[:1], 2)

    assert target.is_file()
    assert restored.ntotal == 2
    assert positions[0, 0] == 0
    assert scores[0, 0] == pytest.approx(1.0)


def test_jsonl_order_and_mapping_positions_are_preserved(tmp_path) -> None:
    output_dir, _ = build_fake_index(tmp_path)

    mapping = read_jsonl(output_dir / ALL_MAPPING_NAME)

    assert [row["position"] for row in mapping] == [0, 1, 2]
    assert [row["material_code"] for row in mapping] == ["001-A", "002-B", "003-C"]
    assert [row["source_row"] for row in mapping] == [2, 3, 4]


def test_full_and_duvet_indexes_have_expected_counts(tmp_path) -> None:
    output_dir, manifest = build_fake_index(tmp_path)

    all_index = read_faiss_index(output_dir / ALL_INDEX_NAME)
    duvet_index = read_faiss_index(output_dir / DUVET_INDEX_NAME)

    assert all_index.ntotal == 3
    assert duvet_index.ntotal == 2
    assert len(read_jsonl(output_dir / ALL_MAPPING_NAME)) == 3
    assert len(read_jsonl(output_dir / DUVET_MAPPING_NAME)) == 2
    assert manifest["index"]["all_records"] == 3
    assert manifest["index"]["duvet_cover_records"] == 2


def test_index_vectors_are_float32_finite_and_normalized(tmp_path) -> None:
    output_dir, _ = build_fake_index(tmp_path)
    index = read_faiss_index(output_dir / ALL_INDEX_NAME)

    vectors = np.vstack([index.reconstruct(position) for position in range(index.ntotal)])

    assert vectors.dtype == np.float32
    assert np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)


def test_index_flat_ip_search_restores_material_code_from_mapping(tmp_path) -> None:
    output_dir, _ = build_fake_index(tmp_path)

    results = search_vector_index(
        output_dir,
        "beta",
        scope="all",
        top_k=2,
        adapter=FakeEmbeddingAdapter(),
    )

    assert results[0]["material_code"] == "002-B"
    assert results[0]["vector_score"] == pytest.approx(1.0)
    assert results[0]["source_row"] == 3
    assert "相似分数" not in results[0]


def test_string_material_codes_are_not_coerced_to_integer(tmp_path) -> None:
    output_dir, _ = build_fake_index(tmp_path)

    result = search_vector_index(
        output_dir,
        "alpha",
        scope="duvet_cover",
        top_k=1,
        adapter=FakeEmbeddingAdapter(),
    )[0]

    assert result["material_code"] == "001-A"
    assert isinstance(result["material_code"], str)


def test_search_rejects_model_name_mismatch(tmp_path) -> None:
    output_dir, _ = build_fake_index(tmp_path)
    adapter = FakeEmbeddingAdapter()
    adapter.model_name = "different/model"

    with pytest.raises(VectorIndexError, match="model"):
        search_vector_index(output_dir, "alpha", adapter=adapter)


def test_search_rejects_dimension_mismatch(tmp_path) -> None:
    output_dir, _ = build_fake_index(tmp_path)
    adapter = FakeEmbeddingAdapter()
    adapter.dimension = 4

    with pytest.raises(VectorIndexError, match="dimension"):
        search_vector_index(output_dir, "alpha", adapter=adapter)


def test_search_rejects_model_revision_mismatch(tmp_path) -> None:
    output_dir, _ = build_fake_index(tmp_path)
    adapter = FakeEmbeddingAdapter()
    adapter.revision = "different-revision"

    with pytest.raises(VectorIndexError, match="revision"):
        search_vector_index(output_dir, "alpha", adapter=adapter)


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf")])
def test_build_rejects_nan_and_inf(tmp_path, invalid_value) -> None:
    documents_path, store_path = write_inputs(tmp_path, sample_documents())
    output_dir = tmp_path / "vector_index"

    with pytest.raises(VectorIndexError, match="NaN or Inf"):
        build_vector_indexes(
            documents_path,
            store_path,
            output_dir,
            model_name="fake/bge",
            adapter=InvalidEmbeddingAdapter(invalid_value),
        )

    assert not output_dir.exists()


def test_build_does_not_overwrite_existing_output_by_default(tmp_path) -> None:
    documents_path, store_path = write_inputs(tmp_path, sample_documents())
    output_dir = tmp_path / "vector_index"
    build_vector_indexes(
        documents_path,
        store_path,
        output_dir,
        model_name="fake/bge",
        adapter=FakeEmbeddingAdapter(),
    )

    with pytest.raises(VectorIndexError, match="--overwrite"):
        build_vector_indexes(
            documents_path,
            store_path,
            output_dir,
            model_name="fake/bge",
            adapter=FakeEmbeddingAdapter(),
        )


def test_failed_overwrite_preserves_previous_complete_index(tmp_path) -> None:
    documents_path, store_path = write_inputs(tmp_path, sample_documents())
    output_dir = tmp_path / "vector_index"
    build_vector_indexes(
        documents_path,
        store_path,
        output_dir,
        model_name="fake/bge",
        adapter=FakeEmbeddingAdapter(),
    )
    manifest_sha = compute_sha256(output_dir / MANIFEST_NAME)

    with pytest.raises(RuntimeError, match="fake encoding failure"):
        build_vector_indexes(
            documents_path,
            store_path,
            output_dir,
            model_name="fake/bge",
            overwrite=True,
            adapter=FailingEmbeddingAdapter(),
        )

    assert compute_sha256(output_dir / MANIFEST_NAME) == manifest_sha
    assert not list(tmp_path.glob(".vector_index.*.tmp"))


def test_failed_build_resumes_verified_embedding_chunks(tmp_path) -> None:
    documents = [
        document(
            f"{index:04d}",
            "alpha" if index % 2 else "beta",
            source_row=index + 2,
            category="被套",
        )
        for index in range(33)
    ]
    documents_path, store_path = write_inputs(tmp_path, documents)
    output_dir = tmp_path / "vector_index"
    checkpoint_dir = tmp_path / "embedding-checkpoints"
    first = CountingEmbeddingAdapter(fail_on_call=2)

    with pytest.raises(RuntimeError, match="planned resumable"):
        build_vector_indexes(
            documents_path,
            store_path,
            output_dir,
            model_name="fake/bge",
            batch_size=1,
            adapter=first,
            checkpoint_dir=checkpoint_dir,
        )

    assert first.batch_lengths == [32, 1]
    assert len(list(checkpoint_dir.rglob("vectors-*.npy"))) == 1
    checkpoint_manifests = list(checkpoint_dir.rglob("checkpoint_manifest.json"))
    assert len(checkpoint_manifests) == 1
    checkpoint_text = checkpoint_manifests[0].read_text(encoding="utf-8")
    assert "alpha" not in checkpoint_text
    assert "beta" not in checkpoint_text

    resumed = CountingEmbeddingAdapter()
    result = build_vector_indexes(
        documents_path,
        store_path,
        output_dir,
        model_name="fake/bge",
        batch_size=1,
        adapter=resumed,
        checkpoint_dir=checkpoint_dir,
    )

    assert resumed.batch_lengths == [1]
    assert result.manifest["build"]["checkpoint_schema_version"] == "1.0"
    assert result.manifest["build"]["reused_chunks"] == 1
    assert result.manifest["build"]["encoded_chunks"] == 1
    assert not checkpoint_dir.exists()
    assert read_faiss_index(output_dir / ALL_INDEX_NAME).ntotal == 33


def test_corrupt_checkpoint_chunk_is_reencoded(tmp_path) -> None:
    documents = [
        document(
            f"{index:04d}",
            "alpha" if index % 2 else "beta",
            source_row=index + 2,
            category="被套",
        )
        for index in range(33)
    ]
    documents_path, store_path = write_inputs(tmp_path, documents)
    output_dir = tmp_path / "vector_index"
    checkpoint_dir = tmp_path / "embedding-checkpoints"

    with pytest.raises(RuntimeError, match="planned resumable"):
        build_vector_indexes(
            documents_path,
            store_path,
            output_dir,
            model_name="fake/bge",
            batch_size=1,
            adapter=CountingEmbeddingAdapter(fail_on_call=2),
            checkpoint_dir=checkpoint_dir,
        )
    checkpoint_chunk = next(checkpoint_dir.rglob("vectors-*.npy"))
    checkpoint_chunk.write_bytes(b"corrupt checkpoint")

    resumed = CountingEmbeddingAdapter()
    result = build_vector_indexes(
        documents_path,
        store_path,
        output_dir,
        model_name="fake/bge",
        batch_size=1,
        adapter=resumed,
        checkpoint_dir=checkpoint_dir,
    )

    assert resumed.batch_lengths == [32, 1]
    assert result.manifest["build"]["reused_chunks"] == 0
    assert result.manifest["build"]["encoded_chunks"] == 2
    assert not checkpoint_dir.exists()


def test_checkpoint_directory_cannot_overlap_final_output(tmp_path) -> None:
    documents_path, store_path = write_inputs(tmp_path, sample_documents())
    output_dir = tmp_path / "vector_index"

    with pytest.raises(VectorIndexError, match="must not overlap"):
        build_vector_indexes(
            documents_path,
            store_path,
            output_dir,
            model_name="fake/bge",
            adapter=FakeEmbeddingAdapter(),
            checkpoint_dir=output_dir,
        )

    assert not output_dir.exists()


def test_artifact_hashes_and_source_hashes_are_recorded(tmp_path) -> None:
    documents_path, store_path = write_inputs(tmp_path, sample_documents())
    store_manifest_path = documents_path.with_name("material_store_manifest.json")
    output_dir = tmp_path / "vector_index"

    result = build_vector_indexes(
        documents_path,
        store_path,
        output_dir,
        model_name="fake/bge",
        adapter=FakeEmbeddingAdapter(),
    )

    manifest = result.manifest
    assert manifest["source"]["material_jsonl_sha256"] == compute_sha256(documents_path)
    assert manifest["source"]["material_store_sha256"] == compute_sha256(store_path)
    assert manifest["source"]["material_store_manifest_sha256"] == compute_sha256(
        store_manifest_path
    )
    for key, file_name in (
        ("all_index", ALL_INDEX_NAME),
        ("all_mapping", ALL_MAPPING_NAME),
        ("duvet_index", DUVET_INDEX_NAME),
        ("duvet_mapping", DUVET_MAPPING_NAME),
    ):
        assert manifest["artifacts"][f"{key}_sha256"] == compute_sha256(
            output_dir / file_name
        )


def test_material_sources_and_unrelated_official_json_remain_unchanged(tmp_path) -> None:
    documents_path, store_path = write_inputs(tmp_path, sample_documents())
    store_manifest_path = documents_path.with_name("material_store_manifest.json")
    official_json = tmp_path / "official.json"
    official_json.write_text('[{"物料编码":"","相似分数":0.0}]', encoding="utf-8")
    protected = {
        path: compute_sha256(path)
        for path in (
            documents_path,
            store_path,
            store_manifest_path,
            official_json,
        )
    }

    build_vector_indexes(
        documents_path,
        store_path,
        tmp_path / "vector_index",
        model_name="fake/bge",
        adapter=FakeEmbeddingAdapter(),
    )

    assert {path: compute_sha256(path) for path in protected} == protected
