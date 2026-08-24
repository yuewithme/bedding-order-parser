from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from io import BytesIO
from urllib.request import urlopen
from urllib.request import Request

from openpyxl import Workbook
from bedding_order_parser.ai_full_order.contracts import AI_BUSINESS_FIELD_NAMES
from bedding_order_parser.ai_full_order.downstream import (
    MaterialMatchOutput,
    MaterialSelection,
)
from bedding_order_parser.ai_full_order.fake_provider import FakeV2CandidateProvider
from bedding_order_parser.ai_full_order.resolution import (
    FieldDecision,
    ResolvedRecord,
    ResolutionReason,
)
from bedding_order_parser.desktop.ai_full_order_composition import (
    DesktopMaterialMatcher,
    DesktopV2DownstreamFactory,
)
from bedding_order_parser.desktop.resource_paths import ApplicationPaths, asset_root
from bedding_order_parser.desktop.runtime_identity import build_runtime_identity
from bedding_order_parser.desktop.server_controller import ServerController
from bedding_order_parser.llm.settings import LLMSettings, VOLCENGINE_ARK_PROVIDER
from bedding_order_parser.models.final_result import FinalResult, STRING_FIELD_NAMES
from bedding_order_parser.web.ai_full_order_service import AIEnhancedDependencies
from bedding_order_parser.web.services import JobService


class _ImmediateExecutor:
    def submit(self, function, *args) -> None:
        function(*args)

    def shutdown(self, **_kwargs) -> None:
        return None


class _V2OnlyProvider(FakeV2CandidateProvider):
    def __init__(self) -> None:
        super().__init__({"candidates": []})
        self.v1_calls = 0

    def extract(self, _request):
        self.v1_calls += 1
        raise AssertionError("V2 desktop job must not use V1 extraction")

    def extract_v2(self, request):
        return FakeV2CandidateProvider.extract(self, request)


class _FakeDictionaryValidator:
    def __init__(self) -> None:
        self.calls = 0

    def validate(self, records, evidence):
        self.calls += 1
        assert evidence
        return {"mode": "validation_only", "records": [{"行号": item.line_number} for item in records]}


class _FakeMaterialMatcher:
    def __init__(self) -> None:
        self.calls = 0

    def match(self, records, resolved):
        self.calls += 1
        return MaterialMatchOutput(
            selections={
                item.source_record_id: MaterialSelection(item.source_record_id, "MAT-DESKTOP", 0.5)
                for item in resolved
            },
            candidates_payload={"records": []},
            summary_payload={"accuracy_statement": "相似分数不是准确率"},
        )


def _paths(tmp_path: Path, *, with_resources: bool) -> ApplicationPaths:
    data = tmp_path / "data"
    paths = ApplicationPaths(
        asset_root=asset_root(frozen=False),
        app_root=tmp_path / "local",
        config_path=tmp_path / "local" / "config" / "app_config.json",
        task_root=tmp_path / "local" / "tasks",
        log_path=tmp_path / "local" / "logs" / "app.log",
        cache_root=tmp_path / "local" / "cache",
        state_root=tmp_path / "local" / "state",
        project_root=Path(__file__).resolve().parents[2],
        data_dir=data,
        material_store=data / "material.sqlite3",
        index_dir=data / "index",
        faiss_index=data / "index" / "duvet_cover.faiss",
        faiss_mapping=data / "index" / "duvet_cover_mapping.jsonl",
        vector_manifest=data / "index" / "vector_index_manifest.json",
        rules_path=data / "reference" / "rules.xlsx",
        styles_path=data / "reference" / "styles.xlsx",
        model_cache=data / "model",
    )
    if with_resources:
        for path in (
            paths.material_store,
            paths.faiss_index,
            paths.faiss_mapping,
            paths.vector_manifest,
            paths.rules_path,
            paths.styles_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"offline-fixture")
        paths.model_cache.mkdir(parents=True)
    return paths


def _ready_settings() -> LLMSettings:
    return LLMSettings(
        enabled=True,
        provider=VOLCENGINE_ARK_PROVIDER,
        model="offline-test-model",
        api_key="x",
        max_retries=0,
    )


def _resolved_record() -> ResolvedRecord:
    decisions = {
        field: FieldDecision(
            field_name=field,
            value="",
            selected_source="python",
            reason_code=ResolutionReason.BOTH_MISSING,
        )
        for field in AI_BUSINESS_FIELD_NAMES
    }
    return ResolvedRecord(
        record_local_id="record:1",
        source_record_id="source:1",
        scope_id="scope:1",
        line_number="1",
        decisions=decisions,
    )


