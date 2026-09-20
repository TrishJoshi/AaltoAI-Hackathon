# Poliview

Closed-policy comparator with a Material 3 **governance** and **project owner** demo. Named after Microsoft Purview: policy you can actually see, and a clear path for the people who have to ship.

## Reviewer UI

```text
pip install -r requirements.txt
python -m uvicorn webapp.app:app --reload
```

Open http://127.0.0.1:8000 — the InfoSec demo is seeded on startup.

**Project owner workspace** (VS Code-style layout) is at http://127.0.0.1:8000/#/project. The left pane is project context, files, connections, and a live compliance preview with **Check compliance**. The centre editor pins **Compliance health** like a file; other project files open in tabs, with findings highlighted. The right pane is a compliance guide chat. Demo workspace: [`examples/workspaces/growthboard/`](examples/workspaces/growthboard/).

**Compliance health** (standalone results view) is at http://127.0.0.1:8000/#/health. The demo picker reads curated snapshots from `examples/health/` plus CLI runs in `data/runs/`. [`examples/health/demo_compliance_health.json`](examples/health/demo_compliance_health.json) showcases multiple policies, donut pass rates, failed-only vs all checks, remediations, and policy-owner contacts.

Upload `.md` to add a **new** policy or to **update** an existing one (version history is kept under `data/reviews/<id>/versions/`). Use **Generate policies** on a new upload and **Update policies** after a changed upload. PDF upload is reserved in the UI and can be added later; convert PDFs to Markdown for now.

## CLI

```text
python main.py generate-policy --domain InfoSec --input examples/policies/infosec.md --out data/policies/infosec.json
python main.py check --policy examples/policies/infosec.schema.json --project examples/projects/compliant.md
```

Export a reviewed document from the UI, then point `check --policy` at `data/policies/<review-id>.json`.
