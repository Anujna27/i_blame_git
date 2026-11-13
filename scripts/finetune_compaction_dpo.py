"""Fine-tune a small causal language model on MNEMOSYNE preferences with DPO.

The synthetic corpus is intentionally kept in the repository's JSONL format.
This script converts each record to TRL's standard ``prompt/chosen/rejected``
preference schema at load time, so there is no second, easily-drifted dataset.

Start with ``--dry-run`` or a small smoke run before using the complete train
split.  The default smoke run is deliberately small for a 4 GB GPU.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import random
import sys
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_DATASET = Path("datasets/mnemosyne_compaction_rlhf_2400.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-name", default=DEFAULT_MODEL)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/mnemosyne-dpo"))
    parser.add_argument("--max-train-samples", type=int, default=48,
                        help="0 uses all 1,920 train records (default: smoke run).")
    parser.add_argument("--max-eval-samples", type=int, default=12,
                        help="0 uses all 240 validation records; -1 disables eval.")
    parser.add_argument("--max-steps", type=int, default=10,
                        help="0 trains for --epochs instead of a fixed step count.")
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-seq-length", type=int, default=768)
    parser.add_argument("--max-prompt-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--no-4bit", action="store_true",
                        help="Disable 4-bit loading; usually not suitable for a 4 GB GPU.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate/format the dataset without importing ML packages.")
    return parser.parse_args()


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            validate_record(record, line_number)
            records.append(record)
    return records


def validate_record(record: dict[str, Any], line_number: int) -> None:
    required = {"record_id", "split", "prompt", "context", "chosen", "rejected"}
    missing = required.difference(record)
    if missing:
        raise ValueError(f"Line {line_number} is missing fields: {sorted(missing)}")
    for preference_name in ("chosen", "rejected"):
        value = record[preference_name]
        if not isinstance(value, dict) or not isinstance(value.get("text"), str):
            raise ValueError(f"Line {line_number} has invalid {preference_name}.text")


def format_prompt(record: dict[str, Any]) -> str:
    prompt = record["prompt"]
    context = record["context"]
    context_json = json.dumps(context, ensure_ascii=False, sort_keys=True)
    return (
        "You are the MNEMOSYNE memory-compaction assistant.\n"
        f"Instruction: {prompt['instruction']}\n"
        f"Query: {prompt['query']}\n"
        f"Token budget: {prompt['token_budget']}\n"
        "Memory context (JSON):\n"
        f"{context_json}\n\n"
        "Return only the best faithful memory decision or compacted text. "
        "Do not invent facts, widen session scope, or resurrect deleted data.\n"
        "Assistant response:\n"
    )


def to_preference_row(record: dict[str, Any]) -> dict[str, str]:
    return {
        "prompt": format_prompt(record),
        "chosen": record["chosen"]["text"],
        "rejected": record["rejected"]["text"],
        "record_id": record["record_id"],
        "task": record["task"],
    }


def select_split(records: list[dict[str, Any]], split: str, limit: int) -> list[dict[str, str]]:
    selected = [to_preference_row(record) for record in records if record["split"] == split]
    if limit > 0:
        selected = selected[:limit]
    return selected


def print_dry_run(records: list[dict[str, Any]], args: argparse.Namespace) -> None:
    train = select_split(records, "train", args.max_train_samples)
    validation = [] if args.max_eval_samples == -1 else select_split(
        records, "validation", args.max_eval_samples
    )
    sample = train[0] if train else None
    print(json.dumps({
        "model_name": args.model_name,
        "dataset": str(args.dataset),
        "total_records": len(records),
        "train_records": len(train),
        "validation_records": len(validation),
        "schema": ["prompt", "chosen", "rejected"],
        "sample_prompt_characters": len(sample["prompt"]) if sample else 0,
        "sample_chosen": sample["chosen"] if sample else None,
        "sample_rejected": sample["rejected"] if sample else None,
        "next_step": "Remove --dry-run to start DPO training.",
    }, indent=2, ensure_ascii=False))


def require_training_dependencies() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    try:
        import torch
        from datasets import Dataset
        from unsloth import FastLanguageModel, PatchDPOTrainer, is_bfloat16_supported
        from trl import DPOConfig, DPOTrainer
    except ImportError as exc:
        raise RuntimeError(
            "DPO dependencies are not installed. Use a Python 3.11/3.12 environment "
            "and follow docs/FINETUNE_DPO.md, then retry."
        ) from exc
    return torch, Dataset, FastLanguageModel, PatchDPOTrainer, is_bfloat16_supported, DPOConfig, DPOTrainer


def supported_kwargs(callable_obj: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Keep the script compatible with nearby TRL/Unsloth API revisions."""
    parameters = inspect.signature(callable_obj).parameters
    return {key: value for key, value in values.items() if key in parameters}


