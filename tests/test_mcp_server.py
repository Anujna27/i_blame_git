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
    run_automated_benchmark,
    run_bemula_benchmark,
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
    # Even if some unrelated memories exist, recall returns string
    unknown = recall("xyznonexistentunrelated99881122")
    assert isinstance(unknown, str)


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


def test_run_automated_benchmark_tool():
    report = run_automated_benchmark(num_profiles=2)
    assert isinstance(report, str)
    assert "=== AUTOMATED SYNTHETIC BENCHMARK ===" in report
    assert "Profiles Tested: 2" in report
    assert "Request Pass Rate (RPR): 100.00%" in report
    assert "Deletion Accuracy: 100.00% (0 leaks)" in report
    assert "Preservation Accuracy: 100.00%" in report


def test_run_bemula_benchmark_tool():
    # Run smoke evaluation
    report = run_bemula_benchmark(smoke=True, limit=2)
    assert isinstance(report, str)
    assert "BEMULA-SCALE SYNTHETIC REPLICATION" in report
    assert "System              | Question Acc | Request Pass Rate" in report
    assert "Real-Stack Agent" in report
    assert "Per-question-type breakdown" in report
    assert "Improvement over 1.5% baseline" in report

