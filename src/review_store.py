"""Load and persist policy review workspaces on disk."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.models import PolicyDocument
from src.policy_merge import prune_document_to_sections
from src.review_models import (
    DocumentVersion,
    PolicyReview,
    PolicySection,
    SectionReview,
    empty_document,
)
from src.sections import slugify, split_markdown, unique_id

ROOT = Path(__file__).resolve().parents[1]
REVIEWS_DIR = ROOT / "data" / "reviews"
POLICIES_DIR = ROOT / "data" / "policies"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    filename = meta.get("filename") or Path(source).name
    created = meta.get("created_at") or utc_now()
    updated = meta.get("updated_at") or created
    versions = [DocumentVersion.model_validate(item) for item in meta.get("versions") or []]
    review = PolicyReview(
        id=meta["id"],
        domain=meta["domain"],
        source_md=source,
        filename=filename,
        version=int(meta.get("version") or 1),
        created_at=created,
        updated_at=updated,
        sections=[PolicySection.model_validate(item) for item in meta["sections"]],
        document=document,
        reviews={
            key: SectionReview.model_validate(value)
            for key, value in meta.get("reviews", {}).items()
        },
        versions=versions,
    )
    if not review.versions:
        review = _backfill_v1(review)
    return resplit_if_improved(review)


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
        "filename": review.filename,
        "version": review.version,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
        "sections": [section.model_dump() for section in review.sections],
        "reviews": {key: value.model_dump() for key, value in review.reviews.items()},
        "versions": [item.model_dump() for item in review.versions],
    }
    (folder / "review.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    if review.document.keys or review.document.statements:
        export_review(review)
    return folder


def export_review(review: PolicyReview) -> Path:
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    path = POLICIES_DIR / f"{review.id}.json"
    path.write_text(review.document.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def delete_review(review_id: str) -> None:
    cleaned = safe_review_id(review_id)
    folder = review_path(cleaned)
    if not folder.exists() or not (folder / "review.json").exists():
        raise FileNotFoundError("Review not found")
    shutil.rmtree(folder)
    exported = POLICIES_DIR / f"{cleaned}.json"
    if exported.exists():
        exported.unlink()


def create_review(
    *,
    domain: str,
    markdown: str,
    source_md: str,
    title: str | None = None,
    review_id: str | None = None,
    document: PolicyDocument | None = None,
    filename: str | None = None,
    needs_generation: bool = True,
) -> PolicyReview:
    sections = split_markdown(markdown)
    heading = title or (sections[0].title if sections else "Policy")
    existing = {path.name for path in reviews_dir().iterdir() if path.is_dir()} if REVIEWS_DIR.exists() else set()
    slug = unique_id(review_id or slugify(heading, fallback="review"), existing)
    stamp = utc_now()
    file_name = filename or Path(source_md).name
    doc = document or empty_document(domain=domain, title=heading, source=source_md)
    reviews = {
        section.id: SectionReview(
            needs_generation=needs_generation and not _is_preamble(section)
        )
        for section in sections
    }
    version = DocumentVersion(
        version=1,
        created_at=stamp,
        filename=file_name,
        action="created",
        section_ids=[section.id for section in sections],
        changed_section_ids=[
            section.id for section in sections if reviews[section.id].needs_generation
        ],
    )
    review = PolicyReview(
        id=slug,
        domain=domain,
        source_md=source_md,
        filename=file_name,
        version=1,
        created_at=stamp,
        updated_at=stamp,
        sections=sections,
        document=doc,
        reviews=reviews,
        versions=[version],
    )
    folder = review_path(review.id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "source.md").write_text(markdown, encoding="utf-8")
    save_review(review)
    snapshot_version(review)
    return review


def update_review_from_markdown(
    review: PolicyReview,
    markdown: str,
    filename: str,
) -> PolicyReview:
    new_sections = split_markdown(markdown)
    new_reviews, changed = _remap_section_reviews(review, new_sections)
    stamp = utc_now()
    next_version = review.version + 1
    versions = list(review.versions)
    versions.append(
        DocumentVersion(
            version=next_version,
            created_at=stamp,
            filename=filename,
            action="updated",
            section_ids=[section.id for section in new_sections],
            changed_section_ids=changed,
        )
    )
    new_ids = {section.id for section in new_sections}
    document = prune_document_to_sections(review.document, new_ids)
    meta = review.document.meta.model_copy(update={"version": str(next_version), "source": filename})
    document = document.model_copy(update={"meta": meta})
    updated = review.model_copy(
        update={
            "source_md": filename,
            "filename": filename,
            "version": next_version,
            "updated_at": stamp,
            "sections": new_sections,
            "reviews": new_reviews,
            "document": document,
            "versions": versions,
        }
    )
    folder = review_path(review.id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "source.md").write_text(markdown, encoding="utf-8")
    save_review(updated)
    snapshot_version(updated)
    return updated


def resplit_if_improved(review: PolicyReview) -> PolicyReview:
    """Re-run section splitting when the source clearly has more blocks than we stored."""
    markdown = read_source_markdown(review)
    new_sections = split_markdown(markdown)
    if len(new_sections) < max(len(review.sections) + 2, 5):
        return review
    if len(new_sections) <= len(review.sections):
        return review
    new_reviews, _changed = _remap_section_reviews(review, new_sections)
    new_ids = {section.id for section in new_sections}
    document = prune_document_to_sections(review.document, new_ids)
    updated = review.model_copy(
        update={
            "sections": new_sections,
            "reviews": new_reviews,
            "document": document,
            "updated_at": utc_now(),
        }
    )
    save_review(updated)
    return updated


def _remap_section_reviews(
    review: PolicyReview,
    new_sections: list,
) -> tuple[dict[str, SectionReview], list[str]]:
    old_sections = review.section_map()
    old_reviews = dict(review.reviews)
    changed: list[str] = []
    new_reviews: dict[str, SectionReview] = {}
    for section in new_sections:
        previous_section = old_sections.get(section.id)
        previous = old_reviews.get(section.id, SectionReview())
        if previous_section is None:
            new_reviews[section.id] = SectionReview(
                status="pending",
                needs_generation=not _is_preamble(section),
            )
            if new_reviews[section.id].needs_generation:
                changed.append(section.id)
        elif previous_section.markdown.strip() != section.markdown.strip():
            new_reviews[section.id] = SectionReview(
                status="pending",
                needs_generation=not _is_preamble(section),
                note=previous.note,
            )
            if new_reviews[section.id].needs_generation:
                changed.append(section.id)
        else:
            new_reviews[section.id] = previous
    return new_reviews, changed


def snapshot_version(review: PolicyReview) -> Path:
    folder = review_path(review.id) / "versions" / str(review.version)
    folder.mkdir(parents=True, exist_ok=True)
    source = review_path(review.id) / "source.md"
    document = review_path(review.id) / "document.json"
    if source.exists():
        shutil.copyfile(source, folder / "source.md")
    if document.exists():
        shutil.copyfile(document, folder / "document.json")
    return folder


def load_version_markdown(review_id: str, version: int) -> str:
    path = review_path(review_id) / "versions" / str(version) / "source.md"
    if not path.exists():
        raise FileNotFoundError(f"Version {version} not found")
    return path.read_text(encoding="utf-8")


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


def _is_preamble(section: PolicySection) -> bool:
    return section.title.strip().lower() == "preamble"


def _backfill_v1(review: PolicyReview) -> PolicyReview:
    stamp = review.created_at or utc_now()
    version = DocumentVersion(
        version=review.version or 1,
        created_at=stamp,
        filename=review.filename or Path(review.source_md).name,
        action="created",
        section_ids=[section.id for section in review.sections],
    )
    filled = review.model_copy(
        update={
            "filename": review.filename or Path(review.source_md).name,
            "created_at": stamp,
            "updated_at": review.updated_at or stamp,
            "versions": [version],
        }
    )
    save_review(filled)
    snapshot_version(filled)
    return filled
