# Mnemosyne — Auditable Forgetting Layer

We do not promise perfect forgetting. We promise an auditable forgetting report: every deletion request produces a verifiable record of what was removed, what derived memory was invalidated, what inference paths were blocked, and exactly where residual risk remains.

```text
Provenance-Anchored Store → Multi-Level Erasure Engine → Portable Memory Capsule
       graph + hashes             five-level audit             cross-agent state
```

## Setup
`pip install -r requirements.txt`

## Run
`python demo/demo_runner.py`  
`streamlit run demo/ui.py`

## Seven differentiators
- Residual Risk Notice
- Five-level erasure checklist
- Portable capsule with inherited deletion state
- Hash-chained audit log
- Storage router with evidence table
- 30-session restart demo
- Token cost comparison

## Judge Q&A
**What makes this different?** Accountability: every forgetting request yields evidence and residual risk.  
**Does it guarantee deletion everywhere?** No; it explicitly reports what cannot be verified.  
**Why provenance?** It closes derived-memory paths, not just the source row.  
**Why capsules?** Deletion state travels with memory across agents.  
**Why hashes?** They make audit history tamper-evident.  
**What is the demo proof?** Contradiction handling, planted-memory abstention, deletion, hand-over, token savings, and restart persistence.

## Tech stack
| Layer | Technology |
|---|---|
| UI | Streamlit + Rich |
| Storage | Python graph/vector stores |
| Audit | Hash chain + JSON capsules |
| Tests | pytest |

## Team roles
| Member | Ownership |
|---|---|
| M1 | core |
| M2 | stores |
| M3 | capsule + agents |
| M4 | demo, integration, tests, docs, slides |
