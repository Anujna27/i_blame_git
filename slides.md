# Mnemosyne — 5-slide pitch

## Slide 1 — The problem
**1.5%** — benchmark says no memory system completes more than 1.5% of deletion requests end-to-end.

## Slide 2 — The insight
Everyone builds shallow deletion (remove the entry). Nobody builds accountability: prove what was removed, what wasn't, and where residual risk remains.

## Slide 3 — Mnemosyne architecture
```text
Provenance-Anchored Store → Multi-Level Erasure Engine → Portable Memory Capsule
                             RESIDUAL RISK NOTICE
╔══════════════════════════════════════════════════════╗
║ RESIDUAL RISK NOTICE                                ║
║ The requested memory was removed; external copies    ║
║ cannot be guaranteed.                                 ║
╚══════════════════════════════════════════════════════╝
```

## Slide 4 — The demo
Cross-agent hand-over: Agent B inherits deletion state and refuses to act on the deleted fact. Honest refusal: “I can’t provide that: this memory is blocked by an inherited deletion record.”

## Slide 5 — Why we win
We crossed 1.5% with provenance closure and we're honest about the rest. Mnemosyne is the system that makes forgetting auditable across agents.
