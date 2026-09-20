"""Project-owner workspace listing, files, recheck, and guide chat."""

from __future__ import annotations

from pathlib import Path

from src.guide_agent import fallback_guide
from src.workspace_store import (
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
    assert len(bundle["health"]["policies"]) == 3
    assert any(item["path"] == "README.md" for item in bundle["files"])


def test_workspace_file_and_findings():
    payload = load_workspace_file("growthboard", "README.md")
    assert "us-east-1" in payload["content"]
    assert payload["findings"]
    assert any(item["statement_id"] == "stmt_data_residency" for item in payload["findings"])


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


def test_campus_pilot_loads_without_run_file():
    spec = load_workspace_spec("campus-pilot")
    bundle = load_workspace("campus-pilot")
    assert bundle["name"] == "Campus Pilot"
    assert bundle["health"]["total"] >= 1
    tree = file_tree(spec["files"])
    assert any(item["name"] == "README.md" for item in tree)


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
