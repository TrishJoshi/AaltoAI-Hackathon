"""Load CLI run artifacts and curated health snapshots for the project UI."""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.health_models import (
    Contact,
    HealthSnapshot,
    HealthStatement,
    PolicyHealth,
    Remediation,
)
from src.models import PolicyDocument, ResultsObject, StatementResult

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "runs"
EXAMPLES_HEALTH = ROOT / "examples" / "health"
POLICIES_DIR = ROOT / "data" / "policies"
EXAMPLES_POLICIES = ROOT / "examples" / "policies"

RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
STAMP_RE = re.compile(r"^(\d{8}T\d{6}Z)")

DEFAULT_OWNERS: dict[str, dict] = {
    "InfoSec": {
        "organization": "Aalto Information Security Office",
        "owners": [
            Contact(
                name="Maya Koskinen",
                role="owner",
                title="Chief Information Security Officer",
                email="maya.koskinen@aalto.example",
                organization="Aalto Information Security Office",
            ),
            Contact(
                name="Jonas Niemi",
                role="member",
                title="Security analyst",
                email="jonas.niemi@aalto.example",
                organization="Aalto Information Security Office",
            ),
        ],
    },
    "GDPR": {
        "organization": "Aalto Data Protection Office",
        "owners": [
            Contact(
                name="Elena Berg",
                role="owner",
                title="Data Protection Officer",
                email="elena.berg@aalto.example",
                organization="Aalto Data Protection Office",
            ),
            Contact(
                name="Samir Haddad",
                role="member",
                title="Legal counsel, privacy",
                email="samir.haddad@aalto.example",
                organization="Legal Services",
            ),
        ],
    },
    "Cloud": {
        "organization": "Aalto IT Procurement",
        "owners": [
            Contact(
                name="Priya Nair",
                role="owner",
                title="Head of cloud procurement",
                email="priya.nair@aalto.example",
                organization="Aalto IT Procurement",
            ),
            Contact(
                name="Leo Mäkinen",
                role="member",
                title="Cloud architect",
                email="leo.makinen@aalto.example",
                organization="Aalto IT Services",
            ),
        ],
    },
}


def safe_run_id(run_id: str) -> str:
    cleaned = (run_id or "").strip()
    if cleaned.endswith(".json"):
        cleaned = cleaned[: -len(".json")]
    if not RUN_ID_RE.fullmatch(cleaned):
        raise ValueError("Invalid run id")
    return cleaned


def list_health_runs() -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for folder, kind in ((EXAMPLES_HEALTH, "demo"), (RUNS_DIR, "workspace")):
        if not folder.exists():
            continue
        paths = sorted(folder.glob("*.json"), key=lambda path: path.name, reverse=True)
        for path in paths:
            try:
                summary = summarize_run_file(path, kind)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if summary["id"] in seen:
                continue
            seen.add(summary["id"])
            items.append(summary)
    demos = [item for item in items if item["kind"] == "demo"]
    rest = sorted(
        [item for item in items if item["kind"] != "demo"],
        key=lambda item: item.get("validated_at") or item["id"],
        reverse=True,
    )
    return demos + rest


def wrap_results_object(
    results: ResultsObject,
    *,
    run_id: str,
    kind: str = "workspace",
    validated_at: str = "",
) -> HealthSnapshot:
    raw = {
        "results": results.model_dump(),
        "project_object": results.project_object.model_dump(),
        "overall_status": results.overall_status(),
        "validated_at": validated_at,
    }
    return _from_cli_run(raw, Path(run_id), kind, run_id)


def load_health_run(run_id: str) -> HealthSnapshot:
    cleaned = safe_run_id(run_id)
    for folder, kind in ((EXAMPLES_HEALTH, "demo"), (RUNS_DIR, "workspace")):
        path = folder / f"{cleaned}.json"
        if path.is_file():
            return load_run_file(path, kind, fallback_id=cleaned)
    raise FileNotFoundError(f"Health run not found: {cleaned}")


def summarize_run_file(path: Path, kind: str) -> dict:
    snapshot = load_run_file(path, kind, fallback_id=path.stem)
    totals = snapshot.totals()
    return {
        "id": snapshot.id,
        "label": snapshot.label or snapshot.project_name or snapshot.id,
        "kind": snapshot.kind,
        "project_name": snapshot.project_name,
        "project_source": snapshot.project_source,
        "validated_at": snapshot.validated_at,
        "overall_status": snapshot.overall_status,
        "policy_count": len(snapshot.policies),
        "checks_total": totals["total"],
        "checks_passed": totals["passed"],
        "checks_failed": totals["failed"],
        "checks_missing": totals["missing"],
        "pass_pct": totals["pass_pct"],
    }


