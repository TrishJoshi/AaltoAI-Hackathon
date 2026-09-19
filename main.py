"""CLI for generating policy documents and running compliance checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.comparator import (
    iterate_policy_statements,
    load_policy_document,
    load_text,
    persist_run,
)
from src.models import PolicyDocument, ProjectObject


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Policy-project comparator: closed schemas, enum answers, deterministic pass/fail."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser(
        "generate-policy",
        help="Policy Agent: turn policy/law text into an editable schema JSON",
    )
    generate.add_argument("--domain", required=True, help="e.g. InfoSec, Legal")
    generate.add_argument("--input", required=True, type=Path, help="Policy text file")
    generate.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Where to write the policy document JSON (human-editable)",
    )
    generate.set_defaults(func=cmd_generate_policy)

    check = sub.add_parser(
        "check",
        help="Run IteratePolicyStatements against a project",
    )
    check.add_argument("--policy", required=True, type=Path, help="Policy document JSON")
    check.add_argument("--project", required=True, type=Path, help="Project metadata text")
    check.add_argument(
        "--answers",
        type=Path,
        default=None,
        help="Optional ProjectObject JSON. If it already covers the statement keys, no LLM is called.",
    )
    check.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/runs"),
        help="Directory for persisted ResultsObject + ProjectObject",
    )
    check.set_defaults(func=cmd_check)

    return parser


def cmd_generate_policy(args: argparse.Namespace) -> int:
    from src.policy_agent import generate_policy_document

    text = load_text(args.input)
    document = generate_policy_document(
        domain=args.domain,
        policy_text=text,
        source=str(args.input),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote policy document to {args.out}")
    print(f"  title: {document.meta.title}")
    print(f"  keys: {', '.join(key.id for key in document.keys)}")
    print(f"  statements: {', '.join(stmt.id for stmt in document.statements)}")
    print("Edit this file if you want to change the schema, then run `check`.")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    policy: PolicyDocument = load_policy_document(args.policy)
    metadata = load_text(args.project)
    existing = None
    if args.answers is not None:
        raw = json.loads(args.answers.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and "answers" in raw:
            existing = ProjectObject.model_validate(raw)
        else:
            existing = ProjectObject(answers={str(k): str(v) for k, v in raw.items()})

    parse_keys = _project_parser
    results, project_object = iterate_policy_statements(
        policy_document=policy,
        project_metadata=metadata,
        parse_keys=parse_keys,
        existing_project_object=existing,
        project_source=str(args.project),
    )
    slug = f"{args.project.stem}_{results.overall_status()}"
    saved = persist_run(results, project_object, args.out_dir, slug=slug)
    print(_format_table(results))
    print(f"overall: {results.overall_status()}")
    if results.user_input_required:
        print("user input required:")
        for item in results.user_input_required:
            print(
                f"  - {item.key}: {item.reason} "
                f"(enum={item.enum}, proposed={item.proposed_answer!r})"
            )
    print(f"saved: {saved}")
    return 0 if results.overall_status() == "pass" else 1


def _project_parser(**kwargs):
    from src.project_agent import parse_project_keys

    return parse_project_keys(**kwargs)


def _format_table(results) -> str:
    rows = [("STATEMENT", "STATUS", "DETAIL")]
    for item in results.results:
        rows.append((item.statement_id, item.status, item.detail))
    widths = [max(len(row[i]) for row in rows) for i in range(3)]
    lines = []
    for index, row in enumerate(rows):
        line = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))
        lines.append(line)
        if index == 0:
            lines.append("  ".join("-" * widths[i] for i in range(3)))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
