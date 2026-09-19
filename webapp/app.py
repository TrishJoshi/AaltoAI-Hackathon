"""FastAPI app for the compliance reviewer UI."""

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

from src.models import PolicyKey, PolicyStatement
from src.policy_agent import generate_policy_document
from src.policy_merge import merge_generated_document, replace_section_checks, set_section_status
from src.review_models import PolicyReview, SectionStatus
from src.review_store import (
    create_review,
    export_review,
    list_reviews,
    load_review,
    save_review,
    safe_review_id,
)
from src.seed_review import seed_infosec_review

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_infosec_review()
    yield


app = FastAPI(title="Policy reviewer", version="0.1.0", lifespan=lifespan)


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
        "progress": review.progress(),
    }


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
    )
    return review.model_dump()


@app.post("/api/reviews/upload")
async def api_upload_review(
    domain: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    markdown = (await file.read()).decode("utf-8")
    source = file.filename or "upload.md"
    review = create_review(domain=domain, markdown=markdown, source_md=source)
    return review.model_dump()


@app.get("/api/reviews/{review_id}")
def api_get_review(review_id: str) -> dict:
    return _load(review_id).model_dump()


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
    review = review.model_copy(update={"document": document})
    save_review(review)
    return review.model_dump()


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
    review = review.model_copy(update={"document": document})
    save_review(review)
    return review.model_dump()


@app.post("/api/reviews/{review_id}/sections/{section_id}/status")
def api_set_status(review_id: str, section_id: str, body: StatusBody) -> dict:
    review = _load(review_id)
    _section_or_404(review, section_id)
    try:
        review = set_section_status(review, section_id, body.status, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_review(review)
    return review.model_dump()


@app.get("/api/reviews/{review_id}/export")
def api_export(review_id: str) -> dict:
    review = _load(review_id)
    path = export_review(review)
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/")}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
