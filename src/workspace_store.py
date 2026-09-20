"""Project-owner workspaces: files, connections, and bound health snapshots."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from src.comparator import iterate_policy_statements, load_policy_document
from src.health_models import HealthSnapshot, PolicyHealth
from src.health_store import dump_snapshot, load_health_run, wrap_results_object
from src.models import ProjectObject, ProjectParseResponse

ROOT = Path(__file__).resolve().parents[1]
WORKSPACES_DIR = ROOT / "examples" / "workspaces"
WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_workspace_id(workspace_id: str) -> str:
    cleaned = (workspace_id or "").strip()
    if not WORKSPACE_ID_RE.fullmatch(cleaned):
        raise ValueError("Invalid workspace id")
    return cleaned


def list_workspaces() -> list[dict]:
    items: list[dict] = []
    if not WORKSPACES_DIR.exists():
        return items
    for path in sorted(WORKSPACES_DIR.glob("*/workspace.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        workspace_id = spec.get("id") or path.parent.name
        items.append(
            {
                "id": workspace_id,
                "name": spec.get("name") or workspace_id,
                "description": spec.get("description") or "",
                "owner": spec.get("owner") or "",
                "health_run_id": spec.get("health_run_id") or "",
            }
        )
    return items


def load_workspace_spec(workspace_id: str) -> dict:
    cleaned = safe_workspace_id(workspace_id)
    path = WORKSPACES_DIR / cleaned / "workspace.json"
    if not path.is_file():
        raise FileNotFoundError(f"Workspace not found: {cleaned}")
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["id"] = spec.get("id") or cleaned
    return spec


def load_workspace(workspace_id: str) -> dict:
    spec = load_workspace_spec(workspace_id)
    snapshot = load_workspace_health(spec)
    payload = dump_snapshot(snapshot)
    files = spec.get("files") or []
    return {
        "id": spec["id"],
        "name": spec.get("name") or spec["id"],
        "description": spec.get("description") or "",
        "owner": spec.get("owner") or "",
        "owner_email": spec.get("owner_email") or "",
        "health_run_id": spec.get("health_run_id") or "",
        "connections": spec.get("connections") or [],
        "files": [{"path": item["path"], "language": item.get("language") or "text"} for item in files],
        "tree": file_tree(files),
        "findings": spec.get("findings") or [],
        "health": payload,
        "workspaces": list_workspaces(),
    }


def load_workspace_file(workspace_id: str, rel_path: str) -> dict:
    spec = load_workspace_spec(workspace_id)
    entry = _file_entry(spec, rel_path)
    source = _safe_source(entry["source"])
    text = source.read_text(encoding="utf-8")
    findings = [item for item in spec.get("findings") or [] if item.get("path") == entry["path"]]
    return {
        "path": entry["path"],
        "language": entry.get("language") or "text",
        "content": text,
        "findings": findings,
    }


def recheck_workspace(workspace_id: str) -> dict:
    spec = load_workspace_spec(workspace_id)
    snapshot = load_workspace_health(spec)
    refreshed = _refresh_infosec_policy(spec, snapshot)
    refreshed = refreshed.model_copy(update={"validated_at": utc_now()})
    payload = dump_snapshot(refreshed)
    bundle = load_workspace(workspace_id)
    bundle["health"] = payload
    return bundle


def _refresh_infosec_policy(spec: dict, snapshot: HealthSnapshot) -> HealthSnapshot:
    answers_path = spec.get("answers_path")
    policy_path = spec.get("policy_path")
    if not answers_path or not policy_path:
        return snapshot
    try:
        document = load_policy_document(_safe_source(policy_path))
        answers = _load_answers(_safe_source(answers_path))
    except (OSError, ValueError, FileNotFoundError):
        return snapshot

    def parse_keys(**_kwargs):
        return ProjectParseResponse()

    results, _project = iterate_policy_statements(
        policy_document=document,
        project_metadata="",
        parse_keys=parse_keys,
        existing_project_object=answers,
        project_source=str(spec.get("answers_path") or ""),
    )
    fresh = wrap_results_object(results, run_id=spec["id"], kind="workspace", validated_at=utc_now())
    if not fresh.policies:
        return snapshot
    replacement = fresh.policies[0]
    policies: list[PolicyHealth] = []
    replaced = False
    for policy in snapshot.policies:
        if policy.domain.lower() == replacement.domain.lower() or policy.policy_id == replacement.policy_id:
            policies.append(replacement)
            replaced = True
        else:
            policies.append(policy)
    if not replaced:
        policies.insert(0, replacement)
    return snapshot.model_copy(update={"policies": policies, "project_name": snapshot.project_name or spec.get("name") or ""})


def load_workspace_health(spec: dict) -> HealthSnapshot:
    run_id = spec.get("health_run_id") or ""
    if run_id:
        try:
            snapshot = load_health_run(run_id)
            if not snapshot.project_name:
                snapshot = snapshot.model_copy(update={"project_name": spec.get("name") or snapshot.project_name})
            return snapshot
        except FileNotFoundError:
            pass
    return _snapshot_from_answers(spec)


def file_tree(files: list[dict]) -> list[dict]:
    root: dict = {"name": "", "path": "", "kind": "dir", "children": {}}
    for item in files:
        parts = str(item["path"]).replace("\\", "/").split("/")
        node = root
        walked: list[str] = []
        for index, part in enumerate(parts):
            walked.append(part)
            current = "/".join(walked)
            children = node["children"]
            if part not in children:
                children[part] = {
                    "name": part,
                    "path": current,
                    "kind": "file" if index == len(parts) - 1 else "dir",
                    "children": {},
                }
            node = children[part]
    return _tree_values(root["children"])


def _tree_values(children: dict) -> list[dict]:
    items = []
    for child in sorted(children.values(), key=lambda item: (item["kind"] != "dir", item["name"].lower())):
        entry = {
            "name": child["name"],
            "path": child["path"],
            "kind": child["kind"],
        }
        if child["kind"] == "dir":
            entry["children"] = _tree_values(child["children"])
        items.append(entry)
    return items


def _file_entry(spec: dict, rel_path: str) -> dict:
    cleaned = (rel_path or "").replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError("Invalid file path")
    for item in spec.get("files") or []:
        if item.get("path") == cleaned:
            return item
    raise FileNotFoundError(f"File not in workspace: {cleaned}")


def _safe_source(relative: str) -> Path:
    path = (ROOT / relative.replace("\\", "/")).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError("File is outside the repository") from exc
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path


def _load_answers(path: Path) -> ProjectObject:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "answers" in raw:
        return ProjectObject.model_validate(raw)
    if isinstance(raw, dict):
        return ProjectObject(answers={str(k): str(v) for k, v in raw.items()})
    raise ValueError("Answers file must be a JSON object")


def _snapshot_from_answers(spec: dict) -> HealthSnapshot:
    answers_path = spec.get("answers_path")
    policy_path = spec.get("policy_path")
    if not answers_path or not policy_path:
        raise FileNotFoundError("No health snapshot or answers available")
    document = load_policy_document(_safe_source(policy_path))
    answers = _load_answers(_safe_source(answers_path))

    def parse_keys(**_kwargs):
        return ProjectParseResponse()

    results, _project = iterate_policy_statements(
        policy_document=document,
        project_metadata="",
        parse_keys=parse_keys,
        existing_project_object=answers,
        project_source=str(answers_path),
    )
    snapshot = wrap_results_object(
        results,
        run_id=spec["id"],
        kind="workspace",
        validated_at=utc_now(),
    )
    return snapshot.model_copy(update={"project_name": spec.get("name") or snapshot.project_name})
