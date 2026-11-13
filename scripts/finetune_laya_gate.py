"""Fine-tune Laya as MNEMOSYNE's local dreaming-state decision gate.

Laya is a typed decision model, not a text generator.  Each preference record
therefore becomes two classification examples:

* the preferred candidate -> ``accept`` locally;
* the rejected candidate -> ``escalate`` to a stronger generator/LLM.

The resulting checkpoint can be loaded by ``laya.load(output_dir)``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_SOURCE = Path("datasets/mnemosyne_compaction_rlhf_2400.jsonl")
DEFAULT_OUTPUT = Path("outputs/laya-mnemosyne-gate")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default="convaiinnovations/laya-multilingual")
    parser.add_argument("--max-records", type=int, default=0,
                        help="0 uses all source records; useful for a smoke run.")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--freeze-encoder", action="store_true", default=True,
                        help="Train the Laya decision head only (recommended for 4 GB GPUs).")
    parser.add_argument("--unfreeze-encoder", action="store_false", dest="freeze_encoder")
    parser.add_argument("--device", default="auto")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def gate_question() -> dict[str, Any]:
    return {
        "gate": {
            "type": "choice",
            "instructions": (
                "Should this candidate memory be accepted by the deterministic dreaming gate, "
                "or escalated because it is unsafe, ambiguous, contradictory, overbroad, or "
                "unsupported by the supplied memory?"
            ),
            "criteria": {
                "accept": "Faithful, scoped, deletion-safe, and supported by the memory context.",
                "escalate": "Ambiguous, contradictory, unsafe, hallucinated, or not safely decidable locally.",
            },
        }
    }


def state_for(record: dict[str, Any], candidate: dict[str, Any]) -> str:
    payload = {
        "task": record["task"],
        "instruction": record["prompt"]["instruction"],
        "query": record["prompt"]["query"],
        "token_budget": record["prompt"]["token_budget"],
        "memory_context": record["context"],
        "candidate": candidate["text"],
        "candidate_scores": candidate.get("scores", {}),
        "candidate_reason": candidate.get("reason", ""),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def convert(records: list[dict[str, Any]], max_records: int = 0) -> dict[str, list[dict[str, Any]]]:
    if max_records > 0:
        records = records[:max_records]
    output: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for record in records:
        split = record["split"]
        if split not in output:
            continue
        output[split].append({
            "state": state_for(record, record["chosen"]),
            "questions": gate_question(),
            "gold": {"gate": {"probabilities": {"accept": 1.0, "escalate": 0.0}}},
            "metadata": {"record_id": record["record_id"], "source": "chosen"},
        })
        output[split].append({
            "state": state_for(record, record["rejected"]),
            "questions": gate_question(),
            "gold": {"gate": {"probabilities": {"accept": 0.0, "escalate": 1.0}}},
            "metadata": {"record_id": record["record_id"], "source": "rejected"},
        })
    return output


def write_splits(splits: dict[str, list[dict[str, Any]]], directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for split, rows in splits.items():
        path = directory / f"laya_gate_{split}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        paths[split] = path
    return paths


def train(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
    try:
        from laya.train import TrainConfig, finetune
    except ImportError as exc:
        raise RuntimeError("Install the Laya package with: pip install laya") from exc

    config = TrainConfig(
        epochs=args.epochs,
        micro_batch=1,
        grad_accum=8,
        encoder_lr=2.5e-5,
        head_lr=1e-4,
        freeze_encoder=args.freeze_encoder,
        max_len=1024,
        head_max_len=256,
        amp=True,
        gradient_checkpointing=True,
        eval_data=str(paths["validation"]),
        calib_max=200,
        calib_frac=0.1,
        calib_seed=1337,
        seed=1337,
        log_every=25,
    )
    summary = finetune(
        data=str(paths["train"]),
        model_dir=args.model,
        output_dir=str(args.output_dir),
        config=config,
        device=args.device,
    )
    (args.output_dir / "mnemosyne_gate_training.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    return summary


def main() -> int:
    args = parse_args()
    records = read_jsonl(args.source)
    splits = convert(records, args.max_records)
    paths = write_splits(splits, args.output_dir.parent / "laya-gate-data")
    print(json.dumps({"split_counts": {k: len(v) for k, v in splits.items()},
                      "data_paths": {k: str(v) for k, v in paths.items()}}, indent=2))
    summary = train(args, paths)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
