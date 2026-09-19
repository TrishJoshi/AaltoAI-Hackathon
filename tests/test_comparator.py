"""Comparator tests — frozen schema, mocked project parser, no API key."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.comparator import (
    MAX_PARSE_ATTEMPTS,
    compare_statement,
    iterate_policy_statements,
    load_policy_document,
    persist_run,
)
from src.models import (
    PolicyDocument,
    PolicyKey,
    PolicyMeta,
    PolicyStatement,
    ProjectObject,
    ProjectParseResponse,
    UnmappedAnswer,
)

ROOT = Path(__file__).resolve().parents[1]
INFOSEC_SCHEMA = ROOT / "examples" / "policies" / "infosec.schema.json"


def sample_document(**overrides) -> PolicyDocument:
    data = {
        "meta": PolicyMeta(
            domain="InfoSec",
            title="Test policy",
            source="tests",
            version="1.0",
        ),
        "keys": [
            PolicyKey(
                id="data_residency",
                question="Where is data stored?",
                explanation="Region of the primary datastore.",
                value_enum=["EU", "EEA", "US", "other", ""],
            ),
            PolicyKey(
                id="encryption_at_rest",
                question="Encryption at rest?",
                explanation="Choose the algorithm used for storage encryption.",
                value_enum=["AES-256", "none", "other", ""],
            ),
            PolicyKey(
                id="mfa_for_production",
                question="MFA required?",
                explanation="Interactive production access.",
                value_enum=["yes", "no", ""],
            ),
        ],
        "statements": [
            PolicyStatement(
                id="stmt_residency",
                description="Data must stay in EU/EEA.",
                accepted={"data_residency": ["EU", "EEA"]},
            ),
            PolicyStatement(
                id="stmt_encryption",
                description="AES-256 at rest.",
                accepted={"encryption_at_rest": ["AES-256"]},
            ),
            PolicyStatement(
                id="stmt_mfa",
                description="MFA required.",
                accepted={"mfa_for_production": ["yes"]},
            ),
        ],
    }
    data.update(overrides)
    return PolicyDocument(**data)


class ScriptedParser:
    def __init__(self, responses: list[ProjectParseResponse]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, **kwargs) -> ProjectParseResponse:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError(f"Unexpected extra parser call: {kwargs}")
        return self.responses.pop(0)


def _answers_parser(answers: dict[str, str]) -> ScriptedParser:
    return ScriptedParser([ProjectParseResponse(answers=answers)])


def test_infosec_schema_loads():
    document = load_policy_document(INFOSEC_SCHEMA)
    assert document.meta.domain == "InfoSec"
    assert {key.id for key in document.keys} >= {
        "data_residency",
        "encryption_at_rest",
        "dpa_signed",
        "mfa_for_production",
    }


def test_compare_pass():
    statement = PolicyStatement(
        id="stmt_residency",
        description="EU/EEA",
        accepted={"data_residency": ["EU", "EEA"]},
    )
    result = compare_statement(statement, {"data_residency": "EU"})
    assert result.status == "pass"
    assert result.missing_keys == []
    assert result.mismatched_keys == []


def test_compare_fail():
    statement = PolicyStatement(
        id="stmt_residency",
        description="EU/EEA",
        accepted={"data_residency": ["EU", "EEA"]},
    )
    result = compare_statement(statement, {"data_residency": "US"})
    assert result.status == "fail"
    assert result.mismatched_keys == ["data_residency"]


def test_compare_missinginfo():
    statement = PolicyStatement(
        id="stmt_residency",
        description="EU/EEA",
        accepted={"data_residency": ["EU", "EEA"]},
    )
    result = compare_statement(statement, {"data_residency": ""})
    assert result.status == "missinginfo"
    assert result.missing_keys == ["data_residency"]


def test_compare_empty_is_pass_when_accepted():
    statement = PolicyStatement(
        id="stmt_optional",
        description="Optional backup",
        accepted={"backup": ["weekly", ""]},
    )
    result = compare_statement(statement, {"backup": ""})
    assert result.status == "pass"


def test_compare_fail_wins_over_missinginfo():
    statement = PolicyStatement(
        id="stmt_combo",
        description="Both",
        accepted={"data_residency": ["EU"], "encryption_at_rest": ["AES-256"]},
    )
    result = compare_statement(
        statement, {"data_residency": "US", "encryption_at_rest": ""}
    )
    assert result.status == "fail"
    assert result.mismatched_keys == ["data_residency"]
    assert result.missing_keys == ["encryption_at_rest"]


def test_iterate_all_pass_does_not_recall_filled_keys():
    document = sample_document()
    parser = ScriptedParser(
        [
            ProjectParseResponse(answers={"data_residency": "EU"}),
            ProjectParseResponse(answers={"encryption_at_rest": "AES-256"}),
            ProjectParseResponse(answers={"mfa_for_production": "yes"}),
        ]
    )
    results, project = iterate_policy_statements(
        document, "eu rds aes-256 mfa", parser
    )
    assert results.overall_status() == "pass"
    assert project.answers == {
        "data_residency": "EU",
        "encryption_at_rest": "AES-256",
        "mfa_for_production": "yes",
    }
    requested = [[key.id for key in call["keys"]] for call in parser.calls]
    assert requested == [
        ["data_residency"],
        ["encryption_at_rest"],
        ["mfa_for_production"],
    ]


def test_iterate_fail_and_missinginfo():
    document = sample_document()
    parser = _answers_parser(
        {
            "data_residency": "US",
            "encryption_at_rest": "AES-256",
            "mfa_for_production": "yes",
        }
    )
    # First statement only asks residency; remaining keys still need later calls.
    parser.responses.extend(
        [
            ProjectParseResponse(answers={"encryption_at_rest": "AES-256"}),
            ProjectParseResponse(answers={"mfa_for_production": "yes"}),
        ]
    )
    results, _ = iterate_policy_statements(document, "us-east-1", parser)
    by_id = {item.statement_id: item.status for item in results.results}
    assert by_id == {
        "stmt_residency": "fail",
        "stmt_encryption": "pass",
        "stmt_mfa": "pass",
    }
    assert results.overall_status() == "fail"


def test_existing_answers_skip_parser():
    document = sample_document()
    parser = ScriptedParser([])
    existing = ProjectObject(
        answers={
            "data_residency": "EU",
            "encryption_at_rest": "AES-256",
            "mfa_for_production": "yes",
        }
    )
    results, _ = iterate_policy_statements(
        document, "unused", parser, existing_project_object=existing
    )
    assert parser.calls == []
    assert results.overall_status() == "pass"


def test_existing_empty_answer_is_missinginfo_without_parser():
    document = sample_document()
    parser = ScriptedParser([])
    existing = ProjectObject(
        answers={
            "data_residency": "",
            "encryption_at_rest": "AES-256",
            "mfa_for_production": "yes",
        }
    )
    results, _ = iterate_policy_statements(
        document, "unknown region", parser, existing_project_object=existing
    )
    assert parser.calls == []
    by_id = {item.statement_id: item.status for item in results.results}
    assert by_id["stmt_residency"] == "missinginfo"
    assert results.overall_status() == "missinginfo"


def test_invalid_enum_retries_then_records_user_input():
    document = sample_document()
    parser = ScriptedParser(
        [ProjectParseResponse(answers={"data_residency": "Narnia"})]
        * MAX_PARSE_ATTEMPTS
        + [
            ProjectParseResponse(answers={"encryption_at_rest": "AES-256"}),
            ProjectParseResponse(answers={"mfa_for_production": "yes"}),
        ]
    )
    results, project = iterate_policy_statements(document, "fantasy hosting", parser)
    assert project.answers["data_residency"] == ""
    assert len(results.user_input_required) == 1
    item = results.user_input_required[0]
    assert item.key == "data_residency"
    assert item.attempts == MAX_PARSE_ATTEMPTS
    assert "Narnia" in (item.proposed_answer or "")
    residency_calls = [call for call in parser.calls if call["keys"][0].id == "data_residency"]
    assert len(residency_calls) == MAX_PARSE_ATTEMPTS
    assert results.results[0].status == "missinginfo"


def test_unmapped_retries_then_records_user_input():
    document = sample_document()
    unmapped = UnmappedAnswer(
        key="data_residency",
        proposed_answer="on-prem Helsinki basement",
        enum=["EU", "EEA", "US", "other", ""],
        reason="Metadata names a building, not a cloud region in the enum.",
    )
    parser = ScriptedParser(
        [ProjectParseResponse(unmapped=[unmapped])] * MAX_PARSE_ATTEMPTS
        + [
            ProjectParseResponse(answers={"encryption_at_rest": "AES-256"}),
            ProjectParseResponse(answers={"mfa_for_production": "yes"}),
        ]
    )
    results, project = iterate_policy_statements(document, "basement server", parser)
    assert project.answers["data_residency"] == ""
    assert results.user_input_required[0].proposed_answer == "on-prem Helsinki basement"
    assert results.overall_status() == "missinginfo"


def test_recovers_on_later_valid_attempt():
    document = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="Tiny", source="t", version="1"),
        keys=[
            PolicyKey(
                id="data_residency",
                question="Where?",
                explanation="Region",
                value_enum=["EU", "US", ""],
            )
        ],
        statements=[
            PolicyStatement(
                id="stmt_residency",
                description="EU only",
                accepted={"data_residency": ["EU"]},
            )
        ],
    )
    parser = ScriptedParser(
        [
            ProjectParseResponse(answers={"data_residency": "Mars"}),
            ProjectParseResponse(answers={"data_residency": "EU"}),
        ]
    )
    results, project = iterate_policy_statements(document, "eu-north-1", parser)
    assert project.answers["data_residency"] == "EU"
    assert results.user_input_required == []
    assert results.overall_status() == "pass"
    assert len(parser.calls) == 2


def test_policy_document_rejects_unknown_statement_key():
    with pytest.raises(ValidationError):
        PolicyDocument(
            meta=PolicyMeta(domain="X", title="t", source="s", version="1"),
            keys=[
                PolicyKey(
                    id="only_key",
                    question="Q",
                    explanation="E",
                    value_enum=["a"],
                )
            ],
            statements=[
                PolicyStatement(
                    id="bad",
                    description="d",
                    accepted={"missing_key": ["a"]},
                )
            ],
        )


def test_persist_run(tmp_path: Path):
    document = sample_document()
    existing = ProjectObject(
        answers={
            "data_residency": "EU",
            "encryption_at_rest": "AES-256",
            "mfa_for_production": "yes",
        }
    )
    results, project = iterate_policy_statements(
        document, "meta", ScriptedParser([]), existing_project_object=existing
    )
    path = persist_run(results, project, tmp_path, slug="demo")
    assert path.exists()
    payload = path.read_text(encoding="utf-8")
    assert "stmt_residency" in payload
    assert "\"overall_status\": \"pass\"" in payload


def test_omitted_keys_give_up_after_retries():
    document = PolicyDocument(
        meta=PolicyMeta(domain="InfoSec", title="Tiny", source="t", version="1"),
        keys=[
            PolicyKey(
                id="data_residency",
                question="Where?",
                explanation="Region",
                value_enum=["EU", "US", ""],
            )
        ],
        statements=[
            PolicyStatement(
                id="stmt_residency",
                description="EU only",
                accepted={"data_residency": ["EU"]},
            )
        ],
    )
    parser = ScriptedParser([ProjectParseResponse()] * MAX_PARSE_ATTEMPTS)
    results, project = iterate_policy_statements(document, "silent", parser)
    assert project.answers["data_residency"] == ""
    assert results.user_input_required[0].key == "data_residency"
    assert len(parser.calls) == MAX_PARSE_ATTEMPTS


def test_cli_check_offline(tmp_path: Path):
    from main import main

    rc = main(
        [
            "check",
            "--policy",
            str(INFOSEC_SCHEMA),
            "--project",
            str(ROOT / "examples" / "projects" / "compliant.md"),
            "--answers",
            str(ROOT / "examples" / "projects" / "compliant.answers.json"),
            "--out-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert list(tmp_path.glob("*.json"))


def test_offline_infosec_fixtures():
    document = load_policy_document(INFOSEC_SCHEMA)
    cases = {
        "compliant": "pass",
        "noncompliant": "fail",
        "incomplete": "missinginfo",
    }
    for name, expected in cases.items():
        answers_path = ROOT / "examples" / "projects" / f"{name}.answers.json"
        existing = ProjectObject.model_validate_json(
            answers_path.read_text(encoding="utf-8")
        )
        results, _ = iterate_policy_statements(
            document,
            "fixture",
            ScriptedParser([]),
            existing_project_object=existing,
            project_source=name,
        )
        assert results.overall_status() == expected, name
