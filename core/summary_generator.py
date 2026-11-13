class SummaryGenerator:
    """Summary provider with an injectable LLM and deterministic fallback."""
    def __init__(self, llm=None):
        self.llm = llm

    def generate(self, content):
        if self.llm:
            try:
                value = self.llm.summarize(content) if hasattr(self.llm, "summarize") else self.llm(content)
                if isinstance(value, dict):
                    return {"l0": value.get("l0", ""), "l1": value.get("l1", ""), "l2": value.get("l2", content)}
            except Exception:
                pass
        sentences = [s.strip() for s in content.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        l0 = (sentences[0] if sentences else content)[:240]
        l1 = ". ".join(sentences[:4])[:2000]
        return {"l0": l0, "l1": l1 or content[:2000], "l2": content}
