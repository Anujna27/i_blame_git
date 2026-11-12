import json
import os

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
        self.model = os.getenv("MNEMOSYNE_LLM_MODEL", "llama-3.1-8b-instant" if self.provider == "groq" else "gpt-4o-mini")
        self.api_key = os.getenv("GROQ_API_KEY") if self.provider == "groq" else os.getenv("OPENAI_API_KEY")
        self._client = None

    @property
    def enabled(self):
        return self.provider in {"openai", "openai_compatible", "groq"} and bool(self.api_key)

    def _get_client(self):
        if not self.enabled: return None
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self.api_key}
            base_url = os.getenv("MNEMOSYNE_LLM_BASE_URL")
            if self.provider == "groq" and not base_url:
                base_url = "https://api.groq.com/openai/v1"
            if base_url: kwargs["base_url"] = base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def json_call(self, system, user):
        client = self._get_client()
        if client is None: return None
        response = client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
        )
        return json.loads(response.choices[0].message.content)

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
