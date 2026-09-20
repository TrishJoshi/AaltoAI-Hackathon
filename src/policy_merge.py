"""Merge per-section PolicyDocument fragments into one workspace document."""

from __future__ import annotations

from src.models import PolicyDocument, PolicyKey, PolicyStatement
from src.review_models import PolicyReview, SectionReview, SectionStatus
from src.sections import unique_id


def section_keys(document: PolicyDocument, section_id: str) -> list[PolicyKey]:
    referenced = set()
    for statement in section_statements(document, section_id):
        referenced.update(statement.accepted)
    selected: list[PolicyKey] = []
    seen: set[str] = set()
    for key in document.keys:
        if key.id in seen:
            continue
        if key.source_section_id == section_id or key.id in referenced:
            selected.append(key)
            seen.add(key.id)
    return selected


def section_statements(document: PolicyDocument, section_id: str) -> list[PolicyStatement]:
    return [item for item in document.statements if item.source_section_id == section_id]


def replace_section_checks(
    document: PolicyDocument,
    section_id: str,
    keys: list[PolicyKey],
    statements: list[PolicyStatement],
) -> PolicyDocument:
    """Replace this section's statements and section-owned keys; keep the rest."""
    kept_statements = [
        item for item in document.statements if item.source_section_id != section_id
    ]
    referenced_elsewhere = {
        key_id for item in kept_statements for key_id in item.accepted
    }
    kept_keys = [
        key
        for key in document.keys
        if key.source_section_id != section_id or key.id in referenced_elsewhere
    ]
    merged = PolicyDocument(
        meta=document.meta,
        keys=kept_keys,
        statements=kept_statements,
    )
    return merge_into_document(merged, keys, statements, section_id)


def merge_into_document(
    base: PolicyDocument,
    keys: list[PolicyKey],
    statements: list[PolicyStatement],
    section_id: str,
) -> PolicyDocument:
    existing_keys = list(base.keys)
    by_id = {key.id: index for index, key in enumerate(existing_keys)}
    remapped: dict[str, str] = {}

    for key in keys:
        tagged = key.model_copy(
            update={"source_section_id": key.source_section_id or section_id}
        )
        if tagged.id in by_id:
            current = existing_keys[by_id[tagged.id]]
            if _same_question(current.question, tagged.question):
                remapped[key.id] = current.id
                continue
            new_id = unique_id(tagged.id, set(by_id))
            remapped[key.id] = new_id
            tagged = tagged.model_copy(update={"id": new_id})
        else:
            remapped[key.id] = tagged.id
        existing_keys.append(tagged)
        by_id[tagged.id] = len(existing_keys) - 1

    existing_statements = list(base.statements)
    taken_stmt = {item.id for item in existing_statements}
    for statement in statements:
        accepted = {
            remapped.get(key_id, key_id): list(values)
            for key_id, values in statement.accepted.items()
        }
        stmt_id = unique_id(statement.id, taken_stmt)
        tagged = statement.model_copy(
            update={
                "id": stmt_id,
                "accepted": accepted,
                "source_section_id": section_id,
            }
        )
        existing_statements.append(tagged)
        taken_stmt.add(stmt_id)

    return PolicyDocument(
        meta=base.meta,
        keys=existing_keys,
        statements=existing_statements,
    )


def prune_document_to_sections(document: PolicyDocument, section_ids: set[str]) -> PolicyDocument:
    statements = [
        item for item in document.statements if item.source_section_id in section_ids
    ]
    referenced = {key_id for item in statements for key_id in item.accepted}
    keys = [
        key
        for key in document.keys
        if key.id in referenced or (key.source_section_id or "") in section_ids
    ]
    return document.model_copy(update={"keys": keys, "statements": statements})


def merge_generated_document(
    base: PolicyDocument,
    incoming: PolicyDocument,
    section_id: str,
) -> PolicyDocument:
    cleared = replace_section_checks(base, section_id, [], [])
    return merge_into_document(cleared, incoming.keys, incoming.statements, section_id)


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
