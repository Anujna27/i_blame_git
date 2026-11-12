# Pre-import faiss on Windows to ensure clean DLL loading during pytest collection
try:
    import faiss  # noqa: F401
except Exception:
    pass
