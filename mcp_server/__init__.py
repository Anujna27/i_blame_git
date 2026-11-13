"""MCP integration for the MNEMOSYNE memory service."""

import importlib.util
from pathlib import Path

# Re-export root mcp_server.py symbols so 'import mcp_server' works seamlessly
_root_file = Path(__file__).resolve().parent.parent / "mcp_server.py"
if _root_file.exists():
    _spec = importlib.util.spec_from_file_location("_mcp_server_root", str(_root_file))
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        for _attr in [
            "mcp",
            "remember",
            "recall",
            "forget",
            "forget_topic",
            "run_memory_audit",
            "agent",
        ]:
            if hasattr(_mod, _attr):
                globals()[_attr] = getattr(_mod, _attr)


