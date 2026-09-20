"""Seed the InfoSec demo review workspace (works without calling an LLM)."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.models import PolicyDocument, PolicyKey, PolicyStatement
from src.review_models import PolicyReview, SectionReview
from src.review_store import REVIEWS_DIR, create_review, load_review, save_review
from src.sections import split_markdown

ROOT = Path(__file__).resolve().parents[1]
INFOSEC_MD = ROOT / "examples" / "policies" / "infosec.md"
INFOSEC_SCHEMA = ROOT / "examples" / "policies" / "infosec.schema.json"

BINDINGS: list[tuple[tuple[str, ...], list[str], list[str]]] = [
    (("residency",), ["data_residency"], ["stmt_data_residency"]),
    (("encryption",), ["encryption_at_rest"], ["stmt_encryption"]),
    (("processor", "agreement", "dpa"), ["processes_pii", "dpa_signed"], ["stmt_dpa"]),
    (("privileged", "access", "mfa"), ["mfa_for_production"], ["stmt_mfa"]),
]


def seed_infosec_review(*, force: bool = False) -> PolicyReview:
    folder = REVIEWS_DIR / "infosec"
    if folder.exists() and (folder / "review.json").exists() and not force:
        return load_review("infosec")

    markdown = INFOSEC_MD.read_text(encoding="utf-8")
    document = PolicyDocument.model_validate_json(INFOSEC_SCHEMA.read_text(encoding="utf-8"))
    sections = split_markdown(markdown)
    tagged_keys, tagged_statements = _tag_infosec(document, sections)
    seeded = document.model_copy(update={"keys": tagged_keys, "statements": tagged_statements})
    if folder.exists():
        shutil.rmtree(folder)
    review = create_review(
        domain="InfoSec",
        markdown=markdown,
        source_md=str(INFOSEC_MD.relative_to(ROOT)).replace("\\", "/"),
        title=document.meta.title,
        review_id="infosec",
        document=seeded,
        filename="infosec.md",
        needs_generation=False,
    )
    reviews = {
        section.id: SectionReview(status="pending")
        for section in review.sections
    }
    review = review.model_copy(update={"reviews": reviews})
    save_review(review)
    return review


def _tag_infosec(
    document: PolicyDocument,
    sections: list,
) -> tuple[list[PolicyKey], list[PolicyStatement]]:
    key_section: dict[str, str] = {}
    stmt_section: dict[str, str] = {}
    used: set[int] = set()
    for section in sections:
        haystack = section.title.lower()
        for index, (needles, key_ids, stmt_ids) in enumerate(BINDINGS):
            if index in used:
                continue
            if any(needle in haystack for needle in needles):
                used.add(index)
                for key_id in key_ids:
                    key_section[key_id] = section.id
                for stmt_id in stmt_ids:
                    stmt_section[stmt_id] = section.id
                break
    keys = [
        key.model_copy(update={"source_section_id": key_section.get(key.id)})
        for key in document.keys
    ]
    statements = [
        item.model_copy(update={"source_section_id": stmt_section.get(item.id)})
        for item in document.statements
    ]
    return keys, statements