def load_run_file(path: Path, kind: str, fallback_id: str) -> HealthSnapshot:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Run file must be a JSON object")
    if isinstance(raw.get("policies"), list):
        snapshot = HealthSnapshot.model_validate(raw)
        return _finalize_snapshot(snapshot, kind=kind, fallback_id=fallback_id)
    return _from_cli_run(raw, path=path, kind=kind, fallback_id=fallback_id)


def dump_snapshot(snapshot: HealthSnapshot) -> dict:
    payload = snapshot.model_dump()
    payload.update(snapshot.totals())
    payload["overall_status"] = snapshot.computed_status()
    policies = []
    for policy in snapshot.policies:
        item = policy.model_dump()
        item.update(policy.counts())
        policies.append(item)
    payload["policies"] = policies
    return payload


def _finalize_snapshot(snapshot: HealthSnapshot, kind: str, fallback_id: str) -> HealthSnapshot:
    updates: dict = {
        "overall_status": snapshot.computed_status(),
    }
    if not snapshot.id:
        updates["id"] = fallback_id
    if snapshot.kind == "workspace" and kind == "demo":
        updates["kind"] = "demo"
    elif not snapshot.kind:
        updates["kind"] = kind
    if not snapshot.label:
        updates["label"] = snapshot.project_name or snapshot.id or fallback_id
    if not snapshot.validated_at:
        updates["validated_at"] = _timestamp_from_stem(fallback_id)
    return snapshot.model_copy(update=updates)


def _from_cli_run(raw: dict, path: Path, kind: str, fallback_id: str) -> HealthSnapshot:
    inner = raw.get("results")
    if isinstance(inner, dict) and "results" in inner:
        results = ResultsObject.model_validate(inner)
    else:
        results = ResultsObject.model_validate(raw)
    answers = dict(results.project_object.answers)
    if isinstance(raw.get("project_object"), dict):
        answers.update({str(k): str(v) for k, v in raw["project_object"].get("answers", {}).items()})
    document = _find_policy_document(results)
    owners_meta = DEFAULT_OWNERS.get(results.policy_domain, {})
    owners = list(owners_meta.get("owners") or [])
    organization = str(owners_meta.get("organization") or results.policy_domain or "Policy owners")
    policy_id = _slug(results.policy_domain or path.stem)
    statements = [
        _enrich_statement(item, document, answers, owners)
        for item in results.results
    ]
    policy = PolicyHealth(
        policy_id=policy_id or "policy",
        title=results.policy_title or results.policy_domain or path.stem,
        domain=results.policy_domain or "",
        version=document.meta.version if document else "1.0",
        source=document.meta.source if document else "",
        organization=organization,
        owners=owners,
        results=statements,
    )
    project_source = results.project_source or ""
    validated_at = _normalize_validated_at(raw.get("validated_at"), path.stem)
    snapshot = HealthSnapshot(
        id=fallback_id,
        label=_cli_label(results, path.stem),
        kind="demo" if kind == "demo" else "workspace",
        project_name=_project_name(project_source, path.stem),
        project_source=project_source,
        validated_at=validated_at,
        overall_status=results.overall_status(),
        policies=[policy],
    )
    snapshot.overall_status = snapshot.computed_status()
    return snapshot


def _enrich_statement(
    item: StatementResult,
    document: PolicyDocument | None,
    answers: dict[str, str],
    owners: list[Contact],
) -> HealthStatement:
    accepted: dict[str, list[str]] = {}
    questions: dict[str, str] = {}
    statement = None
    if document:
        statement = next((row for row in document.statements if row.id == item.statement_id), None)
        key_map = document.key_map()
        if statement:
            accepted = {key: list(values) for key, values in statement.accepted.items()}
        for key_id in {*item.mismatched_keys, *item.missing_keys, *(statement.accepted if statement else {})}:
            spec = key_map.get(key_id)
            if spec:
                questions[key_id] = spec.question
    relevant_keys = list(dict.fromkeys([*item.mismatched_keys, *item.missing_keys, *accepted.keys()]))
    relevant_answers = {key: answers.get(key, "") for key in relevant_keys if key in answers or key in accepted}
    why = _build_why(item, relevant_answers, accepted, questions)
    remediation = _build_remediation(item, relevant_answers, accepted, questions, owners)
    return HealthStatement(
        statement_id=item.statement_id,
        description=item.description,
        status=item.status,
        detail=item.detail,
        mismatched_keys=list(item.mismatched_keys),
        missing_keys=list(item.missing_keys),
        answers=relevant_answers,
        accepted=accepted,
        questions=questions,
        why=why,
        remediation=remediation,
    )


