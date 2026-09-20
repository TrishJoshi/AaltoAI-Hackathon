"""Deterministic policy-statement iteration, enum validation, and persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from src.models import (
    PolicyDocument,
    PolicyKey,
    PolicyStatement,
    ProjectObject,
    ProjectParseResponse,
    ResultsObject,
    StatementResult,
    UnmappedAnswer,
    UserInputRequired,
)

MAX_PARSE_ATTEMPTS = 3


class ProjectParser(Protocol):
    def __call__(
        self,
        *,
        project_metadata: str,
        keys: list[PolicyKey],
        previous_invalid: dict[str, str] | None = None,
        previous_unmapped: list[UnmappedAnswer] | None = None,
    ) -> ProjectParseResponse: ...


def compare_statement(
    statement: PolicyStatement, project_answers: dict[str, str]
) -> StatementResult:
    """Compare one statement's accepted values against the project object.

    Only keys listed on the statement are considered. Fail wins over missinginfo.
    Empty is a pass for a key when ``""`` is in that key's accepted list.
    """
    missing: list[str] = []
    mismatched: list[str] = []
    details: list[str] = []

    for key_id, accepted in statement.accepted.items():
        value = project_answers.get(key_id, "")
        if value == "":
            if "" in accepted:
                continue
            missing.append(key_id)
            details.append(f"{key_id} is missing")
        elif value not in accepted:
            mismatched.append(key_id)
            details.append(f"{key_id}={value!r} not in {accepted}")

    if mismatched:
        status = "fail"
    elif missing:
        status = "missinginfo"
    else:
        status = "pass"

    if status == "pass":
        detail = "all accepted values match"
    else:
        detail = "; ".join(details)

    return StatementResult(
        statement_id=statement.id,
        description=statement.description,
        status=status,
        detail=detail,
        mismatched_keys=mismatched,
        missing_keys=missing,
    )


def validate_answers_against_enums(
    answers: dict[str, str],
    keys: list[PolicyKey],
) -> dict[str, str]:
    """Return {key_id: invalid_value} for non-empty answers outside value_enum."""
    key_map = {key.id: key for key in keys}
    invalid: dict[str, str] = {}
    for key_id, value in answers.items():
        spec = key_map.get(key_id)
        if spec is None:
            continue
        if value == "":
            continue
        if value not in spec.value_enum:
            invalid[key_id] = value
    return invalid


def build_project_object(
    *,
    keys_to_fill: list[PolicyKey],
    project_answers: dict[str, str],
    project_metadata: str,
    parse_keys: ProjectParser,
    attempts: dict[str, int],
    user_input_required: list[UserInputRequired],
    attempted_keys: set[str],
) -> None:
    """Fill missing keys via the project parser; mutate answers in place.

    Invalid enum values and unmapped answers are retried up to MAX_PARSE_ATTEMPTS
    per key. After that the key is set to empty and a user-input exception is recorded.
    """
    if not keys_to_fill:
        return

    pending = {key.id: key for key in keys_to_fill}
    previous_invalid: dict[str, str] = {}
    previous_unmapped: list[UnmappedAnswer] = []

    while pending:
        batch = [pending[key_id] for key_id in pending]
        response = parse_keys(
            project_metadata=project_metadata,
            keys=batch,
            previous_invalid=previous_invalid or None,
            previous_unmapped=previous_unmapped or None,
        )
        previous_invalid = {}
        previous_unmapped = []
        unmapped_keys = {item.key for item in response.unmapped}

        for item in response.unmapped:
            if item.key not in pending:
                continue
            spec = pending[item.key]
            attempts[item.key] = attempts.get(item.key, 0) + 1
            attempted_keys.add(item.key)
            previous_unmapped.append(item)
            if attempts[item.key] >= MAX_PARSE_ATTEMPTS:
                _give_up(
                    key=spec,
                    project_answers=project_answers,
                    pending=pending,
                    user_input_required=user_input_required,
                    proposed=item.proposed_answer,
                    reason=item.reason,
                    attempts=attempts[item.key],
                )

        for key_id, value in response.answers.items():
            if key_id not in pending or key_id in unmapped_keys:
                continue
            spec = pending[key_id]
            attempts[key_id] = attempts.get(key_id, 0) + 1
            attempted_keys.add(key_id)
            if value in spec.value_enum:
                project_answers[key_id] = value
                pending.pop(key_id, None)
            else:
                previous_invalid[key_id] = value
                if attempts[key_id] >= MAX_PARSE_ATTEMPTS:
                    _give_up(
                        key=spec,
                        project_answers=project_answers,
                        pending=pending,
                        user_input_required=user_input_required,
                        proposed=value,
                        reason=(
                            f"Project parser returned {value!r} which is not in "
                            f"{spec.value_enum} after {MAX_PARSE_ATTEMPTS} attempts"
                        ),
                        attempts=attempts[key_id],
                    )

        # Keys the parser omitted entirely still consume an attempt.
        for key_id in list(pending):
            if key_id in previous_invalid or any(u.key == key_id for u in previous_unmapped):
                continue
            if key_id in response.answers:
                continue
            spec = pending[key_id]
            attempts[key_id] = attempts.get(key_id, 0) + 1
            attempted_keys.add(key_id)
            previous_invalid[key_id] = ""
            if attempts[key_id] >= MAX_PARSE_ATTEMPTS:
                _give_up(
                    key=spec,
                    project_answers=project_answers,
                    pending=pending,
                    user_input_required=user_input_required,
                    proposed=None,
                    reason="Project parser did not return a value for this key",
                    attempts=attempts[key_id],
                )


def _give_up(
    *,
    key: PolicyKey,
    project_answers: dict[str, str],
    pending: dict[str, PolicyKey],
    user_input_required: list[UserInputRequired],
    proposed: str | None,
    reason: str,
    attempts: int,
) -> None:
    project_answers[key.id] = ""
    pending.pop(key.id, None)
    user_input_required.append(
        UserInputRequired(
            key=key.id,
            enum=list(key.value_enum),
            proposed_answer=proposed,
            reason=reason,
            attempts=attempts,
        )
    )


def iterate_policy_statements(
    policy_document: PolicyDocument,
    project_metadata: str,
    parse_keys: ProjectParser,
    existing_project_object: ProjectObject | None = None,
    project_source: str = "",
) -> tuple[ResultsObject, ProjectObject]:
    """Walk each policy statement, fill project answers, validate, compare."""
    answers = dict(existing_project_object.answers) if existing_project_object else {}
    attempted_keys = {key_id for key_id, value in answers.items() if value != ""}
    # Preserve prior empties that were already given up on (present as "").
    for key_id, value in answers.items():
        if value == "":
            attempted_keys.add(key_id)

    attempts: dict[str, int] = {}
    user_input_required: list[UserInputRequired] = []
    statement_results: list[StatementResult] = []
    key_map = policy_document.key_map()

    for statement in policy_document.statements:
        needed: list[PolicyKey] = []
        for key_id in statement.accepted:
            spec = key_map[key_id]
            if key_id not in attempted_keys:
                needed.append(spec)

        build_project_object(
            keys_to_fill=needed,
            project_answers=answers,
            project_metadata=project_metadata,
            parse_keys=parse_keys,
            attempts=attempts,
            user_input_required=user_input_required,
            attempted_keys=attempted_keys,
        )

        statement_keys = [key_map[key_id] for key_id in statement.accepted]
        still_invalid = validate_answers_against_enums(
            {k: answers.get(k, "") for k in statement.accepted},
            statement_keys,
        )
        if still_invalid:
            retry_keys = [key_map[key_id] for key_id in still_invalid]
            for key_id in still_invalid:
                answers.pop(key_id, None)
                attempted_keys.discard(key_id)
            build_project_object(
                keys_to_fill=retry_keys,
                project_answers=answers,
                project_metadata=project_metadata,
                parse_keys=parse_keys,
                attempts=attempts,
                user_input_required=user_input_required,
                attempted_keys=attempted_keys,
            )

        statement_results.append(compare_statement(statement, answers))

    project_object = ProjectObject(answers=answers)
    results = ResultsObject(
        policy_title=policy_document.meta.title,
        policy_domain=policy_document.meta.domain,
        project_source=project_source,
        results=statement_results,
        user_input_required=user_input_required,
        project_object=project_object,
    )
    return results, project_object


def persist_run(
    results: ResultsObject,
    project_object: ProjectObject,
    out_dir: Path,
    slug: str | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    name = slug or "run"
    path = out_dir / f"{stamp}_{name}.json"
    payload = {
        "results": results.model_dump(),
        "project_object": project_object.model_dump(),
        "overall_status": results.overall_status(),
        "validated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_policy_document(path: Path) -> PolicyDocument:
    return PolicyDocument.model_validate_json(path.read_text(encoding="utf-8"))


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
