"""Project-owner workspaces: files, connections, and bound health snapshots."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from src.comparator import iterate_policy_statements, load_policy_document
from src.health_models import HealthSnapshot, PolicyHealth
from src.health_store import dump_snapshot, load_health_run, wrap_results_object
from src.models import ProjectObject

ROOT = Path(__file__).resolve().parents[1]
WORKSPACES_DIR = ROOT / "examples" / "workspaces"
WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
FILE_PART_RE = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_WORKSPACE_FILE_BYTES = 200_000
RESERVED_WORKSPACE_FILES = {"workspace.json"}
GENERATED_SCHEMA_NAMES = {"answers.json"}
LANGUAGE_BY_SUFFIX = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".txt": "text",
    ".toml": "toml",
    ".csv": "csv",
    ".html": "html",
    ".css": "css",
}


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


def add_workspace_file(workspace_id: str, rel_path: str, content: str) -> dict:
    spec = load_workspace_spec(workspace_id)
    cleaned = clean_workspace_rel_path(rel_path)
    text = content if isinstance(content, str) else str(content or "")
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_WORKSPACE_FILE_BYTES:
        raise ValueError("File is too large (200 KB max)")
    dest = _safe_dest(spec["id"], cleaned)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    source = dest.relative_to(Path(ROOT).resolve()).as_posix()
    language = language_for_path(cleaned)
    files = spec.setdefault("files", [])
    updated = False
    for item in files:
        if item.get("path") == cleaned:
            item["source"] = source
            item["language"] = language
            updated = True
            break
    if not updated:
        files.append({"path": cleaned, "source": source, "language": language})
    _save_workspace_spec(spec)
    return load_workspace(spec["id"])


def clean_workspace_rel_path(rel_path: str) -> str:
    cleaned = (rel_path or "").replace("\\", "/").strip().lstrip("/")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("Invalid file path")
    parts = cleaned.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid file path")
    if any(not FILE_PART_RE.fullmatch(part) for part in parts):
        raise ValueError("Invalid file path")
    if parts[-1].lower() in RESERVED_WORKSPACE_FILES:
        raise ValueError("Cannot overwrite workspace metadata")
    if Path(parts[-1]).suffix.lower() == ".pdf":
        raise ValueError("PDF upload is not enabled yet. Convert to Markdown or another text file.")
    return cleaned


def language_for_path(rel_path: str) -> str:
    suffix = Path(rel_path).suffix.lower()
    return LANGUAGE_BY_SUFFIX.get(suffix, "text")


def recheck_workspace(workspace_id: str) -> dict:
    spec = load_workspace_spec(workspace_id)
    snapshot = load_workspace_health(spec)
    refreshed = _refresh_infosec_policy(spec, snapshot)
    refreshed = refreshed.model_copy(update={"validated_at": utc_now()})
    payload = dump_snapshot(refreshed)
    bundle = load_workspace(workspace_id)
    bundle["health"] = payload
    return bundle


def check_workspace(workspace_id: str, *, parse: bool = False, parse_keys=None) -> dict:
    if not parse:
        return recheck_workspace(workspace_id)
    spec = load_workspace_spec(workspace_id)
    metadata = _workspace_metadata(spec)
    documents = _load_policy_documents(spec)
    if not documents:
        raise FileNotFoundError("No policy schema is bound to this workspace")
    parser = parse_keys or _live_project_parser
    answers: dict[str, str] = {}
    policies: list[PolicyHealth] = []
    stamped = utc_now()
    for document, source in documents:
        results, project = iterate_policy_statements(
            policy_document=document,
            project_metadata=metadata,
            parse_keys=parser,
            existing_project_object=ProjectObject(answers=answers),
            project_source=source,
        )
        answers.update(project.answers)
        wrapped = wrap_results_object(
            results,
            run_id=spec["id"],
            kind="workspace",
            validated_at=stamped,
        )
        policies.extend(wrapped.policies)
    snapshot = HealthSnapshot(
        id=spec["id"],
        label=spec.get("name") or spec["id"],
        kind="workspace",
        project_name=spec.get("name") or "",
        project_source=spec["id"],
        validated_at=stamped,
        policies=policies,
    )
    snapshot = snapshot.model_copy(update={"overall_status": snapshot.computed_status()})
    bundle = load_workspace(workspace_id)
    bundle["health"] = dump_snapshot(snapshot)
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


def _save_workspace_spec(spec: dict) -> None:
    workspace_id = safe_workspace_id(spec.get("id") or "")
    path = WORKSPACES_DIR / workspace_id / "workspace.json"
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")


def _workspace_root(workspace_id: str) -> Path:
    return (WORKSPACES_DIR / safe_workspace_id(workspace_id)).resolve()


def _safe_dest(workspace_id: str, rel_path: str) -> Path:
    root = _workspace_root(workspace_id)
    dest = (root / rel_path).resolve()
    try:
        dest.relative_to(root)
    except ValueError as exc:
        raise ValueError("File is outside the workspace") from exc
    if dest.name.lower() in RESERVED_WORKSPACE_FILES:
        raise ValueError("Cannot overwrite workspace metadata")
    if dest.exists() and dest.is_dir():
        raise ValueError("Path is a directory")
    return dest


def _file_entry(spec: dict, rel_path: str) -> dict:
    cleaned = (rel_path or "").replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError("Invalid file path")
    for item in spec.get("files") or []:
        if item.get("path") == cleaned:
            return item
    raise FileNotFoundError(f"File not in workspace: {cleaned}")


def _safe_source(relative: str) -> Path:
    root = Path(ROOT).resolve()
    path = (root / relative.replace("\\", "/")).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("File is outside the repository") from exc
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path


def _is_generated_schema(rel_path: str) -> bool:
    name = Path(str(rel_path or "").replace("\\", "/")).name.lower()
    return name in GENERATED_SCHEMA_NAMES


def _workspace_metadata(spec: dict) -> str:
    parts: list[str] = []
    for item in spec.get("files") or []:
        rel = str(item.get("path") or "")
        if _is_generated_schema(rel):
            continue
        source = item.get("source") or ""
        if not source:
            continue
        try:
            text = _safe_source(source).read_text(encoding="utf-8")
        except (OSError, ValueError, FileNotFoundError):
            continue
        parts.append(f"## {rel}\n\n{text.strip()}")
    return "\n\n".join(parts).strip()


def _policy_source_paths(spec: dict) -> list[str]:
    paths: list[str] = []
    for item in spec.get("policy_paths") or []:
        rel = str(item or "").replace("\\", "/").strip()
        if rel and rel not in paths:
            paths.append(rel)
    single = str(spec.get("policy_path") or "").replace("\\", "/").strip()
    if single and single not in paths:
        paths.append(single)
    return paths


def _load_policy_documents(spec: dict) -> list[tuple]:
    documents: list[tuple] = []
    for rel in _policy_source_paths(spec):
        path = _safe_source(rel)
        documents.append((load_policy_document(path), rel))
    return documents


def _live_project_parser(**kwargs):
    from src.project_agent import parse_project_keys

    return parse_project_keys(**kwargs)


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
