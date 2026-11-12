import re


class EntityExtractor:
    """Session extractor with optional LLM output and deterministic fallback."""
    def __init__(self, llm=None):
        self.llm = llm

    def extract(self, texts):
        if self.llm:
            value = self.llm(texts)
            if isinstance(value, list): return value
        entities = []
        for text in texts:
            for match in re.findall(r"(?:I prefer|I use|my [\w ]+ is|user [\w ]+)", text, flags=re.I):
                entities.append({"entity_type": "fact", "content": text, "mention": match})
        return entities
