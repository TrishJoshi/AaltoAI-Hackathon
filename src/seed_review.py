"""Seed the GDPR and EU AI Act demo reviews (works without calling an LLM)."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.models import PolicyDocument, PolicyStatement
from src.review_models import PolicyReview, SectionReview
from src.review_store import REVIEWS_DIR, create_review, load_review, save_review
from src.sections import split_markdown

ROOT = Path(__file__).resolve().parents[1]
GDPR_MD = ROOT / "examples" / "policies" / "gdpr.md"
GDPR_SCHEMA = ROOT / "examples" / "policies" / "gdpr.schema.json"
EU_AI_MD = ROOT / "examples" / "policies" / "eu-ai-act.md"
EU_AI_SCHEMA = ROOT / "examples" / "policies" / "eu-ai-act.schema.json"
INFOSEC_MD = ROOT / "examples" / "policies" / "infosec.md"
INFOSEC_SCHEMA = ROOT / "examples" / "policies" / "infosec.schema.json"

GDPR_BINDINGS: list[tuple[tuple[str, ...], list[str]]] = [
    (("transfer", "international"), ["stmt_transfers"]),
    (("lawful", "basis"), ["stmt_lawful_basis"]),
    (("processor", "agreement", "dpa"), ["stmt_dpa"]),
    (("storage", "retention"), ["stmt_retention"]),
    (("record", "ropa", "processing"), ["stmt_ropa"]),
]

EU_AI_BINDINGS: list[tuple[tuple[str, ...], list[str]]] = [
    (("risk", "class"), ["stmt_risk_class"]),
    (("oversight",), ["stmt_human_oversight"]),
    (("logging", "output"), ["stmt_ai_logging"]),
    (("transparency", "model"), ["stmt_transparency"]),
]

INFOSEC_BINDINGS: list[tuple[tuple[str, ...], list[str]]] = [
    (("residency",), ["stmt_data_residency"]),
    (("encryption",), ["stmt_encryption"]),
    (("processor", "agreement", "dpa"), ["stmt_dpa"]),
    (("privileged", "access", "mfa"), ["stmt_mfa"]),
]


def seed_gdpr_review(*, force: bool = False) -> PolicyReview:
    folder = REVIEWS_DIR / "gdpr"
    if folder.exists() and (folder / "review.json").exists() and not force:
        return load_review("gdpr")

    markdown = GDPR_MD.read_text(encoding="utf-8")
    document = PolicyDocument.model_validate_json(GDPR_SCHEMA.read_text(encoding="utf-8"))
    sections = split_markdown(markdown)
    tagged_statements = _tag_sections(document, sections, GDPR_BINDINGS)
    seeded = document.model_copy(update={"statements": tagged_statements})
    if folder.exists():
        shutil.rmtree(folder)
    review = create_review(
        domain="GDPR",
        markdown=markdown,
        source_md=str(GDPR_MD.relative_to(ROOT)).replace("\\", "/"),
        title=document.meta.title,
        review_id="gdpr",
        document=seeded,
        filename="gdpr.md",
        needs_generation=False,
    )
    reviews = {
        section.id: SectionReview(status="pending")
        for section in review.sections
    }
    for section in review.sections:
        if "transfer" in section.id or "international" in section.id:
            reviews[section.id] = SectionReview(status="covered", needs_generation=False)
            break
    review = review.model_copy(update={"reviews": reviews})
    save_review(review)
    return review


def seed_eu_ai_act_review(*, force: bool = False) -> PolicyReview:
    folder = REVIEWS_DIR / "eu-ai-act"
    if folder.exists() and (folder / "review.json").exists() and not force:
        return load_review("eu-ai-act")

    markdown = EU_AI_MD.read_text(encoding="utf-8")
    document = PolicyDocument.model_validate_json(EU_AI_SCHEMA.read_text(encoding="utf-8"))
    sections = split_markdown(markdown)
    tagged_statements = _tag_sections(document, sections, EU_AI_BINDINGS)
    seeded = document.model_copy(update={"statements": tagged_statements})
    if folder.exists():
        shutil.rmtree(folder)
    review = create_review(
        domain="AI Act",
        markdown=markdown,
        source_md=str(EU_AI_MD.relative_to(ROOT)).replace("\\", "/"),
        title=document.meta.title,
        review_id="eu-ai-act",
        document=seeded,
        filename="eu-ai-act.md",
        needs_generation=False,
    )
    reviews = {
        section.id: SectionReview(status="pending")
        for section in review.sections
    }
    for section in review.sections:
        if "risk" in section.id or "class" in section.id:
            reviews[section.id] = SectionReview(status="covered", needs_generation=False)
            break
    review = review.model_copy(update={"reviews": reviews})
    save_review(review)
    return review


def seed_infosec_review(*, force: bool = False) -> PolicyReview:
    """Kept for InfoSec sample tests; not the default demo seed."""
    folder = REVIEWS_DIR / "infosec"
    if folder.exists() and (folder / "review.json").exists() and not force:
        return load_review("infosec")

    markdown = INFOSEC_MD.read_text(encoding="utf-8")
    document = PolicyDocument.model_validate_json(INFOSEC_SCHEMA.read_text(encoding="utf-8"))
    sections = split_markdown(markdown)
    tagged_statements = _tag_infosec(document, sections)
    seeded = document.model_copy(update={"statements": tagged_statements})
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


def _tag_infosec(document: PolicyDocument, sections: list) -> list[PolicyStatement]:
    return _tag_sections(document, sections, INFOSEC_BINDINGS)


def _tag_gdpr(document: PolicyDocument, sections: list) -> list[PolicyStatement]:
    return _tag_sections(document, sections, GDPR_BINDINGS)


def _tag_eu_ai_act(document: PolicyDocument, sections: list) -> list[PolicyStatement]:
    return _tag_sections(document, sections, EU_AI_BINDINGS)


def _tag_sections(
    document: PolicyDocument,
    sections: list,
    bindings: list[tuple[tuple[str, ...], list[str]]],
) -> list[PolicyStatement]:
    stmt_section: dict[str, str] = {}
    used: set[int] = set()
    for section in sections:
        haystack = section.title.lower()
        for index, (needles, stmt_ids) in enumerate(bindings):
            if index in used:
                continue
            if any(needle in haystack for needle in needles):
                used.add(index)
                for stmt_id in stmt_ids:
                    stmt_section[stmt_id] = section.id
                break
    return [
        item.model_copy(update={"source_section_id": stmt_section.get(item.id)})
        for item in document.statements
    ]
