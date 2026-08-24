import json
import sqlite3
from pathlib import Path

import pytest

from bedding_order_parser.materials.models import EXPECTED_HEADERS
from bedding_order_parser.materials.store import MaterialStoreError, build_material_store
from bedding_order_parser.materials.loader import compute_sha256


def row(code: str = "F001", *, name: str = "被套", spec: str = "240*260CM") -> list[str]:
    return [
        code,
        name,
        spec,
        "漂白色",
        "贡缎/C80S*C80S/200*100+100/缎纹",
        "无飞边平口信封式",
        "无标",
        "交货尺寸",
        "贡缎 缎纹",
        "80S*80S",
        "T300",
        "C100",
    ]


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.write_text(
        "\ufeff" + ",".join(EXPECTED_HEADERS) + "\n" + "\n".join(",".join(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_store_builds_sqlite_and_jsonl_with_matching_counts(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    output = tmp_path / "material_store"
    write_csv(source, [row("F001"), row("F002", name="枕套")])

    result = build_material_store(source, output)

    assert result.sqlite_records == 2
    assert result.jsonl_records == 2
    assert result.sqlite_path.exists()
    assert result.jsonl_path.exists()
    assert result.manifest_path.exists()
    with sqlite3.connect(result.sqlite_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 2
        columns = connection.execute("PRAGMA table_info(materials)").fetchall()
        pk_columns = [column[1] for column in columns if column[5] == 1]
        assert pk_columns == ["material_code"]
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(materials)")}
        assert "idx_materials_product_category" in indexes
        assert "idx_materials_spec_normalized" in indexes


def test_jsonl_is_one_document_per_material_with_unique_ids(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    output = tmp_path / "material_store"
    write_csv(source, [row("F001"), row("F002", spec="200*240CM")])

    result = build_material_store(source, output)

    lines = result.jsonl_path.read_text(encoding="utf-8").splitlines()
    documents = [json.loads(line) for line in lines]
    assert len(lines) == 2
    assert "" not in lines
    assert [document["id"] for document in documents] == ["F001", "F002"]
    assert len({document["id"] for document in documents}) == 2
    assert all("metadata" in document for document in documents)
    assert all(document["id"] not in document["text"] for document in documents)


def test_sqlite_jsonl_counts_match_manifest(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    output = tmp_path / "material_store"
    write_csv(source, [row("F001")])

    result = build_material_store(source, output)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert manifest["source"]["row_count"] == 1
    assert manifest["outputs"]["sqlite_records"] == 1
    assert manifest["outputs"]["jsonl_records"] == 1
    assert manifest["category"]["duvet_cover_records"] == 1
    assert manifest["quality"]["empty_material_code"] == 0


def test_repeated_build_jsonl_is_stable_with_overwrite(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    output = tmp_path / "material_store"
    write_csv(source, [row("F001"), row("F002", spec="200*240CM")])

    first = build_material_store(source, output)
    first_text = first.jsonl_path.read_text(encoding="utf-8")
    second = build_material_store(source, output, overwrite=True)

    assert second.jsonl_path.read_text(encoding="utf-8") == first_text


def test_default_build_does_not_overwrite_existing_outputs(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    output = tmp_path / "material_store"
    write_csv(source, [row("F001")])
    build_material_store(source, output)

    with pytest.raises(MaterialStoreError, match="--overwrite"):
        build_material_store(source, output)


def test_build_failure_does_not_leave_output_directory(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    output = tmp_path / "material_store"
    write_csv(source, [row("F001"), row("F001")])

    with pytest.raises(Exception):
        build_material_store(source, output)

    assert not output.exists()


def test_source_csv_sha_does_not_change_during_store_build(tmp_path) -> None:
    source = tmp_path / "material_info.csv"
    output = tmp_path / "material_store"
    write_csv(source, [row("F001")])
    before = compute_sha256(source)

    build_material_store(source, output)

    assert compute_sha256(source) == before
