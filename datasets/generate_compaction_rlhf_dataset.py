"""Generate a deterministic synthetic preference dataset for MNEMOSYNE compaction.

The output is intentionally synthetic and contains no real personal data. It is
formatted as JSONL records suitable for preference tuning, reward modeling, or
RLHF-style ranking experiments.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "mnemosyne_compaction_rlhf_2400.jsonl"
SCHEMA = ROOT / "mnemosyne_compaction_rlhf_schema.json"


PEOPLE = ["USER_ASTER", "USER_BIRCH", "USER_CEDAR", "USER_DUNE", "USER_ELM"]
TOOLS = ["Python", "TypeScript", "Rust", "Go", "Java"]
FRAMEWORKS = ["FastAPI", "Django", "Express", "Axum", "Spring Boot"]
CHANNELS = ["email", "chat", "ticket", "phone", "internal note"]
PROJECTS = ["ORBIT", "LANTERN", "RIVER", "MOSAIC", "PULSE"]


def entity(entity_id, content, session, entity_type, state="active", derived_from=None):
    return {
        "entity_id": entity_id,
        "content": content,
        "session_id": session,
        "entity_type": entity_type,
        "deletion_state": state,
        "derived_from": derived_from or [],
    }


def context_for(i, mode):
    person = PEOPLE[i % len(PEOPLE)]
    tool = TOOLS[i % len(TOOLS)]
    framework = FRAMEWORKS[i % len(FRAMEWORKS)]
    project = PROJECTS[i % len(PROJECTS)]
    session = f"session_{i % 18:02d}"
    base = [
        entity(f"e-{i}-profile", f"{person} is working on project {project}.", session, "profile"),
        entity(f"e-{i}-language", f"{person} prefers {tool} for backend work.", session, "preference"),
        entity(f"e-{i}-framework", f"{person} uses {framework} in project {project}.", session, "preference"),
        entity(f"e-{i}-channel", f"{person} prefers {CHANNELS[i % len(CHANNELS)]} for support.", session, "preference"),
    ]
    if mode in {"contradiction", "deletion", "dreaming"}:
        base.append(entity(f"e-{i}-old", f"Earlier note: {person} preferred {TOOLS[(i + 1) % len(TOOLS)]}.", session, "historical", "active"))
    if mode in {"deletion", "dreaming"}:
        base.append(entity(f"e-{i}-derived", f"Derived summary: {person} is a {tool} developer on {project}.", session, "derived", "active", [f"e-{i}-language", f"e-{i}-profile"]))
    if mode == "session":
        base.append(entity(f"e-{i}-other-session", f"Unrelated session note: deployment target is Windows Server.", f"other_{i:03d}", "deployment"))
    return base


def good_output(i, mode, budget):
    person = PEOPLE[i % len(PEOPLE)]
    tool = TOOLS[i % len(TOOLS)]
    framework = FRAMEWORKS[i % len(FRAMEWORKS)]
    project = PROJECTS[i % len(PROJECTS)]
    if mode == "compaction":
        return f"{person} is building {project} with {tool} and {framework}. Keep this as the active project preference."
    if mode == "token":
        return f"{person}: {tool} + {framework}; project {project}. Exclude unrelated session data."
    if mode == "contradiction":
        return f"Conflict: current preference is {tool}; an older note says {TOOLS[(i + 1) % len(TOOLS)]}. Prefer the newer/current claim and retain the conflict marker."
    if mode == "session":
        return f"Session-scoped context: {person} uses {tool} and {framework} for {project}. Do not include the unrelated deployment note."
    if mode == "deletion":
        return f"Deletion-safe result: remove the requested target and its derived copies; preserve unrelated entities; report unresolved semantic risk instead of inventing success."
    return f"Dream-state consolidation: merge stable repeated facts about {person}, preserve current {tool}/{framework} preferences, retain contradictions and deletion markers, and avoid creating new facts."


def bad_output(i, mode, budget):
    person = PEOPLE[i % len(PEOPLE)]
    tool = TOOLS[i % len(TOOLS)]
    project = PROJECTS[i % len(PROJECTS)]
    if mode == "compaction":
        return f"{person} is a developer. All conversation details are preserved: {tool}, {project}, every timestamp, and every unrelated note."
    if mode == "token":
        return (f"{person} uses {tool} for project {project}. " * max(8, budget // 8)).strip()
    if mode == "contradiction":
        return f"{person} definitely uses {tool}; ignore the conflicting older memory and delete it."
    if mode == "session":
        return f"{person} uses {tool}. The deployment target is Windows Server, so include that unrelated session context too."
    if mode == "deletion":
        return f"Deletion complete. Keep the derived summary and paraphrases because they are useful, and claim fully_deleted without checking them."
    return f"Dream consolidation: infer that {person} likes {tool}, prefers {CHANNELS[(i + 2) % len(CHANNELS)]}, and will use project {project} next year."


def make_record(i, mode, split, rng):
    budget = [32, 64, 96, 128][i % 4]
    context = context_for(i, mode)
    chosen = good_output(i, mode, budget)
    rejected = bad_output(i, mode, budget)
    chosen_score = {
        "fidelity": 1.0,
        "compression": 0.85 if mode in {"compaction", "token"} else 0.65,
        "scope_control": 1.0 if mode == "session" else 0.9,
        "deletion_safety": 1.0 if mode == "deletion" else 0.75,
        "contradiction_handling": 1.0 if mode == "contradiction" else 0.7,
        "hallucination_resistance": 1.0 if mode == "dreaming" else 0.85,
    }
    rejected_score = {key: round(max(0.0, value - rng.uniform(0.35, 0.75)), 2) for key, value in chosen_score.items()}
    return {
        "record_id": f"mnemosyne-{i:05d}",
        "split": split,
        "task": mode,
        "prompt": {
            "instruction": "Compact memory for an agent while preserving truth, scope, lifecycle, and deletion safety.",
            "query": {
                "compaction": "What stable facts should remain in memory?",
                "token": f"Build context within a {budget}-token budget.",
                "contradiction": "Resolve or expose conflicting preferences.",
                "session": "Answer using only the active session.",
                "deletion": "Process the deletion request without claiming more than was verified.",
                "dreaming": "Consolidate memory during a background dreaming pass.",
            }[mode],
            "token_budget": budget,
        },
        "context": {
            "session_id": context[0]["session_id"],
            "entities": context,
            "source": "synthetic_memory_corpus",
        },
        "chosen": {"text": chosen, "scores": chosen_score, "reason": "Preserves relevant facts, scope, uncertainty, and deletion safety."},
        "rejected": {"text": rejected, "scores": rejected_score, "reason": "Over-compresses, leaks scope, deletes evidence, or invents unsupported facts."},
        "preference": {"chosen": "chosen", "margin": round(sum(chosen_score.values()) - sum(rejected_score.values()), 2)},
        "metadata": {"synthetic": True, "generator_version": "1.0", "seed": 1337, "entity_count": len(context)},
    }


def main():
    rng = random.Random(1337)
    modes = ["compaction", "token", "contradiction", "session", "deletion", "dreaming"]
    records = []
    total = 2400
    for i in range(total):
        mode = modes[i % len(modes)]
        split = "train" if i < 1920 else ("validation" if i < 2160 else "test")
        records.append(make_record(i, mode, split, rng))
    with OUTPUT.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    schema = {
        "format": "jsonl",
        "records": total,
        "splits": {"train": 1920, "validation": 240, "test": 240},
        "tasks": modes,
        "fields": {
            "prompt": "instruction, query, token_budget",
            "context": "session-scoped synthetic entities",
            "chosen": "preferred compaction/action with reward dimensions",
            "rejected": "negative preference with failure reason",
            "preference": "ranking label and reward margin",
        },
        "safety": "Synthetic identifiers and facts only; no real personal data or secrets.",
    }
    SCHEMA.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "schema": str(SCHEMA), "records": total, "splits": schema["splits"]}, indent=2))


if __name__ == "__main__":
    main()
