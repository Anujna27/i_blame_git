import json
import os
import time

def _load_dotenv():
    path = os.getenv("MNEMOSYNE_ENV_FILE", ".env")
    if not os.path.exists(path): return
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            key, value = line.split("=", 1); key = key.strip(); value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except OSError:
        pass


class ConfiguredLLM:
    """Optional OpenAI-compatible JSON adapter; inactive unless configured."""
    def __init__(self):
        _load_dotenv()
        self.provider = os.getenv("MNEMOSYNE_LLM_PROVIDER", "none").lower()
        default_model = {"groq": "llama-3.1-8b-instant", "ollama": "llama3.2:3b"}.get(self.provider, "gpt-4o-mini")
        self.model = os.getenv("MNEMOSYNE_LLM_MODEL", default_model)
        if self.provider == "groq":
            self.api_key = os.getenv("GROQ_API_KEY")
        elif self.provider == "ollama":
            self.api_key = os.getenv("OLLAMA_API_KEY", "ollama-local")
        else:
            self.api_key = os.getenv("OPENAI_API_KEY")
        self._client = None
        self.calls = 0; self.failures = 0; self.input_tokens = 0; self.output_tokens = 0

    @property
    def enabled(self):
        return self.provider in {"openai", "openai_compatible", "groq", "ollama"} and bool(self.api_key)

    def _get_client(self):
        if not self.enabled: return None
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self.api_key}
            base_url = os.getenv("MNEMOSYNE_LLM_BASE_URL")
            if self.provider == "groq" and not base_url:
                base_url = "https://api.groq.com/openai/v1"
            if self.provider == "ollama" and not base_url:
                base_url = "http://127.0.0.1:11434/v1"
            if base_url: kwargs["base_url"] = base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def json_call(self, system, user):
        client = self._get_client()
        if client is None: return None
        attempts = int(os.getenv("MNEMOSYNE_LLM_RETRIES", "3"))
        for attempt in range(attempts):
            try:
                response = client.chat.completions.create(model=self.model, temperature=0, response_format={"type":"json_object"}, messages=[{"role":"system","content":system},{"role":"user","content":user}])
                self.calls += 1; usage = getattr(response, "usage", None)
                self.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0); self.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
                return json.loads(response.choices[0].message.content)
            except Exception:
                self.failures += 1
                if attempt == attempts - 1: raise
                time.sleep(2 ** attempt)

    def telemetry(self):
        return {"provider": self.provider, "model": self.model, "enabled": self.enabled, "calls": self.calls, "failures": self.failures, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens}

    def summarize(self, content):
        return self.json_call(
            "Return JSON only with keys l0, l1, l2. l0 is <=100 tokens, l1 is <=500 tokens, l2 preserves the full source.",
            content,
        )

    def extract(self, texts):
        return self.json_call(
            "Extract durable entities from the session. Return JSON only as {\"entities\":[{\"entity_type\":str,\"content\":str,\"properties\":object}]}.",
            "\n".join(texts),
        ).get("entities", [])

    def suggest_link(self, orphan, candidates):
        return self.json_call(
            "Choose at most one candidate. Return JSON only with target_node_id, relationship, confidence, or null target_node_id.",
            json.dumps({"orphan": orphan, "candidates": candidates}, default=str),
        )
