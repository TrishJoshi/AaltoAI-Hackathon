"""FastAPI app for Poliview."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from src.generate_policies import generate_needed_policies
from src.health_store import dump_snapshot, list_health_runs, load_health_run, safe_run_id
from src.models import PolicyStatement
from src.policy_merge import replace_section_checks, set_section_status
from src.review_models import PolicyReview, SectionStatus
from src.review_store import (
    create_review,
    delete_review,
    list_reviews,
    load_review,
    save_review,
    safe_review_id,
    update_review_from_markdown,
)
from src.seed_review import seed_eu_ai_act_review, seed_gdpr_review
from src.workspace_store import (
    add_workspace_file,
    check_workspace,
    load_workspace,
    load_workspace_file,
    list_workspaces,
    safe_workspace_id,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = ROOT / "data"
POLICY_DATA_DIR = DATA_DIR / "policies"
PDF_LATER = (
    "PDF upload is not enabled yet. Convert the PDF to Markdown and upload the .md file. "
    "PDF ingestion can be added later without changing this workflow."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_gdpr_review()
    seed_eu_ai_act_review()
    yield


app = FastAPI(title="Poliview · GDPR & EU AI Act", version="0.1.0", lifespan=lifespan)


class CreateReviewJSON(BaseModel):
    domain: str
    source_md: str
    title: str | None = None


class SectionPatch(BaseModel):
    statements: list[PolicyStatement] = []


class StatusBody(BaseModel):
    status: SectionStatus
    note: str = ""


class ProjectFileBody(BaseModel):
    path: str
    content: str = ""


class FromDataBody(BaseModel):
    path: str
    domain: str = "GDPR"
    title: str = ""
    review_id: str = ""


class CheckBody(BaseModel):
    parse: bool = False


def _summarize(review: PolicyReview) -> dict:
    return {
        "id": review.id,
        "domain": review.domain,
        "title": review.document.meta.title,
        "source_md": review.source_md,
        "filename": review.filename,
        "version": review.version,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
        "progress": review.progress(),
        "dirty_section_ids": review.dirty_section_ids(),
        "sync_action": review.sync_action(),
        "versions": [item.model_dump() for item in review.versions],
    }


def _dump(review: PolicyReview) -> dict:
    payload = review.model_dump()
    payload["progress"] = review.progress()
    payload["dirty_section_ids"] = review.dirty_section_ids()
    payload["sync_action"] = review.sync_action()
    payload["title"] = review.document.meta.title
    return payload


def _load(review_id: str) -> PolicyReview:
    try:
        cleaned = safe_review_id(review_id)
        return load_review(cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Review not found") from exc


def _section_or_404(review: PolicyReview, section_id: str):
    section = review.section_map().get(section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


def list_data_markdown() -> list[dict]:
    files: list[dict] = []
    if not POLICY_DATA_DIR.is_dir():
        return files
    root = DATA_DIR.resolve()
    for path in sorted(POLICY_DATA_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        rel_data = path.resolve().relative_to(root)
        rel_repo = path.resolve().relative_to(ROOT.resolve())
        files.append(
            {
                "path": str(rel_repo).replace("\\", "/"),
                "name": path.name,
                "folder": "data/policies",
                "label": str(rel_data).replace("\\", "/"),
            }
        )
    return files


def resolve_data_markdown(rel: str) -> Path:
    cleaned = (rel or "").replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ValueError("Path must be a Markdown file under data/")
    path = (ROOT / cleaned).resolve()
    try:
        path.relative_to(DATA_DIR.resolve())
    except ValueError as exc:
        raise ValueError("Path must be a Markdown file under data/") from exc
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("Only Markdown (.md) under data/ can be loaded.")
    if not path.is_file():
        raise FileNotFoundError("Markdown file not found")
    return path


def _guess_domain(path: str, fallback: str = "GDPR") -> str:
    lower = path.lower()
    if "gdpr" in lower:
        return "GDPR"
    if "ai-act" in lower or "ai_act" in lower or "/ai." in lower:
        return "AI Act"
    if "infosec" in lower:
        return "InfoSec"
    return fallback or "GDPR"


def _read_markdown_upload(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        raise HTTPException(status_code=400, detail=PDF_LATER)
    if suffix not in {".md", ".txt", ""}:
        raise HTTPException(
            status_code=400,
            detail="Only Markdown (.md) is supported right now. PDF upload can be added later.",
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 Markdown.") from exc


@app.get("/api/reviews")
def api_list_reviews() -> dict:
    return {"reviews": [_summarize(item) for item in list_reviews()]}


@app.get("/api/data/markdown")
def api_list_data_markdown() -> dict:
    return {"root": "data/policies", "files": list_data_markdown()}


@app.post("/api/reviews/from-data")
def api_review_from_data(payload: FromDataBody) -> dict:
    try:
        path = resolve_data_markdown(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    markdown = path.read_text(encoding="utf-8")
    source = str(path.relative_to(ROOT)).replace("\\", "/")
    domain = payload.domain.strip() or _guess_domain(source)
    if payload.review_id.strip():
        review = update_review_from_markdown(_load(payload.review_id.strip()), markdown, path.name)
        return _dump(review)
    title = payload.title.strip() or path.stem.replace("-", " ").replace("_", " ")
    review = create_review(
        domain=domain,
        markdown=markdown,
        source_md=source,
        filename=path.name,
        title=title,
        review_id=None,
    )
    return _dump(review)


@app.post("/api/reviews")
def api_create_review(payload: CreateReviewJSON) -> dict:
    path = (ROOT / payload.source_md).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="source_md must be inside the repo") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Markdown file not found")
    markdown = path.read_text(encoding="utf-8")
    review = create_review(
        domain=payload.domain,
        markdown=markdown,
        source_md=payload.source_md.replace("\\", "/"),
        title=payload.title,
        filename=path.name,
    )
    return _dump(review)


@app.post("/api/reviews/upload")
async def api_upload_review(
    domain: str = Form(...),
    file: UploadFile = File(...),
    review_id: str = Form(default=""),
    title: str = Form(default=""),
) -> dict:
    filename = file.filename or "upload.md"
    markdown = _read_markdown_upload(filename, await file.read())
    if review_id.strip():
        review = update_review_from_markdown(_load(review_id.strip()), markdown, filename)
        return _dump(review)
    name = title.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the new policy a name.")
    review = create_review(
        domain=domain,
        markdown=markdown,
        source_md=filename,
        filename=filename,
        title=name,
        review_id=None,
    )
    return _dump(review)


@app.get("/api/reviews/{review_id}")
def api_get_review(review_id: str) -> dict:
    return _dump(_load(review_id))


@app.post("/api/reviews/{review_id}/generate-policies")
def api_generate_policies(review_id: str) -> dict:
    review = _load(review_id)
    if review.sync_action() == "none":
        payload = _dump(review)
        payload["generated"] = []
        payload["errors"] = []
        payload["remaining"] = 0
        return payload
    updated, generated, errors, remaining = generate_needed_policies(review)
    payload = _dump(updated)
    payload["generated"] = generated
    payload["errors"] = errors
    payload["remaining"] = remaining
    if errors and not generated:
        raise HTTPException(status_code=502, detail="; ".join(errors))
    return payload


@app.patch("/api/reviews/{review_id}/sections/{section_id}")
def api_patch_section(review_id: str, section_id: str, body: SectionPatch) -> dict:
    review = _load(review_id)
    _section_or_404(review, section_id)
    try:
        document = replace_section_checks(
            review.document,
            section_id,
            body.statements,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    reviews = dict(review.reviews)
    previous = reviews.get(section_id)
    if previous:
        reviews[section_id] = previous.model_copy(update={"needs_generation": False})
    review = review.model_copy(update={"document": document, "reviews": reviews})
    save_review(review)
    return _dump(review)


@app.post("/api/reviews/{review_id}/sections/{section_id}/status")
def api_set_status(review_id: str, section_id: str, body: StatusBody) -> dict:
    review = _load(review_id)
    _section_or_404(review, section_id)
    try:
        review = set_section_status(review, section_id, body.status, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_review(review)
    return _dump(review)


@app.delete("/api/reviews/{review_id}")
def api_delete_review(review_id: str) -> dict:
    try:
        delete_review(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Review not found") from exc
    return {"ok": True, "id": review_id}


@app.get("/api/projects")
def api_list_projects() -> dict:
    return {"projects": list_workspaces()}


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: str) -> dict:
    try:
        return load_workspace(safe_workspace_id(project_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/files")
def api_get_project_file(project_id: str, path: str = "") -> dict:
    try:
        return load_workspace_file(safe_workspace_id(project_id), path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/files")
def api_add_project_file(project_id: str, payload: ProjectFileBody) -> dict:
    try:
        return add_workspace_file(safe_workspace_id(project_id), payload.path, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/check")
def api_recheck_project(project_id: str, payload: CheckBody | None = None) -> dict:
    body = payload or CheckBody()
    try:
        return check_workspace(safe_workspace_id(project_id), parse=body.parse)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/health/runs")
def api_list_health_runs() -> dict:
    return {"runs": list_health_runs()}


@app.get("/api/health/runs/{run_id}")
def api_get_health_run(run_id: str) -> dict:
    try:
        cleaned = safe_run_id(run_id)
        snapshot = load_health_run(cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Health run not found") from exc
    return dump_snapshot(snapshot)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/")
def index() -> FileResponse:
    return _index()


@app.get("/health")
def health_page() -> FileResponse:
    return _index()


@app.get("/project")
def project_page() -> FileResponse:
    return _index()
