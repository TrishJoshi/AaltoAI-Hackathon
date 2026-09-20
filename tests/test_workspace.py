"""Project-owner workspace listing, files, recheck, and guide chat."""

from __future__ import annotations

from pathlib import Path

from src.guide_agent import fallback_guide
from src.health_models import HealthSnapshot
from src.models import ProjectParseResponse
from src.workspace_store import (
    add_workspace_file,
    check_workspace,
    file_tree,
    list_workspaces,
    load_workspace,
    load_workspace_file,
    load_workspace_spec,
    recheck_workspace,
    safe_workspace_id,
)

ROOT = Path(__file__).resolve().parents[1]


def test_list_workspaces_includes_growthboard():
    ids = {item["id"] for item in list_workspaces()}
    assert "growthboard" in ids
    assert "campus-pilot" in ids


def test_growthboard_bundle_has_health_and_tree():
    bundle = load_workspace("growthboard")
    assert bundle["name"] == "GrowthBoard"
    assert bundle["owner"]
    assert bundle["connections"]
    assert bundle["tree"]
    assert bundle["health"]["failed"] >= 1
    assert len(bundle["health"]["policies"]) == 2
    assert bundle["health"]["policies"][0]["domain"] == "GDPR"
    assert any(item["path"] == "README.md" for item in bundle["files"])
    assert [item["path"] for item in bundle["files"]] == [
        "README.md",
        "answers.json",
        "docs/architecture.md",
        "docs/processors.md",
        "infra/hosting.md",
    ]
    answers = load_workspace_file("growthboard", "answers.json")
    assert "data_residency" in answers["content"]
    assert "human_oversight" in answers["content"]


def test_workspace_file_and_findings():
    payload = load_workspace_file("growthboard", "README.md")
    assert "us-east-1" in payload["content"]
    assert payload["findings"]
    assert any(item["statement_id"] == "stmt_transfers" for item in payload["findings"])


def test_workspace_rejects_path_traversal():
    import pytest

    with pytest.raises(ValueError):
        load_workspace_file("growthboard", "../README.md")
    with pytest.raises(ValueError):
        safe_workspace_id("../x")


def test_recheck_updates_timestamp():
    after = recheck_workspace("growthboard")["health"]
    assert after["validated_at"]
    assert after["policies"]
    assert after["total"] >= 1


def test_parse_check_builds_schema_from_project_files(monkeypatch):
    seen = {}

    def fake_parse(*, project_metadata, keys, **_kwargs):
        seen["meta"] = project_metadata
        answers = {}
        for key in keys:
            if key.id == "data_residency" and "US" in key.value_enum:
                answers[key.id] = "US"
            elif key.id == "human_oversight" and "no" in key.value_enum:
                answers[key.id] = "no"
            elif "" in key.value_enum:
                answers[key.id] = ""
            else:
                answers[key.id] = key.value_enum[0]
        return ProjectParseResponse(answers=answers)

    bundle = check_workspace("growthboard", parse=True, parse_keys=fake_parse)
    meta = seen["meta"]
    assert "us-east-1" in meta
    assert "lead scoring" in meta.lower() or "lead-scoring" in meta.lower()
    assert '"data_residency"' not in meta
    assert bundle["health"]["policies"]
    domains = {item["domain"] for item in bundle["health"]["policies"]}
    assert "GDPR" in domains
    assert "AI Act" in domains
    assert bundle["health"]["failed"] >= 1
    gdpr = next(item for item in bundle["health"]["policies"] if item["domain"] == "GDPR")
    residency = next(
        (row for row in gdpr["results"] if "data_residency" in (row.get("answers") or {})),
        None,
    )
    assert residency is not None
    assert residency["answers"]["data_residency"] == "US"


def test_campus_pilot_loads_without_run_file():
    spec = load_workspace_spec("campus-pilot")
    bundle = load_workspace("campus-pilot")
    assert bundle["name"] == "Campus Pilot"
    assert bundle["health"]["total"] >= 1
    tree = file_tree(spec["files"])
    assert any(item["name"] == "README.md" for item in tree)


def _stub_health(spec):
    return HealthSnapshot(
        id=spec.get("id") or "demo",
        project_name=spec.get("name") or "Demo",
        kind="workspace",
        validated_at="2026-09-20T00:00:00Z",
    )


def test_add_workspace_file_writes_into_explorer(tmp_path, monkeypatch):
    import json

    import src.workspace_store as store

    folder = tmp_path / "examples" / "workspaces" / "demo"
    folder.mkdir(parents=True)
    spec = {"id": "demo", "name": "Demo", "files": [], "findings": []}
    (folder / "workspace.json").write_text(json.dumps(spec), encoding="utf-8")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "WORKSPACES_DIR", tmp_path / "examples" / "workspaces")
    monkeypatch.setattr(store, "load_workspace_health", _stub_health)

    bundle = add_workspace_file("demo", "docs/notes.md", "Hosting stays in eu-north-1.\n")
    assert any(item["path"] == "docs/notes.md" for item in bundle["files"])
    assert any(item["name"] == "notes.md" for item in file_tree(bundle["files"])[0]["children"])
    saved = json.loads((folder / "workspace.json").read_text(encoding="utf-8"))
    assert saved["files"][0]["source"] == "examples/workspaces/demo/docs/notes.md"
    payload = load_workspace_file("demo", "docs/notes.md")
    assert "eu-north-1" in payload["content"]


def test_add_workspace_file_rejects_traversal_and_spec(tmp_path, monkeypatch):
    import json

    import pytest

    import src.workspace_store as store

    folder = tmp_path / "examples" / "workspaces" / "demo"
    folder.mkdir(parents=True)
    (folder / "workspace.json").write_text(json.dumps({"id": "demo", "files": []}), encoding="utf-8")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "WORKSPACES_DIR", tmp_path / "examples" / "workspaces")

    with pytest.raises(ValueError):
        add_workspace_file("demo", "../secret.md", "nope")
    with pytest.raises(ValueError):
        add_workspace_file("demo", "workspace.json", "{}")
    with pytest.raises(ValueError):
        add_workspace_file("demo", "notes.pdf", "%PDF")


def test_add_project_file_via_api(tmp_path, monkeypatch):
    import json

    import src.workspace_store as store
    from fastapi.testclient import TestClient
    from webapp.app import app

    folder = tmp_path / "examples" / "workspaces" / "demo"
    folder.mkdir(parents=True)
    (folder / "workspace.json").write_text(json.dumps({"id": "demo", "name": "Demo", "files": []}), encoding="utf-8")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "WORKSPACES_DIR", tmp_path / "examples" / "workspaces")
    monkeypatch.setattr(store, "load_workspace_health", _stub_health)

    client = TestClient(app)
    response = client.post(
        "/api/projects/demo/files",
        json={"path": "context.md", "content": "Vendor list is internal-only."},
    )
    assert response.status_code == 200
    body = response.json()
    assert any(item["path"] == "context.md" for item in body["files"])
    assert (folder / "context.md").read_text(encoding="utf-8") == "Vendor list is internal-only."


def test_fallback_guide_mentions_failure_and_contact():
    from src.health_store import dump_snapshot, load_health_run
    from src.health_models import HealthSnapshot

    snapshot = load_health_run("demo_compliance_health")
    assert isinstance(snapshot, HealthSnapshot)
    reply = fallback_guide("Why did data residency fail?", snapshot, active_file="README.md")
    assert "EU" in reply.reply or "residen" in reply.reply.lower() or "US" in reply.reply
    assert reply.suggested_prompts
    dumped = dump_snapshot(snapshot)
    assert dumped["failed"] == 5
