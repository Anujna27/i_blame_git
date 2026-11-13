# MNEMOSYNE preference fine-tuning (Path B)

`convaiinnovations/laya-multilingual` is not the training target here: it is a
non-autoregressive text-classification model, while DPO needs a causal model
that can generate the `chosen` and `rejected` responses. Path B therefore uses
`Qwen/Qwen2.5-1.5B-Instruct` as a small multilingual causal baseline and trains
a LoRA adapter with Unsloth + TRL DPO.

The dataset is already in the repository at
`datasets/mnemosyne_compaction_rlhf_2400.jsonl`. The script converts each
record's structured prompt/context into TRL's three fields:

```text
prompt   -> memory task, query, token budget, and JSON context
chosen   -> preferred response text
rejected -> deliberately worse response text
```

## Environment

The current machine has Python 3.14 and an RTX 3050 with 4 GB VRAM. Unsloth,
PyTorch, and CUDA wheels are version-sensitive, so use Python 3.11 or 3.12 in
a separate environment. On Windows, WSL2/Linux is the safer route if a native
install cannot resolve the CUDA packages.

```powershell
# If Python 3.11 or 3.12 is installed:
py -3.11 -m venv .venv-dpo
.\.venv-dpo\Scripts\Activate.ps1
python -m pip install --upgrade pip

# Install the CUDA-enabled PyTorch wheel appropriate to the machine from
# https://pytorch.org/get-started/locally/, then:
pip install -r requirements-dpo.txt

# The Unsloth resolver can replace CUDA Torch with a CPU wheel on Windows.
# Re-assert the CUDA build after the requirements install:
pip install --force-reinstall --no-deps `
  torch==2.6.0+cu124 torchvision==0.21.0+cu124 `
  --index-url https://download.pytorch.org/whl/cu124
```

Do not put a Hugging Face token or a model-provider API key in the dataset.
The corpus is synthetic and the training script does not call Groq.

## Validate the dataset without installing ML packages

This reads every JSONL record, validates the required fields, and prints the
exact DPO row counts. It does not download a model or modify the repository.

```powershell
python scripts/finetune_compaction_dpo.py --dry-run
```

Expected default smoke selection: 48 train rows and 12 validation rows.

## Run a safe smoke fine-tune

```powershell
python scripts/finetune_compaction_dpo.py `
  --max-train-samples 48 `
  --max-eval-samples 12 `
  --max-steps 10 `
  --output-dir outputs/mnemosyne-dpo-smoke
```

The default uses 4-bit loading, batch size 1, gradient accumulation 8, and
short sequences to fit a 4 GB card. The result is a LoRA adapter, not a full
replacement model. Inspect the loss, preference accuracy, and generated
outputs before treating it as useful.

## Run the full synthetic training split

```powershell
python scripts/finetune_compaction_dpo.py `
  --max-train-samples 0 `
  --max-eval-samples 0 `
  --max-steps 0 `
  --epochs 1 `
  --output-dir outputs/mnemosyne-dpo-full
```

The full run uses 1,920 training examples and 240 validation examples. It may
be slow or exceed 4 GB depending on the installed CUDA/PyTorch build. If it
does, reduce `--max-seq-length`, keep batch size at 1, or use a larger GPU.

## What this does and does not prove

DPO teaches the causal model to prefer the synthetic `chosen` behavior over
the synthetic `rejected` behavior. It does not prove that the model correctly
uses MNEMOSYNE's live SessionStore, KnowledgeGraph, VectorStore, filesystem
memory, or deletion engine. After training, evaluate the adapter through the
real memory pipeline and rerun BEMULA-R; do not use training loss as an
unlearning or deletion-safety score.

## RLHF continuation and dreaming gate

DPO is the policy warm-start, not the complete RLHF loop. MNEMOSYNE uses the
Laya typed-decision model as a local reward gate. The gate is trained with
`scripts/finetune_laya_gate.py`; preferred candidates are labelled `accept`
and rejected candidates are labelled `escalate`.

The online policy stage is implemented in
`scripts/rlhf_grpo_compaction.py`. It loads the Qwen DPO adapter, generates
candidate compact memories, scores them with Laya, and performs a GRPO update
with a reference-policy/KL constraint.

```powershell
.\.venv-dpo\Scripts\python.exe scripts/finetune_laya_gate.py --epochs 1
.\.venv-dpo\Scripts\python.exe scripts/rlhf_grpo_compaction.py --max-train-samples 8 --max-steps 2
```

At runtime:

```python
report = agent.dream_session("session-id")
```

The local gate runs first. Ambiguous cases go to the configured LLM. A
deterministic evidence-support check runs before Laya so unsupported claims or
deletion-resurrection claims cannot be accepted solely because the classifier
is overconfident.
