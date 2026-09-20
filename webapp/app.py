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
from src.guide_agent import ChatMessage, guide_project_owner
from src.health_store import dump_snapshot, list_health_runs, load_health_run, safe_run_id
from src.models import PolicyKey, PolicyStatement
from src.policy_agent import generate_policy_document
from src.policy_merge import merge_generated_document, replace_section_checks, set_section_status
from src.review_models import PolicyReview, SectionStatus
from src.review_store import (
    create_review,
    delete_review,
    export_review,
    list_reviews,
    load_review,
    load_version_markdown,
    save_review,
    safe_review_id,
    update_review_from_markdown,
)
from src.seed_review import seed_infosec_review
from src.workspace_store import (
    load_workspace,
    load_workspace_file,
    load_workspace_health,
    load_workspace_spec,
    list_workspaces,
    recheck_workspace,
    safe_workspace_id,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
PDF_LATER = (
    "PDF upload is not enabled yet. Convert the PDF to Markdown and upload the .md file. "
    "PDF ingestion can be added later without changing this workflow."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_infosec_review()
    yield


app = FastAPI(title="Poliview", version="0.1.0", lifespan=lifespan)


class CreateReviewJSON(BaseModel):
    domain: str
    source_md: str
    title: str | None = None


class SectionPatch(BaseModel):
    keys: list[PolicyKey] = []
    statements: list[PolicyStatement] = []


class StatusBody(BaseModel):
    status: SectionStatus
    note: str = ""


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


@app.get("/api/reviews/{review_id}/versions")
def api_list_versions(review_id: str) -> dict:
    review = _load(review_id)
    return {"id": review.id, "version": review.version, "versions": [item.model_dump() for item in review.versions]}


@app.get("/api/reviews/{review_id}/versions/{version}")
def api_get_version(review_id: str, version: int) -> dict:
    review = _load(review_id)
    try:
        markdown = load_version_markdown(review.id, version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    meta = next((item for item in review.versions if item.version == version), None)
    return {
        "version": version,
        "markdown": markdown,
        "meta": meta.model_dump() if meta else None,
    }


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
            body.keys,
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


@app.post("/api/reviews/{review_id}/sections/{section_id}/generate")
def api_generate_section(review_id: str, section_id: str) -> dict:
    review = _load(review_id)
    section = _section_or_404(review, section_id)
    try:
        generated = generate_policy_document(
            domain=review.domain,
            policy_text=section.markdown,
            source=review.source_md,
            source_section_id=section_id,
        )
        document = merge_generated_document(review.document, generated, section_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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


@app.get("/api/reviews/{review_id}/export")
def api_export(review_id: str) -> dict:
    review = _load(review_id)
    path = export_review(review)
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/")}


@app.delete("/api/reviews/{review_id}")
def api_delete_review(review_id: str) -> dict:
    try:
        delete_review(review_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Review not found") from exc
    return {"ok": True, "id": review_id}


class ChatBody(BaseModel):
    messages: list[ChatMessage] = []
    active_file: str = ""
    focus_policy_id: str = ""


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


@app.post("/api/projects/{project_id}/check")
def api_recheck_project(project_id: str) -> dict:
    try:
        return recheck_workspace(safe_workspace_id(project_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/chat")
def api_project_chat(project_id: str, body: ChatBody) -> dict:
    try:
        spec = load_workspace_spec(safe_workspace_id(project_id))
        snapshot = load_workspace_health(spec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    excerpt = ""
    if body.active_file:
        try:
            excerpt = load_workspace_file(spec["id"], body.active_file).get("content") or ""
        except (FileNotFoundError, ValueError):
            excerpt = ""
    reply = guide_project_owner(
        snapshot=snapshot,
        messages=body.messages,
        active_file=body.active_file,
        file_excerpt=excerpt,
        focus_policy_id=body.focus_policy_id,
    )
    return reply.model_dump()


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
