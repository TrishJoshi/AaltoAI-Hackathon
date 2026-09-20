"""Merge per-section PolicyDocument fragments into one workspace document."""

from __future__ import annotations

from src.models import PolicyDocument, PolicyKey, PolicyStatement, StatementKey
from src.review_models import PolicyReview, SectionReview, SectionStatus
from src.sections import unique_id


def section_keys(document: PolicyDocument, section_id: str) -> list[PolicyKey]:
    seen: set[str] = set()
    selected: list[PolicyKey] = []
    for statement in section_statements(document, section_id):
        for key in statement.keys:
            if key.id in seen:
                continue
            seen.add(key.id)
            selected.append(key.as_policy_key(section_id))
    return selected


def section_statements(document: PolicyDocument, section_id: str) -> list[PolicyStatement]:
    return [item for item in document.statements if item.source_section_id == section_id]


def replace_section_checks(
    document: PolicyDocument,
    section_id: str,
    statements: list[PolicyStatement],
) -> PolicyDocument:
    """Replace this section's statements; keep the rest of the document."""
    kept_statements = [
        item for item in document.statements if item.source_section_id != section_id
    ]
    merged = PolicyDocument(meta=document.meta, statements=kept_statements)
    return merge_into_document(merged, statements, section_id)


def merge_into_document(
    base: PolicyDocument,
    statements: list[PolicyStatement],
    section_id: str,
) -> PolicyDocument:
    existing_statements = list(base.statements)
    taken_stmt = {item.id for item in existing_statements}
    by_id: dict[str, StatementKey] = {}
    for statement in existing_statements:
        for key in statement.keys:
            by_id.setdefault(key.id, key)

    for statement in statements:
        nested: list[StatementKey] = []
        for key in statement.keys:
            if key.id in by_id:
                current = by_id[key.id]
                if _same_question(current.question, key.question):
                    nested.append(
                        key.model_copy(
                            update={
                                "id": current.id,
                                "question": current.question,
                                "explanation": current.explanation,
                                "value_enum": list(current.value_enum),
                                "required": current.required,
                            }
                        )
                    )
                    continue
                tagged = key.model_copy(update={"id": unique_id(key.id, set(by_id))})
            else:
                tagged = key
            nested.append(tagged)
            by_id[tagged.id] = tagged

        stmt_id = unique_id(statement.id, taken_stmt)
        tagged_stmt = statement.model_copy(
            update={
                "id": stmt_id,
                "keys": nested,
                "source_section_id": section_id,
            }
        )
        existing_statements.append(tagged_stmt)
        taken_stmt.add(stmt_id)

    return PolicyDocument(meta=base.meta, statements=existing_statements)


def prune_document_to_sections(document: PolicyDocument, section_ids: set[str]) -> PolicyDocument:
    statements = [
        item for item in document.statements if item.source_section_id in section_ids
    ]
    return document.model_copy(update={"statements": statements})


def merge_generated_document(
    base: PolicyDocument,
    incoming: PolicyDocument,
    section_id: str,
) -> PolicyDocument:
    cleared = replace_section_checks(base, section_id, [])
    return merge_into_document(cleared, incoming.statements, section_id)


def set_section_status(
    review: PolicyReview,
    section_id: str,
    status: SectionStatus,
    note: str = "",
) -> PolicyReview:
    if section_id not in review.section_map():
        raise KeyError(f"Unknown section {section_id!r}")
    if status == "covered" and not section_statements(review.document, section_id):
        raise ValueError(
            "Cannot mark a section as exhaustively covered without at least one statement."
        )
    reviews = dict(review.reviews)
    previous = reviews.get(section_id, SectionReview())
    needs_generation = False if status in {"covered", "no_restriction"} else previous.needs_generation
    reviews[section_id] = SectionReview(
        status=status,
        note=note,
        needs_generation=needs_generation,
    )
    return review.model_copy(update={"reviews": reviews})


def _same_question(left: str, right: str) -> bool:
    return " ".join(left.lower().split()) == " ".join(right.lower().split())
