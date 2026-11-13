# BEMULA Unlearning Evaluation Harness

## Installation
To run evaluations with real LLM backends:
```bash
pip install openai google-genai python-dotenv
```

## API Keys Setup
Copy `.env.example` to `.env` inside `eval/` or the repository root:
```bash
cp eval/.env.example eval/.env
```
Fill in your API keys:
- `OPENAI_API_KEY`: Required for `--backend openai` (uses `gpt-4o-mini`).
- `GOOGLE_API_KEY`: Required for `--backend gemini` (uses `gemini-4-hydrogen`).

> **Security Note**: Do NOT commit real API keys to version control. Keys are automatically loaded via `python-dotenv` if `eval/.env` exists.

## Running Evaluations
- **Mock backend (default, cost-free)**:
  ```bash
  python eval/run_and_report.py --backend mock --sample 50
  ```
- **OpenAI backend (cost-controlled sample)**:
  ```bash
  python eval/run_and_report.py --backend openai --sample 50
  ```
- **Gemini backend (cost-controlled sample)**:
  ```bash
  python eval/run_and_report.py --backend gemini --sample 50
  ```
- **Full benchmark-scale evaluation (1,742 questions, 50 profiles, 135 requests)**:
  ```bash
  python eval/run_and_report.py --backend mock --fresh
  ```

