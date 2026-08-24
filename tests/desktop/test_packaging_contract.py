from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_packaging_resource_manifest_is_complete() -> None:
    required = {
        "packaging/bedding_order_parser_onedir.spec",
        "packaging/bedding_order_parser_onefile.spec",
        "packaging/build_desktop.ps1",
        "packaging/create_desktop_shortcut.ps1",
        "packaging/create_local_desktop_shortcut.ps1",
        "packaging/import_business_library.ps1",
        "packaging/initialize_desktop_config.ps1",
        "packaging/verify_release.ps1",
        "packaging/version_info.txt",
        "src/bedding_order_parser/desktop/resources/app.ico",
        "src/bedding_order_parser/desktop/resources/app_icon.svg",
    }

    assert all((PROJECT_ROOT / path).is_file() for path in required)


def test_specs_are_windowed_and_do_not_bundle_business_resources() -> None:
    text = "\n".join(
        (PROJECT_ROOT / path).read_text(encoding="utf-8")
        for path in (
            "packaging/bedding_order_parser_onedir.spec",
            "packaging/bedding_order_parser_onefile.spec",
        )
    )

    assert "console=False" in text
    assert "web/templates" in text
    assert "web/static" in text
    for forbidden in (
        "material_master.sqlite3",
        "duvet_cover.faiss",
        "material_documents.jsonl",
        "material_info.csv",
        "LLM_API_KEY",
    ):
        assert forbidden not in text


def test_pyinstaller_entry_uses_the_frozen_worker_dispatcher() -> None:
    source = (PROJECT_ROOT / "packaging" / "desktop_entry.py").read_text(
        encoding="utf-8"
    )

    assert "bedding_order_parser.desktop.entrypoint" in source
    assert "bedding_order_parser.desktop.launcher" not in source


def test_architecture_does_not_migrate_to_fastapi_or_uvicorn() -> None:
    desktop_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT_ROOT / "src" / "bedding_order_parser" / "desktop"
        ).glob("*.py")
    )

    assert "FastAPI" not in desktop_sources
    assert "uvicorn" not in desktop_sources.lower()


def test_local_setup_scripts_do_not_pin_the_archived_project_path() -> None:
    scripts = {
        name: (PROJECT_ROOT / "packaging" / name).read_text(encoding="utf-8-sig")
        for name in (
            "create_local_desktop_shortcut.ps1",
            "initialize_desktop_config.ps1",
            "import_business_library.ps1",
        )
    }

    assert all(
        "D:\\AI-Learning\\Projects\\bedding-order-parser" not in text
        for text in scripts.values()
    )
    assert (
        'Join-Path $PSScriptRoot ".."'
        in scripts["create_local_desktop_shortcut.ps1"]
    )
    assert "[string]$DataDir" in scripts["initialize_desktop_config.ps1"]
    assert "PI单提取规则.xlsx" in scripts["import_business_library.ps1"]
    assert "material_info.csv" in scripts["import_business_library.ps1"]
