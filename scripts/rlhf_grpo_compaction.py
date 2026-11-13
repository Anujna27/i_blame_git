"""Online RLHF-style policy optimization using Laya as the reward model.

This is the stage after DPO warm-start:
Qwen policy -> generate candidates -> Laya reward -> GRPO policy update.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=Path("datasets/mnemosyne_compaction_rlhf_2400.jsonl"))
    p.add_argument("--policy", default="outputs/mnemosyne-dpo-full-v2")
    p.add_argument("--reward-model", default="outputs/laya-mnemosyne-gate")
    p.add_argument("--output-dir", type=Path, default=Path("outputs/mnemosyne-rlhf-grpo"))
    p.add_argument("--max-train-samples", type=int, default=8)
    p.add_argument("--max-steps", type=int, default=2)
    return p.parse_args()


def prompt_for(record: dict[str, Any]) -> str:
    return (
        "You are the MNEMOSYNE memory-compaction assistant.\n"
        f"Instruction: {record['prompt']['instruction']}\n"
        f"Query: {record['prompt']['query']}\n"
        f"Token budget: {record['prompt']['token_budget']}\n"
        "Memory context (JSON):\n"
        f"{json.dumps(record['context'], ensure_ascii=False, sort_keys=True)}\n\n"
        "Generate only a faithful compact memory decision. Do not invent facts, widen scope, "
        "or resurrect deleted data.\nAssistant response:\n"
    )


def main() -> int:
    a = args()
    import torch
    from datasets import Dataset
    from unsloth import FastLanguageModel
    from trl import GRPOConfig, GRPOTrainer
    import laya

    records = [json.loads(line) for line in a.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = [r for r in records if r.get("split") == "train"][:a.max_train_samples]
    dataset = Dataset.from_list([{"prompt": prompt_for(r)} for r in records])
    reward_agent = laya.load(a.reward_model, device="cpu")

    questions = {
        "gate": {
            "type": "choice",
            "instructions": "Should this generated memory be accepted locally or escalated?",
            "criteria": {
                "accept": "faithful, scoped, deletion-safe, supported",
                "escalate": "ambiguous, contradictory, unsafe, hallucinated, unsupported",
            },
        }
    }

    def laya_reward(prompts, completions, **kwargs):
        rewards = []
        for prompt, completion in zip(prompts, completions):
            result = reward_agent.predict(prompt + completion, questions)
            answer = ((result or {}).get("answers") or {}).get("gate", {})
            probs = answer.get("probabilities") or {}
            rewards.append(float(probs.get("accept", 0.0)) - float(probs.get("escalate", 0.0)))
        return rewards

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=a.policy, max_seq_length=768, dtype=None, load_in_4bit=True
    )
    FastLanguageModel.for_training(model)
    config = GRPOConfig(
        output_dir=str(a.output_dir),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        max_steps=a.max_steps,
        learning_rate=1e-6,
        num_generations=2,
        max_completion_length=64,
        gradient_checkpointing=True,
        bf16=True,
        report_to="none",
        save_strategy="no",
        beta=0.04,
        seed=1337,
    )
    trainer = GRPOTrainer(
        model=model,
        reward_funcs=laya_reward,
        args=config,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    result = trainer.train()
    trainer.save_model(str(a.output_dir))
    summary = {"policy": a.policy, "reward_model": a.reward_model, "records": len(records),
               "max_steps": a.max_steps, "metrics": getattr(result, "metrics", {})}
    a.output_dir.mkdir(parents=True, exist_ok=True)
    (a.output_dir / "rlhf_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
