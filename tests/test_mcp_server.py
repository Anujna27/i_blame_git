"""
tests/test_mcp_server.py

Tests for the FastMCP memory server (mcp_server.py) exposing:
- remember
- recall
- forget
"""

import json
import pytest
from mcp_server import (
    mcp,
    remember,
    recall,
    forget,
    forget_topic,
    run_memory_audit,
)


def test_mcp_server_initialization():
    assert mcp.name == "mnemosyne-memory"


def test_remember_tool():
    res = remember("Secret project code is Prometheus-9.", trust_status="user_asserted")
    assert isinstance(res, str)
    assert res.startswith("Memory stored with ID: ")
    node_id = res.replace("Memory stored with ID: ", "").strip()
    assert len(node_id) > 0


def test_recall_tool_hit_and_abstention():
    # Store a distinct fact
    stored_msg = remember("The database port for testing is 54329.", trust_status="user_asserted")
    node_id = stored_msg.replace("Memory stored with ID: ", "").strip()

    # Recall should find it
    context = recall("database port for testing", token_budget=1000)
    assert isinstance(context, str)
    assert "54329" in context

    # Non-existent or empty query behavior
    # Even if some unrelated memories exist, recall returns secure abstention
    unknown = recall("xyznonexistentunrelated99881122")
    assert isinstance(unknown, str)
    assert unknown == "Request unavailable."


def test_forget_tool_accountability_report():
    stored_msg = remember("Sensitive API key sk-test-mcp-9999", trust_status="user_asserted")
    node_id = stored_msg.replace("Memory stored with ID: ", "").strip()

    # Call forget tool
    report_json = forget(node_id=node_id, reason="User GDPR deletion request", actor="user")
    assert isinstance(report_json, str)

    report = json.loads(report_json)
    assert "verdict" in report
    assert report["verdict"] in ("fully_deleted", "partially_deleted", "failed")
    assert "residual_risks" in report
    assert isinstance(report["residual_risks"], list)

    # After forget, recall should not leak the deleted fact
    context_after = recall("Sensitive API key sk-test-mcp-9999")
    assert "sk-test-mcp-9999" not in context_after


def test_forget_topic_tool():
    # Store memories on a specific topic
    remember("User enjoys Rust programming and memory safety.", trust_status="user_asserted")
    remember("Rust cargo is used as build system.", trust_status="user_asserted")
    remember("User also likes Greek philosophy.", trust_status="user_asserted")

    # Bulk forget by topic
    result = forget_topic("Rust", reason="Erase all Rust language knowledge", actor="user")
    assert isinstance(result, str)
    assert "Successfully deleted" in result
    assert "Rust" in result
    assert "Skipped" in result

    # Verify 5 Accountability Layers are present in the JSON report
    report_dict = json.loads(result)
    assert "levels" in report_dict
    assert len(report_dict["levels"]) == 5
    assert report_dict["verdict"] in ("fully_deleted", "partially_deleted")
    assert "residual_risks" in report_dict
    assert "accountability_notice" in report_dict

    # Verify abstention after topic forget
    after = recall("Rust programming")
    assert "Rust" not in after


def test_forget_topic_no_matches():
    res = forget_topic("NonExistentTopic99999XYZ", reason="test")
    assert isinstance(res, str)
    assert ("No memories found" in res) or ("none explicitly contained" in res) or ("Nothing deleted" in res)


def test_run_memory_audit_tool():
    log = run_memory_audit(num_users=2)
    assert isinstance(log, str)
    assert "LIVE AUDIT: 2 / 50 USERS" in log
    assert "Loaded 2 profiles" in log
    assert "--- 5-LEVEL ERASURE EXECUTION SAMPLE ---" in log
    assert "[Level 1] Source Record Removed: PASS" in log
    assert "[Level 2] Derived Artifacts Invalidated: PASS" in log
    assert "[Level 3] Inference Blocked: PASS" in log
    assert "[Level 4] Non-Inferability Checked: PARTIAL" in log
    assert "[Level 5] State Restoration Checked: FAIL" in log
    assert "FINAL ACCOUNTABILITY REPORT" in log
    assert "Users Evaluated:       2 / 50" in log
    assert "METRICS & FAILURE ANALYSIS:" in log
    assert "Forget Accuracy:       100.00%" in log
    assert "Zero leaks. All targeted data was successfully blocked." in log
    assert "Control Accuracy:      100.00%" in log
    assert "Preservation Accuracy:" in log
    assert "RESIDUAL RISK NOTICE:" in log

