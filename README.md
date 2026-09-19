# AaltoAI-Hackathon

Policy–project comparator with a compliance **reviewer UI**.

## Reviewer UI

```text
pip install -r requirements.txt
python -m uvicorn webapp.app:app --reload
```

Open http://127.0.0.1:8000 — the InfoSec demo review is seeded on startup from `examples/policies/infosec.md`.

## CLI

```text
python main.py generate-policy --domain InfoSec --input examples/policies/infosec.md --out data/policies/infosec.json
python main.py check --policy examples/policies/infosec.schema.json --project examples/projects/compliant.md
```

Export a reviewed document from the UI, then point `check --policy` at `data/policies/<review-id>.json`.
