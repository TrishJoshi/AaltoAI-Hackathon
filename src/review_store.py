"""Load and persist policy review workspaces on disk."""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.models import PolicyDocument
from src.review_models import PolicyReview, PolicySection, SectionReview, empty_document
from src.sections import slugify, split_markdown, unique_id

ROOT = Path(__file__).resolve().parents[1]
REVIEWS_DIR = ROOT / "data" / "reviews"
POLICIES_DIR = ROOT / "data" / "policies"


def reviews_dir() -> Path:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    return REVIEWS_DIR


def review_path(review_id: str) -> Path:
    return reviews_dir() / review_id


def list_reviews() -> list[PolicyReview]:
    items: list[PolicyReview] = []
    if not REVIEWS_DIR.exists():
        return items
    for path in sorted(REVIEWS_DIR.iterdir()):
        if path.is_dir() and (path / "review.json").exists():
            items.append(load_review(path.name))
    return items


def load_review(review_id: str) -> PolicyReview:
    folder = review_path(review_id)
    meta = json.loads((folder / "review.json").read_text(encoding="utf-8"))
    document = PolicyDocument.model_validate_json(
        (folder / "document.json").read_text(encoding="utf-8")
    )
    source = meta.get("source_md") or str(folder / "source.md")
    return PolicyReview(
        id=meta["id"],
        domain=meta["domain"],
        source_md=source,
        sections=[PolicySection.model_validate(item) for item in meta["sections"]],
        document=document,
        reviews={
            key: SectionReview.model_validate(value)
            for key, value in meta.get("reviews", {}).items()
        },
    )


def save_review(review: PolicyReview) -> Path:
    folder = review_path(review.id)
    folder.mkdir(parents=True, exist_ok=True)
    source_file = folder / "source.md"
    if not source_file.exists():
        original = Path(review.source_md)
        if original.is_file():
            source_file.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            source_file.write_text(
                "\n\n".join(section.markdown for section in review.sections),
                encoding="utf-8",
            )
    (folder / "document.json").write_text(
        review.document.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    payload = {
        "id": review.id,
        "domain": review.domain,
        "source_md": review.source_md,
        "sections": [section.model_dump() for section in review.sections],
        "reviews": {key: value.model_dump() for key, value in review.reviews.items()},
    }
    (folder / "review.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    return folder


def export_review(review: PolicyReview) -> Path:
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    path = POLICIES_DIR / f"{review.id}.json"
    path.write_text(review.document.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def create_review(
    *,
    domain: str,
    markdown: str,
    source_md: str,
    title: str | None = None,
    review_id: str | None = None,
    document: PolicyDocument | None = None,
) -> PolicyReview:
    sections = split_markdown(markdown)
    heading = title or (sections[0].title if sections else "Policy")
    existing = {path.name for path in reviews_dir().iterdir() if path.is_dir()} if REVIEWS_DIR.exists() else set()
    slug = unique_id(review_id or slugify(heading, fallback="review"), existing)
    doc = document or empty_document(domain=domain, title=heading, source=source_md)
    reviews = {section.id: SectionReview() for section in sections}
    review = PolicyReview(
        id=slug,
        domain=domain,
        source_md=source_md,
        sections=sections,
        document=doc,
        reviews=reviews,
    )
    folder = review_path(review.id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "source.md").write_text(markdown, encoding="utf-8")
    save_review(review)
    return review


def read_source_markdown(review: PolicyReview) -> str:
    folder_source = review_path(review.id) / "source.md"
    if folder_source.exists():
        return folder_source.read_text(encoding="utf-8")
    original = Path(review.source_md)
    if original.is_file():
        return original.read_text(encoding="utf-8")
    return "\n\n".join(section.markdown for section in review.sections)


def safe_review_id(value: str) -> str:
    cleaned = re.sub(r"^[.]{1,2}$", "", value)
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError("Invalid review id")
    return cleaned
