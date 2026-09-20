"""Compliance health snapshots: demo file plus wrapping CLI run artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.health_store import (
    dump_snapshot,
    list_health_runs,
    load_health_run,
    load_run_file,
    safe_run_id,
)
from src.models import ResultsObject, StatementResult

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "health" / "demo_compliance_health.json"
INFOSEC_SCHEMA = ROOT / "examples" / "policies" / "infosec.schema.json"


def test_demo_file_showcases_health_features():
    snapshot = load_health_run("demo_compliance_health")
    payload = dump_snapshot(snapshot)
    assert payload["id"] == "demo_compliance_health"
    assert payload["kind"] == "demo"
    assert payload["project_name"] == "GrowthBoard"
    assert payload["validated_at"]
    assert payload["overall_status"] == "fail"
    assert payload["total"] == 9
    assert payload["passed"] == 3
    assert payload["failed"] == 5
    assert payload["missing"] == 1
    assert len(payload["policies"]) == 2
    assert payload["policies"][0]["domain"] == "GDPR"

    statuses = {item["status"] for policy in payload["policies"] for item in policy["results"]}
    assert statuses == {"pass", "fail", "missinginfo"}

    failed = next(
        item
        for policy in payload["policies"]
        for item in policy["results"]
        if item["status"] == "fail"
    )
    assert failed["why"]
    assert failed["remediation"]["actions"]
    assert failed["remediation"]["steps"]
    assert any(contact["role"] == "owner" for contact in failed["remediation"]["contacts"])
    assert any(contact["email"] for contact in failed["remediation"]["contacts"])

    missing = next(
        item
        for policy in payload["policies"]
        for item in policy["results"]
        if item["status"] == "missinginfo"
    )
    assert missing["missing_keys"]
    assert missing["remediation"]["actions"]


def test_list_runs_includes_demo_first():
    runs = list_health_runs()
    assert runs
    assert runs[0]["id"] == "demo_compliance_health"
    assert runs[0]["kind"] == "demo"
    assert runs[0]["checks_failed"] == 5


def test_safe_run_id_rejects_paths():
    with pytest.raises(ValueError):
        safe_run_id("../secrets")
    with pytest.raises(ValueError):
        safe_run_id("foo/bar")
    assert safe_run_id("demo_compliance_health.json") == "demo_compliance_health"


def test_wrap_cli_run_enriches_from_policy(tmp_path: Path):
    results = ResultsObject(
        policy_title="Internal Information Security Standard v3",
        policy_domain="InfoSec",
        project_source="examples/projects/noncompliant.md",
        results=[
            StatementResult(
                statement_id="stmt_data_residency",
                description="Personal data of EU persons must be stored in the EU or EEA.",
                status="fail",
                detail="data_residency='US' not in ['EU', 'EEA']",
                mismatched_keys=["data_residency"],
            ),
            StatementResult(
                statement_id="stmt_encryption",
                description="AES-256 at rest.",
                status="pass",
                detail="all accepted values match",
            ),
        ],
        project_object={"answers": {"data_residency": "US", "encryption_at_rest": "AES-256"}},
    )
    path = tmp_path / "20260919T120500Z_noncompliant_fail.json"
    path.write_text(
        json.dumps(
            {
                "results": results.model_dump(),
                "project_object": {"answers": {"data_residency": "US", "encryption_at_rest": "AES-256"}},
                "overall_status": "fail",
            }
        ),
        encoding="utf-8",
    )
    snapshot = load_run_file(path, "workspace", path.stem)
    payload = dump_snapshot(snapshot)
    assert payload["kind"] == "workspace"
    assert payload["overall_status"] == "fail"
    assert payload["validated_at"] == "2026-09-19T12:05:00Z"
    assert payload["project_name"] == "Noncompliant"
    assert payload["failed"] == 1
    assert payload["passed"] == 1
    assert INFOSEC_SCHEMA.is_file()
    failed = payload["policies"][0]["results"][0]
    assert failed["status"] == "fail"
    assert "US" in failed["why"]
    assert failed["accepted"].get("data_residency") == ["EU", "EEA"]
    assert failed["questions"].get("data_residency")
    assert failed["remediation"]["steps"]
    assert payload["policies"][0]["organization"]
    assert payload["policies"][0]["owners"]


def test_missing_run_raises():
    with pytest.raises(FileNotFoundError):
        load_health_run("does_not_exist_run")