def _build_why(
    item: StatementResult,
    answers: dict[str, str],
    accepted: dict[str, list[str]],
    questions: dict[str, str],
) -> str:
    if item.status == "pass":
        return item.detail or "All required answers match the accepted values for this check."
    parts: list[str] = []
    for key in item.mismatched_keys:
        label = questions.get(key, key)
        current = answers.get(key, "")
        allowed = accepted.get(key, [])
        allowed_label = ", ".join(_value_label(value) for value in allowed) or "(none listed)"
        parts.append(
            f"{label} is currently {_value_label(current)}, which is not accepted. "
            f"Accepted value(s): {allowed_label}."
        )
    for key in item.missing_keys:
        label = questions.get(key, key)
        allowed = accepted.get(key, [])
        allowed_label = ", ".join(_value_label(value) for value in allowed) or "(none listed)"
        parts.append(
            f"{label} was not answered, so this check cannot be decided. "
            f"Provide one of: {allowed_label}."
        )
    if not parts and item.detail:
        parts.append(item.detail)
    return " ".join(parts)


def _build_remediation(
    item: StatementResult,
    answers: dict[str, str],
    accepted: dict[str, list[str]],
    questions: dict[str, str],
    owners: list[Contact],
) -> Remediation:
    if item.status == "pass":
        return Remediation(
            actions=["No change required for this check."],
            steps=[],
            contacts=owners,
        )
    actions: list[str] = []
    steps: list[str] = []
    for key in item.mismatched_keys:
        label = questions.get(key, key)
        current = answers.get(key, "")
        allowed = ", ".join(_value_label(value) for value in accepted.get(key, []) if value != "")
        actions.append(f"Change “{label}” from {_value_label(current)} to {allowed or 'an accepted value'}.")
        steps.extend(
            [
                f"Confirm the current project setting for {key}: {_value_label(current)}.",
                f"Update the system or documentation so the answer becomes {allowed or 'an accepted value'}.",
            ]
        )
    for key in item.missing_keys:
        label = questions.get(key, key)
        allowed = ", ".join(_value_label(value) for value in accepted.get(key, []) if value != "")
        actions.append(f"Record an answer for “{label}” ({allowed or 'see the policy enum'}).")
        steps.append(f"Collect the missing fact for {key} from the project owner or infrastructure notes.")
    if item.status == "fail":
        steps.append("Re-run the compliance health check after the change is in production or documented.")
    else:
        steps.append("Save the missing answers and re-run the compliance health check.")
    if not actions:
        actions.append("Review the check detail and align the project with the policy’s accepted values.")
    if not steps:
        steps.append("Contact the policy owner listed below if you are unsure how to remediate.")
    return Remediation(actions=actions, steps=steps, contacts=owners)


def _find_policy_document(results: ResultsObject) -> PolicyDocument | None:
    domain = (results.policy_domain or "").strip()
    slugs = []
    if domain:
        slugs.append(_slug(domain))
        slugs.append(domain.lower())
    title = (results.policy_title or "").lower()
    if "infosec" in title or domain.lower() == "infosec":
        slugs.append("infosec")
    seen: set[str] = set()
    candidates: list[Path] = []
    for slug in slugs:
        if not slug or slug in seen:
            continue
        seen.add(slug)
        candidates.extend(
            [
                POLICIES_DIR / f"{slug}.json",
                EXAMPLES_POLICIES / f"{slug}.schema.json",
                EXAMPLES_POLICIES / f"{slug}.json",
            ]
        )
    for path in candidates:
        if path.is_file():
            try:
                return PolicyDocument.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def _cli_label(results: ResultsObject, stem: str) -> str:
    title = results.policy_title or results.policy_domain or stem
    status = results.overall_status()
    return f"{title} · {status}"


def _project_name(project_source: str, stem: str) -> str:
    if project_source:
        name = Path(project_source.replace("\\", "/")).stem
        if name:
            return name.replace("_", " ").replace("-", " ").title()
    match = re.search(r"Z_(.+)$", stem)
    if match:
        return match.group(1).replace("_", " ").title()
    return stem


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _value_label(value: str) -> str:
    return "(empty)" if value == "" else value


def _normalize_validated_at(value: object, stem: str) -> str:
    text = str(value or "").strip()
    if text:
        if re.fullmatch(r"\d{8}T\d{6}Z", text):
            return _iso_from_compact(text)
        return text
    return _timestamp_from_stem(stem)


def _timestamp_from_stem(stem: str) -> str:
    match = STAMP_RE.match(stem)
    if not match:
        return ""
    return _iso_from_compact(match.group(1))


def _iso_from_compact(stamp: str) -> str:
    if len(stamp) >= 16 and stamp[8] == "T" and stamp.endswith("Z"):
        return f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"
    return stamp
