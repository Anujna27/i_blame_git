"""
eval/llm_backends.py

Abstract and concrete LLM backend implementations for the BEMULA evaluation harness.

CRITICAL ARCHITECTURAL RULE:
The LLM does NOT own memory. Mnemosyne owns memory. The LLM only receives
the ActiveContext string built by the harness and generates an answer from it.
Deletion is enforced by Mnemosyne's blocked_embeddings gate and vector store,
not by the LLM provider.
"""

from abc import ABC, abstractmethod
import os
from pathlib import Path
import time
from typing import Optional

from google import genai

# Attempt to load environment variables from .env files if python-dotenv is installed
try:
    from dotenv import load_dotenv

    _eval_dir = Path(__file__).resolve().parent
    _eval_env = _eval_dir / ".env"
    _root_env = _eval_dir.parent / ".env"

    if _eval_env.exists():
        load_dotenv(_eval_env)
    elif _root_env.exists():
        load_dotenv(_root_env)
    else:
        load_dotenv()
except ImportError:
    pass


class LLMBackend(ABC):
    """Abstract base class for all LLM answer generators."""

    @abstractmethod
    def generate(self, context: str, question: str) -> str:
        """
        Generate an answer to question strictly using the provided context.
        If context does not contain the answer, return an abstention phrase
        (e.g., 'I don't know.').
        """
        pass


class MockBackend(LLMBackend):
    """
    Deterministic mock generator.
    Returns the context content if present, or 'I don't know' if context is empty.
    """

    def generate(self, context: str, question: str) -> str:
        if not context or not context.strip():
            return "I don't know."
        return context.strip()


class OpenAIBackend(LLMBackend):
    """
    OpenAI GPT generator (default: gpt-4o-mini).
    Requires OPENAI_API_KEY environment variable.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI backend requires OPENAI_API_KEY environment variable. "
                "Set OPENAI_API_KEY or install python-dotenv and add it to eval/.env"
            )
        try:
            import openai
        except ImportError:
            raise RuntimeError(
                "OpenAI backend requires 'openai' package. "
                "Install with: pip install openai and set OPENAI_API_KEY"
            )

        self.model = model
        self.client = openai.OpenAI(api_key=api_key)

    def generate(self, context: str, question: str) -> str:
        if not context or not context.strip():
            return "I don't know."

        # Retries with exponential backoff for transient rate limits
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Answer ONLY from the provided context. "
                                "If the context does not contain the answer, say: I don't know."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Context:\n{context}\n\nQuestion: {question}",
                        },
                    ],
                    temperature=0,
                )
                content = response.choices[0].message.content
                return (content or "").strip()
            except Exception as e:
                # If rate limit or connection issue, retry with backoff
                err_str = str(e).lower()
                if ("rate_limit" in err_str or "429" in err_str or "connection" in err_str) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                # Otherwise re-raise with clear explanation
                raise RuntimeError(f"OpenAI API error during generation: {e}") from e


class GeminiBackend(LLMBackend):
    def __init__(self, model="gemini-4-hydrogen", fallback_models=("gemini-2.5-flash", "gemini-2.0-flash"), delay: float = 12.0):
        import os
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("Gemini backend requires GOOGLE_API_KEY environment variable.")
        self.client = genai.Client(api_key=api_key)
        self.model_name = os.environ.get("GEMINI_MODEL", model)
        self.fallback_models = [m for m in fallback_models if m != self.model_name]
        self.delay = float(os.environ.get("GEMINI_DELAY", str(delay)))
        self.last_call_time = 0.0  # Track time of last API call

    def generate(self, context: str, question: str) -> str:
        prompt = (
            f"Answer ONLY from this context. If the answer is not present, say I don't know.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}"
        )

        max_retries = 5
        models_to_try = [self.model_name] + self.fallback_models

        for current_model in models_to_try:
            for attempt in range(max_retries):
                # Enforce delay to comply with rate limits (default 12.0s for free tier 5 RPM)
                now = time.time()
                time_since_last_call = now - self.last_call_time
                if self.delay > 0 and time_since_last_call < self.delay:
                    wait_time = self.delay - time_since_last_call
                    time.sleep(wait_time)

                try:
                    response = self.client.models.generate_content(
                        model=current_model,
                        contents=prompt,
                    )
                    self.last_call_time = time.time()
                    return (response.text or "").strip()
                except Exception as e:
                    self.last_call_time = time.time()
                    err_str = str(e)

                    is_503 = "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower()
                    is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                    is_transient = is_503 or is_429 or "500" in err_str or "INTERNAL" in err_str or "timeout" in err_str.lower() or "connection" in err_str.lower()

                    if is_transient and attempt < max_retries - 1:
                        if is_429:
                            import re
                            delay_match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+)s?", err_str)
                            if delay_match:
                                wait_seconds = max(int(delay_match.group(1)), 12)
                            else:
                                wait_seconds = 12 * (attempt + 1)
                            print(f"[Rate limit 429] Waiting {wait_seconds}s before retrying {current_model} (Attempt {attempt + 1}/{max_retries})...")
                            time.sleep(wait_seconds)
                        elif is_503:
                            wait_seconds = 15 * (attempt + 1)
                            print(f"[High Demand 503] {current_model} experiencing temporary load spike. Waiting {wait_seconds}s before retrying (Attempt {attempt + 1}/{max_retries})...")
                            time.sleep(wait_seconds)
                        else:
                            wait_seconds = 12 * (attempt + 1)
                            print(f"[Transient error] Waiting {wait_seconds}s before retrying {current_model} (Attempt {attempt + 1}/{max_retries})...")
                            time.sleep(wait_seconds)
                        continue

                    # If 503 high demand persists on this model and we have a fallback model, try next model
                    if is_503 and current_model != models_to_try[-1]:
                        print(f"Model {current_model} experienced persistent 503 high demand. Trying fallback model...")
                        break

                    if current_model == models_to_try[-1]:
                        raise RuntimeError(f"Gemini API error during generation after {max_retries} attempts: {e}")


def get_backend(name: str = "mock", model: Optional[str] = None, delay: Optional[float] = None) -> LLMBackend:
    """Factory for selecting LLM backend."""
    name_clean = (name or "mock").strip().lower()
    if name_clean == "mock":
        return MockBackend()
    elif name_clean == "openai":
        return OpenAIBackend(model=model or "gpt-4o-mini")
    elif name_clean in ("gemini", "google"):
        delay_val = delay if delay is not None else 12.0
        return GeminiBackend(model=model or "gemini-4-hydrogen", delay=delay_val)
    else:
        raise ValueError(
            f"Unknown backend '{name}'. Supported backends: 'mock', 'openai', 'gemini'"
        )

