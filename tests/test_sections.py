"""Section split, merge, and review-status rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models import PolicyDocument, PolicyKey, PolicyMeta, PolicyStatement
from src.policy_merge import merge_into_document, replace_section_checks, set_section_status
from src.review_models import PolicyReview, PolicySection, SectionReview, empty_document
from src.seed_review import _tag_infosec
from src.sections import split_markdown, unique_id

ROOT = Path(__file__).resolve().parents[1]
INFOSEC_MD = ROOT / "examples" / "policies" / "infosec.md"
INFOSEC_SCHEMA = ROOT / "examples" / "policies" / "infosec.schema.json"


def test_split_infosec_numbered_sections():
    sections = split_markdown(INFOSEC_MD.read_text(encoding="utf-8"))
    titles = [item.title for item in sections]
    assert titles[0] == "Preamble"
    assert "Personal data residency" in titles
    assert "Encryption at rest" in titles
    assert "Processor agreements" in titles
    assert "Privileged access" in titles
    assert len(sections) == 5


def test_split_prefers_repeated_atx_headings():
    text = "# Policy\n\nIntro\n\n## Residency\nEU only.\n\n## Encryption\nAES-256.\n"
    sections = split_markdown(text)
    titles = [item.title for item in sections]
    assert titles == ["Preamble", "Residency", "Encryption"]


def test_unique_id_suffixes_collisions():
    taken = {"data_residency"}
    assert unique_id("data_residency", taken) == "data_residency_2"


def _key(key_id: str, question: str, enum: list[str], section: str | None = None) -> PolicyKey:
    return PolicyKey(
        id=key_id,
        question=question,
        explanation="test",
        value_enum=enum,
        source_section_id=section,
    )


def _stmt(stmt_id: str, accepted: dict[str, list[str]], section: str) -> PolicyStatement:
    return PolicyStatement(
        id=stmt_id,
        description=stmt_id,
        accepted=accepted,
        source_section_id=section,
    )


def test_merge_reuses_existing_key_id():
    base = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="t", source="s"),
        keys=[_key("data_residency", "Where?", ["EU", "US"], "sec_a")],
        statements=[],
    )
    merged = merge_into_document(
        base,
        [_key("data_residency", "Where?", ["EU", "US"])],
        [_stmt("stmt_residency", {"data_residency": ["EU"]}, "sec_b")],
        "sec_b",
    )
    assert [key.id for key in merged.keys] == ["data_residency"]
    assert merged.statements[0].source_section_id == "sec_b"
    assert merged.statements[0].accepted == {"data_residency": ["EU"]}


def test_merge_renames_conflicting_key_ids():
    base = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="t", source="s"),
        keys=[_key("region", "Hosting region?", ["EU", "US"], "sec_a")],
        statements=[],
    )
    merged = merge_into_document(
        base,
        [_key("region", "Backup region?", ["EU", "US"])],
        [_stmt("stmt_backup", {"region": ["EU"]}, "sec_b")],
        "sec_b",
    )
    assert {key.id for key in merged.keys} == {"region", "region_2"}
    assert merged.statements[0].accepted == {"region_2": ["EU"]}


def test_replace_section_keeps_other_statements():
    document = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="t", source="s"),
        keys=[
            _key("data_residency", "Where?", ["EU", "US"], "sec_a"),
            _key("mfa", "MFA?", ["yes", "no"], "sec_b"),
        ],
        statements=[
            _stmt("stmt_a", {"data_residency": ["EU"]}, "sec_a"),
            _stmt("stmt_b", {"mfa": ["yes"]}, "sec_b"),
        ],
    )
    updated = replace_section_checks(
        document,
        "sec_b",
        [_key("mfa", "MFA?", ["yes", "no"], "sec_b")],
        [_stmt("stmt_b2", {"mfa": ["yes"]}, "sec_b")],
    )
    assert [item.id for item in updated.statements] == ["stmt_a", "stmt_b2"]
    assert {key.id for key in updated.keys} == {"data_residency", "mfa"}


def test_infosec_seed_tags_source_sections():
    markdown = INFOSEC_MD.read_text(encoding="utf-8")
    document = PolicyDocument.model_validate_json(INFOSEC_SCHEMA.read_text(encoding="utf-8"))
    keys, statements = _tag_infosec(document, split_markdown(markdown))
    tagged = {item.id: item.source_section_id for item in statements}
    assert tagged["stmt_data_residency"]
    assert tagged["stmt_encryption"]
    assert tagged["stmt_dpa"]
    assert tagged["stmt_mfa"]
    assert len(set(tagged.values())) == 4
    assert all(key.source_section_id for key in keys)


def _review_with_preamble() -> PolicyReview:
    preamble = PolicySection(id="sec_preamble", title="Preamble", markdown="Intro", order=0)
    body = PolicySection(id="sec_rule", title="Rule", markdown="Must use MFA.", order=1)
    document = empty_document("InfoSec", "t", "s")
    document = document.model_copy(
        update={
            "keys": [_key("mfa", "MFA?", ["yes", "no"], "sec_rule")],
            "statements": [_stmt("stmt_mfa", {"mfa": ["yes"]}, "sec_rule")],
        }
    )
    return PolicyReview(
        id="demo",
        domain="InfoSec",
        source_md="x.md",
        sections=[preamble, body],
        document=document,
        reviews={
            "sec_preamble": SectionReview(status="pending"),
            "sec_rule": SectionReview(status="pending"),
        },
    )


def test_no_restriction_does_not_require_statements():
    review = set_section_status(_review_with_preamble(), "sec_preamble", "no_restriction")
    assert review.reviews["sec_preamble"].status == "no_restriction"


def test_covered_without_statements_is_rejected():
    review = _review_with_preamble()
    with pytest.raises(ValueError, match="exhaustively covered"):
        set_section_status(review, "sec_preamble", "covered")


def test_covered_with_statements_is_allowed():
    review = set_section_status(_review_with_preamble(), "sec_rule", "covered")
    assert review.reviews["sec_rule"].status == "covered"


def test_illegal_accepted_value_still_rejected():
    with pytest.raises(ValidationError):
        PolicyDocument(
            meta=PolicyMeta(domain="InfoSec", title="t", source="s"),
            keys=[_key("mfa", "MFA?", ["yes", "no"], "sec_rule")],
            statements=[_stmt("stmt_mfa", {"mfa": ["sometimes"]}, "sec_rule")],
        )
