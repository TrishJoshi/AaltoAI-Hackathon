"""Section split, merge, and review-status rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models import PolicyDocument, PolicyMeta, PolicyStatement, StatementKey
from src.policy_merge import merge_into_document, replace_section_checks, set_section_status
from src.review_models import PolicyReview, PolicySection, SectionReview, empty_document
from src.seed_review import _tag_eu_ai_act, _tag_gdpr, _tag_infosec
from src.sections import split_markdown, unique_id

ROOT = Path(__file__).resolve().parents[1]
INFOSEC_MD = ROOT / "examples" / "policies" / "infosec.md"
INFOSEC_SCHEMA = ROOT / "examples" / "policies" / "infosec.schema.json"
GDPR_MD = ROOT / "examples" / "policies" / "gdpr.md"
GDPR_SCHEMA = ROOT / "examples" / "policies" / "gdpr.schema.json"
EU_AI_MD = ROOT / "examples" / "policies" / "eu-ai-act.md"
EU_AI_SCHEMA = ROOT / "examples" / "policies" / "eu-ai-act.schema.json"


def test_split_infosec_numbered_sections():
    sections = split_markdown(INFOSEC_MD.read_text(encoding="utf-8"))
    titles = [item.title for item in sections]
    assert titles[0] == "Preamble"
    assert "Personal data residency" in titles
    assert "Encryption at rest" in titles
    assert "Processor agreements" in titles
    assert "Privileged access" in titles
    assert len(sections) == 5


def test_split_gdpr_numbered_sections():
    sections = split_markdown(GDPR_MD.read_text(encoding="utf-8"))
    titles = [item.title for item in sections]
    assert titles[0] == "Preamble"
    assert "International transfers" in titles
    assert "Lawful basis" in titles
    assert "Processor agreements" in titles
    assert "Storage limitation" in titles
    assert "Record of processing" in titles
    assert len(sections) == 6


def test_split_prefers_repeated_atx_headings():
    text = "# Policy\n\nIntro\n\n## Residency\nEU only.\n\n## Encryption\nAES-256.\n"
    sections = split_markdown(text)
    titles = [item.title for item in sections]
    assert titles == ["Preamble", "Residency", "Encryption"]


def test_split_gdpr_style_recitals_not_footnotes():
    text = """# REGULATIONS

Whereas:

(1) The protection of natural persons in relation to the processing of personal data is a fundamental right.

(2) The principles of, and rules on the protection of natural persons with regard to the processing of their personal data should respect their fundamental rights.

(3) Directive 95/46/EC seeks to harmonise the protection of fundamental rights.

---
(1) OJ C 229, 31.7.2012, p. 90.
(2) OJ C 391, 18.12.2012, p. 127.

