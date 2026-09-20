# Poliview

Closed-policy comparator with a Material 3 **governance** and **project owner** demo. Named after Microsoft Purview: policy you can actually see, and a clear path for the people who have to ship.

The walkthrough loads **GDPR** once (transfers, lawful basis, DPA, retention, RoPA) and reuses it for every product. **EU AI Act** is the second standard (risk class, human oversight, logging, model card). GrowthBoard fails both on purpose; Campus Pilot is missing transfer evidence. The LLM never decides pass/fail — [`src/comparator.py`](src/comparator.py) does.

## Reviewer UI

```text
pip install -r requirements.txt
python -m uvicorn webapp.app:app --reload
```

Open http://127.0.0.1:8000 — GDPR and the EU AI Act are seeded on startup. The first-run guide walks both roles. Extra Markdown (and project notes) for live uploads live in [`data/samples/`](data/samples/).

**Governance** (`#/`) is the DPO / AI Act officer library. Load the law once, close the questions, keep final say.

**Project owner workspace** is at http://127.0.0.1:8000/#/project. The left pane is project context, files, connections, and a live compliance preview with **Check compliance**. Owners can add files or paste notes from Explorer. The centre editor pins **Compliance health** like a file; other project files open in tabs. The right pane is a compliance guide chat. Demo workspace: [`examples/workspaces/growthboard/`](examples/workspaces/growthboard/) — a CRM dashboard that fails GDPR transfers and EU AI Act oversight. Campus Pilot is the GDPR missing-info contrast.

**Compliance health** (standalone results view) is at http://127.0.0.1:8000/#/health. The picker reads curated snapshots from `examples/health/` plus CLI runs in `data/runs/`. [`examples/health/demo_compliance_health.json`](examples/health/demo_compliance_health.json) showcases GDPR + EU AI Act, donut pass rates, failed-only vs all checks, remediations, and DPO / AI Act officer contacts.

Upload `.md` to add a **new** policy or to **update** an existing one (version history is kept under `data/reviews/<id>/versions/`). Use **Generate policies** on a new upload and **Update policies** after a changed upload. PDF upload is reserved in the UI and can be added later; convert PDFs to Markdown for now.

## CLI

```text
python main.py generate-policy --domain GDPR --input examples/policies/gdpr.md --out data/policies/gdpr.json
python main.py check --policy examples/policies/gdpr.schema.json --project examples/projects/compliant.md
```

Export a reviewed document from the UI, then point `check --policy` at `data/policies/<review-id>.json`.
