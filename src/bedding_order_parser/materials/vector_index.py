"""Build atomic FAISS indexes over canonical material documents."""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import faiss
import numpy as np

from bedding_order_parser.exceptions import BeddingOrderParserError
from bedding_order_parser.materials.embedding_model import (
    EmbeddingAdapter,
    SentenceTransformerEmbeddingAdapter,
)
from bedding_order_parser.materials.embedding_checkpoints import (
    CHECKPOINT_SCHEMA_VERSION,
    EmbeddingCheckpointStore,
)
from bedding_order_parser.materials.faiss_io import write_faiss_index
from bedding_order_parser.materials.loader import compute_sha256


ALL_INDEX_NAME = "materials_all.faiss"
DUVET_INDEX_NAME = "duvet_cover.faiss"
ALL_MAPPING_NAME = "materials_all_mapping.jsonl"
DUVET_MAPPING_NAME = "duvet_cover_mapping.jsonl"
MANIFEST_NAME = "vector_index_manifest.json"


class VectorIndexError(BeddingOrderParserError):
    """Raised when vector index inputs or outputs violate their contract."""


@dataclass(frozen=True)
class VectorIndexBuildResult:
    output_dir: Path
    manifest_path: Path
    all_records: int
    duvet_cover_records: int
    dimension: int
    duration_seconds: float
    manifest: dict[str, Any]


@dataclass(frozen=True)
class MaterialDocument:
    material_code: str
    text: str
    source_row: int
    product_category: str
    metadata: dict[str, Any]


