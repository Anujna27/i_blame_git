# Pre-import faiss on Windows to ensure clean DLL loading during pytest collection
try:
    import faiss  # type: ignore # noqa: F401
except (ImportError, Exception):
    pass