(4) The processing of personal data should be designed to serve mankind.
"""
    sections = split_markdown(text)
    titles = [item.title for item in sections]
    assert titles[0] == "Preamble"
    assert titles[1].startswith("(1)")
    assert titles[2].startswith("(2)")
    assert titles[3].startswith("(3)")
    assert titles[4].startswith("(4)")
    assert len(sections) == 5
    assert "OJ C 229" not in sections[1].markdown
    assert "serve mankind" in sections[4].markdown


def test_unique_id_suffixes_collisions():
    taken = {"data_residency"}
    assert unique_id("data_residency", taken) == "data_residency_2"


def _skey(key_id: str, question: str, enum: list[str], accepted: list[str]) -> StatementKey:
    return StatementKey(
        id=key_id,
        question=question,
        explanation="test",
        value_enum=enum,
        accepted=accepted,
    )


def _stmt(stmt_id: str, keys: list[StatementKey], section: str) -> PolicyStatement:
    return PolicyStatement(
        id=stmt_id,
        description=stmt_id,
        keys=keys,
        source_section_id=section,
    )


def test_merge_reuses_existing_key_id():
    base = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="t", source="s"),
        statements=[_stmt("stmt_a", [_skey("data_residency", "Where?", ["EU", "US"], ["EU"])], "sec_a")],
    )
    merged = merge_into_document(
        base,
        [_stmt("stmt_residency", [_skey("data_residency", "Where?", ["EU", "US"], ["EU"])], "sec_b")],
        "sec_b",
    )
    assert [key.id for key in merged.keys] == ["data_residency"]
    assert merged.statements[1].source_section_id == "sec_b"
    assert merged.statements[1].accepted == {"data_residency": ["EU"]}


def test_merge_renames_conflicting_key_ids():
    base = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="t", source="s"),
        statements=[_stmt("stmt_a", [_skey("region", "Hosting region?", ["EU", "US"], ["EU"])], "sec_a")],
    )
    merged = merge_into_document(
        base,
        [_stmt("stmt_backup", [_skey("region", "Backup region?", ["EU", "US"], ["EU"])], "sec_b")],
        "sec_b",
    )
    assert {key.id for key in merged.keys} == {"region", "region_2"}
    assert merged.statements[1].accepted == {"region_2": ["EU"]}


def test_replace_section_keeps_other_statements():
    document = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="t", source="s"),
        statements=[
            _stmt("stmt_a", [_skey("data_residency", "Where?", ["EU", "US"], ["EU"])], "sec_a"),
            _stmt("stmt_b", [_skey("mfa", "MFA?", ["yes", "no"], ["yes"])], "sec_b"),
        ],
    )
    updated = replace_section_checks(
        document,
        "sec_b",
        [_stmt("stmt_b2", [_skey("mfa", "MFA?", ["yes", "no"], ["yes"])], "sec_b")],
    )
    assert [item.id for item in updated.statements] == ["stmt_a", "stmt_b2"]
    assert {key.id for key in updated.keys} == {"data_residency", "mfa"}


def test_gdpr_seed_tags_source_sections():
    markdown = GDPR_MD.read_text(encoding="utf-8")
    document = PolicyDocument.model_validate_json(GDPR_SCHEMA.read_text(encoding="utf-8"))
    statements = _tag_gdpr(document, split_markdown(markdown))
    tagged = {item.id: item.source_section_id for item in statements}
    assert tagged["stmt_transfers"]
    assert tagged["stmt_lawful_basis"]
    assert tagged["stmt_dpa"]
    assert tagged["stmt_retention"]
    assert tagged["stmt_ropa"]
    assert len(set(tagged.values())) == 5
    assert all(item.source_section_id for item in statements)


def test_eu_ai_act_seed_tags_source_sections():
    markdown = EU_AI_MD.read_text(encoding="utf-8")
    document = PolicyDocument.model_validate_json(EU_AI_SCHEMA.read_text(encoding="utf-8"))
    statements = _tag_eu_ai_act(document, split_markdown(markdown))
    tagged = {item.id: item.source_section_id for item in statements}
    assert tagged["stmt_risk_class"]
    assert tagged["stmt_human_oversight"]
    assert tagged["stmt_ai_logging"]
    assert tagged["stmt_transparency"]
    assert len(set(tagged.values())) == 4
    assert all(item.source_section_id for item in statements)


def test_infosec_seed_tags_source_sections():
    markdown = INFOSEC_MD.read_text(encoding="utf-8")
    document = PolicyDocument.model_validate_json(INFOSEC_SCHEMA.read_text(encoding="utf-8"))
    statements = _tag_infosec(document, split_markdown(markdown))
    tagged = {item.id: item.source_section_id for item in statements}
    assert tagged["stmt_data_residency"]
    assert tagged["stmt_encryption"]
    assert tagged["stmt_dpa"]
    assert tagged["stmt_mfa"]
    assert len(set(tagged.values())) == 4
    assert all(item.source_section_id for item in statements)


def _review_with_preamble() -> PolicyReview:
    preamble = PolicySection(id="sec_preamble", title="Preamble", markdown="Intro", order=0)
    body = PolicySection(id="sec_rule", title="Rule", markdown="Must use MFA.", order=1)
    document = empty_document("InfoSec", "t", "s")
    document = document.model_copy(
        update={"statements": [_stmt("stmt_mfa", [_skey("mfa", "MFA?", ["yes", "no"], ["yes"])], "sec_rule")]}
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
            statements=[_stmt("stmt_mfa", [_skey("mfa", "MFA?", ["yes", "no"], ["sometimes"])], "sec_rule")],
        )