def _final_record() -> FinalResult:
    values: dict[str, str | float] = {field: "" for field in STRING_FIELD_NAMES}
    values["行号"] = "1"
    values["相似分数"] = 0.0
    return FinalResult.from_mapping(values)


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PI"
    sheet.append(["", "PROFORMA INVOICE", "", "", "Unit Price (USD)"])
    sheet.append(["BUYER:", "", "", "", ""])
    sheet.append(["Synthetic Hotel", "", "", "", "Contact Person: Aaron Lee"])
    sheet.append(["Delivery date:", "2026-09-30", "", "", ""])
    sheet.append(["No.", "Item", "Size", "Specification", "Qty"])
    sheet.append(["1", "Duvet Cover", "200*240", "100% cotton white", "12"])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _upload(url: str, content: bytes) -> dict:
    boundary = "----D3B2E"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="synthetic.xlsx"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    ).encode() + content + (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="parse_mode"\r\n\r\n'
        f"ai_enhanced\r\n--{boundary}--\r\n"
    ).encode()
    request = Request(
        f"{url}/api/jobs",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urlopen(request, timeout=10) as response:
        assert response.status == 201
        return json.loads(response.read().decode("utf-8"))


def test_runtime_identity_is_short_and_path_free() -> None:
    root = Path(__file__).resolve().parents[2]
    identity = build_runtime_identity(project_root=root, asset_root=asset_root(frozen=False))

    payload = identity.to_public_dict()

    assert payload["application_version"] == "0.1.0"
    assert payload["ui_asset_version"] == "v2-ui-2026-08-05"
    assert len(payload["ui_asset_sha256_short"]) == 12
    assert "\\" not in json.dumps(payload)
    assert root.drive.casefold() not in json.dumps(payload).casefold()


def test_default_desktop_composition_is_ready_without_loading_matching_runtime(
    tmp_path: Path,
) -> None:
    runtime_modules_before = {
        name: sys.modules.get(name)
        for name in ("faiss", "sentence_transformers")
    }
    controller = ServerController(
        _paths(tmp_path, with_resources=True),
        preferred_port=0,
        health_timeout=3,
        ai_enhanced_settings=_ready_settings(),
    )
    try:
        url = controller.start()
        with urlopen(f"{url}/api/capabilities", timeout=3) as response:
            capabilities = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{url}/api/ai-enhanced/preflight", timeout=3) as response:
            preflight = json.loads(response.read().decode("utf-8"))
    finally:
        controller.stop()

    assert capabilities["runtime"]["ui_asset_version"] == "v2-ui-2026-08-05"
    assert capabilities["runtime"]["ai_contract_version"] == "2.0"
    assert preflight["v2_backend_available"] is True
    assert preflight["provider_ready"] is True
    assert {
        name: sys.modules.get(name)
        for name in runtime_modules_before
    } == runtime_modules_before


def test_default_composition_blocks_submission_when_resources_are_missing(
    tmp_path: Path,
) -> None:
    controller = ServerController(
        _paths(tmp_path, with_resources=False),
        preferred_port=0,
        health_timeout=3,
        ai_enhanced_settings=_ready_settings(),
    )
    try:
        preflight = controller.service.ai_enhanced_preflight()
    finally:
        controller.stop()

    assert preflight["v2_backend_available"] is True
    assert preflight["provider_ready"] is False
    assert preflight["unavailable_reason_code"] == "AI_DOWNSTREAM_NOT_READY"


def test_material_adapter_reuses_existing_match_entry_only_when_match_runs(
    tmp_path: Path, monkeypatch
) -> None:
    input_path = tmp_path / "synthetic.xlsx"
    input_path.write_bytes(b"PK\x03\x04synthetic")
    calls: list[Path] = []

    def fake_match_orders(orders_dir, parse_reports_dir, store_path, index_dir, **kwargs):
        calls.append(Path(orders_dir))
        assert Path(orders_dir) == Path(parse_reports_dir)
        assert Path(store_path).name == "material.sqlite3"
        assert Path(index_dir).name == "index"
        assert kwargs["top_k"] == 10
        return SimpleNamespace(
            candidates_payload={"records": []},
            summary_payload={"accuracy_statement": "参考分数不是准确率"},
        )

    import bedding_order_parser.materials.hybrid_matcher as hybrid_matcher

    monkeypatch.setattr(hybrid_matcher, "match_orders", fake_match_orders)
    matcher = DesktopMaterialMatcher(
        input_path=input_path,
        runtime_root=tmp_path / "runtime",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
    )

    result = matcher.match((_final_record(),), (_resolved_record(),))

    assert len(calls) == 1
    assert result.selections["source:1"].material_code == ""
    assert result.selections["source:1"].similarity_score == 0.0
    assert not list((tmp_path / "runtime").glob("ai-full-order-v2-*"))


def test_factory_is_only_bound_after_a_v2_job_reaches_downstream(tmp_path: Path) -> None:
    runtime_modules_before = {
        name: sys.modules.get(name)
        for name in ("faiss", "sentence_transformers")
    }
    factory = DesktopV2DownstreamFactory(_paths(tmp_path, with_resources=True))

    assert factory.is_ready() is True
    assert {
        name: sys.modules.get(name)
        for name in runtime_modules_before
    } == runtime_modules_before


def test_controller_http_with_fake_v2_dependencies_publishes_five_roles(
    tmp_path: Path,
) -> None:
    provider = _V2OnlyProvider()
    dictionary = _FakeDictionaryValidator()
    matcher = _FakeMaterialMatcher()
    service = JobService(
        tmp_path / "tasks",
        store_path=tmp_path / "material.sqlite3",
        index_dir=tmp_path / "index",
        executor=_ImmediateExecutor(),
        ai_enhanced_dependencies=AIEnhancedDependencies(
            provider=provider,
            dictionary_validator=dictionary,
            material_matcher=matcher,
        ),
        desktop_mode=True,
    )
    controller = ServerController(_paths(tmp_path, with_resources=False), preferred_port=0, service=service)
    try:
        url = controller.start()
        with urlopen(f"{url}/", timeout=3) as response:
            assert response.status == 200
        created = _upload(url, _workbook_bytes())
        with urlopen(f"{url}/api/jobs/{created['id']}", timeout=3) as response:
            job = json.loads(response.read().decode("utf-8"))
        for role in (
            "official_result",
            "parse_diagnostics",
            "dictionary_validation",
            "material_candidates",
            "material_summary",
        ):
            with urlopen(f"{url}/api/jobs/{created['id']}/artifacts/{role}/preview", timeout=3) as response:
                assert response.status == 200
    finally:
        controller.stop()

    assert job["status"] == "completed"
    assert job["ai_contract_version"] == "2.0"
    assert job["has_complete_five_results"] is True
    assert provider.extraction_call_count == 1
    assert provider.v1_calls == provider.structure_call_count == provider.network_call_count == 0
    assert dictionary.calls == matcher.calls == 1