def build_vector_indexes(
    documents_path: str | Path,
    store_path: str | Path,
    output_dir: str | Path,
    *,
    model_name: str = "BAAI/bge-m3",
    device: str = "cpu",
    batch_size: int = 16,
    overwrite: bool = False,
    adapter: EmbeddingAdapter | None = None,
    checkpoint_dir: str | Path | None = None,
) -> VectorIndexBuildResult:
    """Build full and duvet-cover IndexFlatIP indexes in JSONL order."""
    if batch_size <= 0:
        raise VectorIndexError("batch_size must be greater than zero.")

    started = time.perf_counter()
    documents_file = Path(documents_path).expanduser().resolve()
    store_file = Path(store_path).expanduser().resolve()
    target = Path(output_dir).expanduser().resolve()
    store_manifest_file = documents_file.with_name("material_store_manifest.json")
    _require_file(documents_file, "Material JSONL")
    _require_file(store_file, "Material SQLite store")
    _require_file(store_manifest_file, "Material store manifest")
    if target.exists() and any(target.iterdir()) and not overwrite:
        raise VectorIndexError(
            f"Vector index output already exists; pass --overwrite: {target}"
        )

    source_hashes_before = _source_hashes(
        documents_file, store_file, store_manifest_file
    )
    store_manifest = _load_json(store_manifest_file)
    source_csv_sha256 = str(store_manifest.get("source", {}).get("sha256", ""))
    documents = _load_documents(documents_file)
    _validate_store(store_file, documents)

    embedding = adapter or SentenceTransformerEmbeddingAdapter(
        model_name, device=device
    )
    if embedding.model_name != model_name:
        raise VectorIndexError(
            f"Embedding adapter model mismatch: {embedding.model_name!r} != {model_name!r}"
        )

    encode_window = max(batch_size, batch_size * 32)
    checkpoint_root = Path(
        checkpoint_dir
        or target.parent / f".{target.name}.embedding-checkpoints"
    ).expanduser().resolve()
    if _paths_overlap(checkpoint_root, target):
        raise VectorIndexError(
            "Embedding checkpoint directory and final output must not overlap."
        )
    checkpoint_store = EmbeddingCheckpointStore(
        checkpoint_root,
        {
            "source_hashes": source_hashes_before,
            "source_csv_sha256": source_csv_sha256,
            "document_count": len(documents),
            "model_name": embedding.model_name,
            "model_revision": embedding.revision,
            "device": embedding.device,
            "dimension": int(embedding.dimension),
            "normalized": True,
            "batch_size": batch_size,
            "encode_window": encode_window,
        },
    )

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir = parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    temp_dir.mkdir()
    backup_dir: Path | None = None
    try:
        all_index, duvet_index, all_mapping, duvet_mapping, dimension = (
            _encode_and_index(
                documents,
                embedding,
                batch_size,
                encode_window=encode_window,
                checkpoint_store=checkpoint_store,
            )
        )
        if all_index.ntotal != len(documents):
            raise VectorIndexError("Full FAISS index record count mismatch.")
        if duvet_index.ntotal != len(duvet_mapping):
            raise VectorIndexError("Duvet FAISS index record count mismatch.")

        write_faiss_index(all_index, temp_dir / ALL_INDEX_NAME)
        write_faiss_index(duvet_index, temp_dir / DUVET_INDEX_NAME)
        _write_mapping(temp_dir / ALL_MAPPING_NAME, all_mapping)
        _write_mapping(temp_dir / DUVET_MAPPING_NAME, duvet_mapping)

        duration = time.perf_counter() - started
        artifacts = _artifact_manifest(temp_dir)
        manifest = {
            "source": {
                "material_jsonl_path": _display_path(documents_path),
                "material_jsonl_sha256": source_hashes_before["material_jsonl"],
                "material_store_path": _display_path(store_path),
                "material_store_sha256": source_hashes_before["material_store"],
                "material_store_manifest_sha256": source_hashes_before[
                    "material_store_manifest"
                ],
                "source_csv_sha256": source_csv_sha256,
            },
            "model": {
                "name": embedding.model_name,
                "revision": embedding.revision,
                "dimension": dimension,
                "normalized": True,
                "device": embedding.device,
                "cache_path": getattr(embedding, "cache_path", ""),
            },
            "index": {
                "type": "IndexFlatIP",
                "metric": "inner_product_on_normalized_vectors",
                "all_records": int(all_index.ntotal),
                "duvet_cover_records": int(duvet_index.ntotal),
            },
            "artifacts": artifacts,
            "build": {
                "batch_size": batch_size,
                "duration_seconds": round(duration, 3),
                "peak_memory_if_available": None,
                "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
                "encoded_chunks": checkpoint_store.encoded_chunks,
                "reused_chunks": checkpoint_store.reused_chunks,
            },
        }
        _write_json(temp_dir / MANIFEST_NAME, manifest)

        source_hashes_after = _source_hashes(
            documents_file, store_file, store_manifest_file
        )
        if source_hashes_after != source_hashes_before:
            raise VectorIndexError("Material source SHA-256 changed during index build.")

        backup_dir = _commit_directory(temp_dir, target, overwrite=overwrite)
        if backup_dir is not None:
            shutil.rmtree(backup_dir)
        checkpoint_store.cleanup_after_success()
        return VectorIndexBuildResult(
            output_dir=target,
            manifest_path=target / MANIFEST_NAME,
            all_records=int(all_index.ntotal),
            duvet_cover_records=int(duvet_index.ntotal),
            dimension=dimension,
            duration_seconds=duration,
            manifest=manifest,
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if backup_dir is not None and backup_dir.exists() and not target.exists():
            backup_dir.rename(target)
        raise


def _encode_and_index(
    documents: Sequence[MaterialDocument],
    adapter: EmbeddingAdapter,
    batch_size: int,
    *,
    encode_window: int,
    checkpoint_store: EmbeddingCheckpointStore,
) -> tuple[
    faiss.IndexFlatIP,
    faiss.IndexFlatIP,
    list[dict[str, Any]],
    list[dict[str, Any]],
    int,
]:
    if not documents:
        raise VectorIndexError("Material JSONL contains no documents.")

    dimension = int(adapter.dimension)
    if dimension <= 0:
        raise VectorIndexError(f"Invalid embedding dimension: {dimension}")
    all_index = faiss.IndexFlatIP(dimension)
    duvet_index = faiss.IndexFlatIP(dimension)
    all_mapping: list[dict[str, Any]] = []
    duvet_mapping: list[dict[str, Any]] = []

    for start in range(0, len(documents), encode_window):
        batch_documents = documents[start : start + encode_window]
        end = start + len(batch_documents)
        vectors = checkpoint_store.load(start, end, dimension=dimension)
        loaded_from_checkpoint = vectors is not None
        if not loaded_from_checkpoint:
            vectors = adapter.encode(
                [document.text for document in batch_documents],
                batch_size=batch_size,
            )
        vectors = _validate_vectors(
            vectors,
            expected_rows=len(batch_documents),
            expected_dimension=dimension,
        )
        if not loaded_from_checkpoint:
            checkpoint_store.save(start, end, vectors)
        all_index.add(vectors)
        duvet_positions = [
            index
            for index, document in enumerate(batch_documents)
            if document.product_category == "被套"
        ]
        if duvet_positions:
            duvet_index.add(
                np.ascontiguousarray(vectors[duvet_positions], dtype=np.float32)
            )

        for document in batch_documents:
            all_mapping.append(_mapping_row(len(all_mapping), document))
            if document.product_category == "被套":
                duvet_mapping.append(_mapping_row(len(duvet_mapping), document))

    return all_index, duvet_index, all_mapping, duvet_mapping, dimension


def _validate_vectors(
    vectors: np.ndarray,
    *,
    expected_rows: int,
    expected_dimension: int,
) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    if array.shape != (expected_rows, expected_dimension):
        raise VectorIndexError(
            "Embedding shape mismatch: "
            f"expected {(expected_rows, expected_dimension)}, got {array.shape}"
        )
    if not np.isfinite(array).all():
        raise VectorIndexError("Embedding vectors contain NaN or Inf.")
    norms = np.linalg.norm(array, axis=1)
    if not np.isfinite(norms).all() or not np.allclose(
        norms, 1.0, rtol=1e-4, atol=1e-4
    ):
        raise VectorIndexError("Embedding vectors are not normalized.")
    return np.ascontiguousarray(array, dtype=np.float32)


def _load_documents(path: Path) -> list[MaterialDocument]:
    documents: list[MaterialDocument] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise VectorIndexError(f"Blank JSONL line at {line_number}.")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise VectorIndexError(
                    f"Invalid material JSONL at line {line_number}: {exc}"
                ) from exc
            material_code = str(payload.get("id", ""))
            text = str(payload.get("text", ""))
            metadata = payload.get("metadata")
            if not material_code or not text or not isinstance(metadata, dict):
                raise VectorIndexError(
                    f"Incomplete material document at JSONL line {line_number}."
                )
            if material_code in seen:
                raise VectorIndexError(
                    f"Duplicate material code in JSONL: {material_code}"
                )
            seen.add(material_code)
            source_row = metadata.get("source_row")
            if not isinstance(source_row, int):
                raise VectorIndexError(
                    f"Invalid source_row at JSONL line {line_number}."
                )
            documents.append(
                MaterialDocument(
                    material_code=material_code,
                    text=text,
                    source_row=source_row,
                    product_category=str(metadata.get("product_category", "")),
                    metadata=dict(metadata),
                )
            )
    return documents


def _validate_store(path: Path, documents: Sequence[MaterialDocument]) -> None:
    expected = {
        document.material_code: (
            document.source_row,
            document.product_category,
            document.text,
        )
        for document in documents
    }
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(
                "SELECT material_code, source_row, product_category, embedding_text "
                "FROM materials ORDER BY rowid"
            ).fetchall()
    except sqlite3.Error as exc:
        raise VectorIndexError(f"Unable to read material SQLite store: {exc}") from exc
    if len(rows) != len(documents):
        raise VectorIndexError(
            f"SQLite/JSONL record mismatch: {len(rows)} != {len(documents)}"
        )
    for material_code, source_row, category, text in rows:
        if expected.get(str(material_code)) != (
            int(source_row),
            str(category),
            str(text),
        ):
            raise VectorIndexError(
                f"SQLite/JSONL material mismatch for code: {material_code}"
            )


def _mapping_row(position: int, document: MaterialDocument) -> dict[str, Any]:
    return {
        "position": position,
        "material_code": document.material_code,
        "source_row": document.source_row,
        "product_category": document.product_category,
        "embedding_text": document.text,
        "metadata": document.metadata,
    }


def _write_mapping(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            )
            handle.write("\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _artifact_manifest(temp_dir: Path) -> dict[str, Any]:
    mapping = {
        "all_index": ALL_INDEX_NAME,
        "all_mapping": ALL_MAPPING_NAME,
        "duvet_index": DUVET_INDEX_NAME,
        "duvet_mapping": DUVET_MAPPING_NAME,
    }
    artifacts: dict[str, Any] = {}
    for key, name in mapping.items():
        path = temp_dir / name
        artifacts[f"{key}_sha256"] = compute_sha256(path)
        artifacts[f"{key}_size"] = path.stat().st_size
    return artifacts


def _source_hashes(
    documents_path: Path,
    store_path: Path,
    manifest_path: Path,
) -> dict[str, str]:
    return {
        "material_jsonl": compute_sha256(documents_path),
        "material_store": compute_sha256(store_path),
        "material_store_manifest": compute_sha256(manifest_path),
    }


def _commit_directory(
    temp_dir: Path,
    target: Path,
    *,
    overwrite: bool,
) -> Path | None:
    if not target.exists():
        temp_dir.rename(target)
        return None
    if any(target.iterdir()) and not overwrite:
        raise VectorIndexError(
            f"Vector index output already exists; pass --overwrite: {target}"
        )
    backup = target.parent / f".{target.name}.{uuid.uuid4().hex}.backup"
    target.rename(backup)
    try:
        temp_dir.rename(target)
    except Exception:
        backup.rename(target)
        raise
    return backup


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VectorIndexError(f"Unable to read JSON file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VectorIndexError(f"Expected JSON object: {path}")
    return payload


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise VectorIndexError(f"{label} does not exist: {path}")


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _display_path(path: str | Path) -> str:
    return str(Path(path))
