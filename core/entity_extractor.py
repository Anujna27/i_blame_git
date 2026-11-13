import re


class EntityExtractor:
    """Session extractor with optional LLM output and deterministic fallback."""
    def __init__(self, llm=None):
        self.llm = llm

    def extract(self, texts):
        if self.llm:
            try:
                value = self.llm.extract(texts) if hasattr(self.llm, "extract") else self.llm(texts)
                if isinstance(value, list): return value
            except Exception:
                pass
        entities = []
        for text in texts:
            for match in re.findall(r"(?:I prefer|I use|my [\w ]+ is|user [\w ]+)", text, flags=re.I):
                entities.append({"entity_type": "fact", "content": text, "mention": match})
        return entities