def train(records: list[dict[str, Any]], args: argparse.Namespace) -> None:
    torch, Dataset, FastLanguageModel, PatchDPOTrainer, is_bfloat16_supported, DPOConfig, DPOTrainer = (
        require_training_dependencies()
    )

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. This smoke configuration expects an NVIDIA GPU.")

    random.seed(args.seed)
    os.environ.setdefault("WANDB_DISABLED", "true")
    PatchDPOTrainer()

    train_rows = select_split(records, "train", args.max_train_samples)
    eval_rows = [] if args.max_eval_samples == -1 else select_split(
        records, "validation", args.max_eval_samples
    )
    if not train_rows:
        raise ValueError("No training rows selected.")

    train_dataset = Dataset.from_list(train_rows)
    eval_dataset = Dataset.from_list(eval_rows) if eval_rows else None
    args.output_dir.mkdir(parents=True, exist_ok=True)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model_name,
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=not args.no_4bit,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=8,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=8,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        max_seq_length=args.max_seq_length,
    )

    use_bf16 = bool(is_bfloat16_supported())
    config_values: dict[str, Any] = {
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": 1,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "warmup_ratio": 0.1,
        "num_train_epochs": args.epochs,
        "fp16": not use_bf16,
        "bf16": use_bf16,
        "logging_steps": 1,
        "logging_first_step": True,
        "optim": "adamw_8bit",
        "seed": args.seed,
        "output_dir": str(args.output_dir),
        "report_to": "none",
        "remove_unused_columns": False,
        "gradient_checkpointing": True,
        # Evaluate once after training below. Evaluating every step is
        # disproportionately expensive on a small GPU and is not useful for
        # this deterministic synthetic corpus.
        "save_strategy": "no",
        "eval_strategy": "no",
        "evaluation_strategy": "no",
        "max_steps": args.max_steps if args.max_steps > 0 else -1,
        "beta": 0.1,
        "max_length": args.max_seq_length,
        "max_prompt_length": args.max_prompt_length,
    }
    dpo_config = DPOConfig(**supported_kwargs(DPOConfig, config_values))

    trainer_values = {
        "model": model,
        "ref_model": None,
        "args": dpo_config,
        "train_dataset": train_dataset,
        "eval_dataset": eval_dataset,
        "beta": 0.1,
        "max_length": args.max_seq_length,
        "max_prompt_length": args.max_prompt_length,
        "processing_class": tokenizer,
        "tokenizer": tokenizer,
    }
    trainer = DPOTrainer(**supported_kwargs(DPOTrainer, trainer_values))
    result = trainer.train()
    eval_metrics = trainer.evaluate() if eval_dataset is not None else {}
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))

    summary = {
        "model_name": args.model_name,
        "dataset": str(args.dataset),
        "train_records": len(train_rows),
        "validation_records": len(eval_rows),
        "max_steps": args.max_steps,
        "output_dir": str(args.output_dir),
        "train_metrics": getattr(result, "metrics", {}),
        "eval_metrics": eval_metrics,
        "note": "This is a LoRA adapter trained with DPO; evaluate before production use.",
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str))


def main() -> int:
    args = parse_args()
    try:
        records = read_records(args.dataset)
        if args.dry_run:
            print_dry_run(records, args)
            return 0
        train(records, args)
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
