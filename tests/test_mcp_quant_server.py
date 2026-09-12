"""
quant-server MCP tools and manifest consistency: builder/mentor boundaries
across both servers and both agent sources, no order-sending tools,
deterministic tool outputs.
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))


def _load_server():
    spec = importlib.util.spec_from_file_location("quant_server", ROOT / "mcp" / "quant_server" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["quant_server"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def server():
    return _load_server()


@pytest.fixture(scope="module")
def manifest():
    return yaml.safe_load((ROOT / "mcp" / "manifest.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def gc():
    import generate_configs

    return generate_configs


# ------------------------------------------------------------- manifest
def test_manifest_tools_exist_and_are_grouped(server, manifest):
    groups = manifest["tool_groups"]["quant-server"]
    declared = {t for g in groups.values() for t in g}
    implemented = {fn.__name__ for g in server.TOOLS.values() for fn in g}
    assert declared == implemented
    for group, names in groups.items():
        assert [fn.__name__ for fn in server.TOOLS[group]] == names


def test_role_boundaries(manifest, gc):
    mentor = manifest["agents"]["quant-mentor"]
    builder = manifest["agents"]["quant-builder"]
    assert "build" not in mentor["groups"] and mentor["filesystem_access"] == "read-only"
    assert "audit" not in builder["groups"] and builder["filesystem_access"] == "read-write"

    mentor_tools = set(gc.agent_tool_names(manifest, "quant-mentor"))
    builder_tools = set(gc.agent_tool_names(manifest, "quant-builder"))
    orch_tools = set(gc.agent_tool_names(manifest, "quant-orchestrator"))
    # same rule on both servers
    assert {"mcp__quant-server__review_log", "mcp__quant_mcp__log_review"} <= mentor_tools
    assert {"mcp__quant-server__paper_simulation", "mcp__quant_mcp__refresh"}.isdisjoint(mentor_tools)
    assert {"mcp__quant-server__paper_simulation", "mcp__quant_mcp__export_dataset"} <= builder_tools
    assert {"mcp__quant-server__review_log", "mcp__quant_mcp__log_review"}.isdisjoint(builder_tools)
    assert orch_tools >= mentor_tools | builder_tools


def test_no_order_sending_tools(server, manifest):
    names = [t for s in manifest["tool_groups"].values() for g in s.values() for t in g]
    names += [fn.__name__ for g in server.TOOLS.values() for fn in g]
    for pat in manifest["forbidden_tool_patterns"]:
        assert not any(pat in n for n in names), pat


def test_every_agent_has_identical_grants_in_every_copy(manifest, gc):
    prefixes = gc.managed_prefixes(manifest)
    for agent in manifest["agents"]:
        expected = gc.agent_tool_names(manifest, agent)
        for path in gc.resolve_agent_files(manifest, agent):
            if not path.exists():
                continue  # external workspace absent on this machine
            text = path.read_text(encoding="utf-8-sig")
            assert gc.BEGIN in text and gc.END in text, path
            m = __import__("re").search(r"^tools:\s*(.*)$", text, flags=__import__("re").M)
            if m:
                granted = [t.strip() for t in m.group(1).split(",") if any(t.strip().startswith(p) for p in prefixes)]
                assert granted == expected, path


def test_generated_configs_are_current(manifest, gc):
    cfg = gc.server_config(manifest, env_style=True)
    assert set(cfg["mcpServers"]) == set(manifest["servers"])
    assert cfg["mcpServers"]["quant-server"]["args"][0] == "mcp/quant_server/server.py"
    assert cfg["mcpServers"]["quant_mcp"]["args"][0].startswith("${QUANT_MERG_ROOT:-")
    resolved = gc.server_config(manifest, env_style=False)
    assert "${" not in json.dumps(resolved) and "{merg" not in json.dumps(resolved)
    assert (ROOT / ".mcp.json").exists() and (ROOT / ".agents" / "mcp.json").exists()
    assert gc.main(["--check"]) == 0


def test_fastmcp_registration(server):
    pytest.importorskip("mcp")
    import asyncio

    names = {t.name for t in asyncio.run(server.build_server().list_tools())}
    assert names == {fn.__name__ for g in server.TOOLS.values() for fn in g}
    assert len(names) == 13


# ---------------------------------------------------------------- tools
def test_risk_tools_match_engine(server):
    r = server.risk_size_position(100_000.0, 2_000.0, 25.0, "BUY")
    assert r["allowed"] and r["units"] == pytest.approx(20.0) and r["stop_loss_price"] == pytest.approx(1_950.0)
    assert server.risk_size_position(100_000.0, 2_000.0, 25.0, "BUY", current_drawdown_pct=0.09)["allowed"] is False
    s = server.risk_check_hard_stop("buy", 95.0, 110.0, 80.0, 81.0, 78.0)
    assert s["triggered"] and s["reason"] == "HARD_STOP" and s["exit_price"] == pytest.approx(80.0)


def test_hrp_tool(server):
    rng = np.random.default_rng(1)
    r = server.portfolio_hrp_weights({"A": list(rng.normal(0, 0.002, 200)), "B": list(rng.normal(0, 0.02, 200))})
    assert r["sum"] == pytest.approx(1.0) and r["weights"]["A"] > r["weights"]["B"]


def test_paper_simulation_and_sweep(server):
    sim = server.paper_simulation(bars=60, seed=3)
    assert sim["bars"] == 60 and sim["status"] in ("RUNNING", "CIRCUIT_BREAKER_TRIGGERED")
    rng = np.random.default_rng(2)
    closes = list(100 + np.cumsum(rng.normal(0, 0.5, 400)))
    sw = server.ma_cross_sweep(closes, [5, 10], [20, 40], fees_bps=6.0)
    assert sw["n_trials"] == 4 and len(sw["cells"]) == 4
    assert {"sharpe_median", "share_positive"} <= set(sw["population"])


def test_audit_tools(server, tmp_path):
    single = server.audit_deflated_sharpe(observed_sharpe=0.1, n_trials=1, n_obs=500)
    many = server.audit_deflated_sharpe(observed_sharpe=0.1, n_trials=200, n_obs=500)
    assert many["expected_max_sharpe_under_null"] > single["expected_max_sharpe_under_null"]
    assert many["deflated_sharpe_probability"] < single["deflated_sharpe_probability"]
    assert single["verdict"] == "PASS"

    leaky = tmp_path / "leaky.py"
    leaky.write_text("y = df['close'].shift(-1)\nz = df.rolling(5, center=True).mean()\n", encoding="utf-8")
    scan = server.audit_lookahead_scan(str(leaky))
    assert scan["count"] == 2 and {f["line"] for f in scan["findings"]} == {1, 2}
    assert server.audit_lookahead_scan(str(ROOT / "orchestration" / "risk"))["count"] == 0


def test_review_log_roundtrip(server, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REVIEWS_PATH", tmp_path / "reviews.jsonl")
    assert "error" in server.review_log("bot_x", "phase5", "maybe", "bad verdict")
    out = server.review_log("bot_x", "phase5", "not_evidence_yet", "K=200 trials, DSR 0.41")
    assert out["recorded"]
    recall = server.review_recall("bot_x")
    assert len(recall["reviews"]) == 1 and recall["reviews"][0]["verdict"] == "not_evidence_yet"


def test_openalgo_builder_never_sends(server):
    r = server.openalgo_build_order("BTC/USDT", "buy", 0.5, "LIMIT", 65_000.0)
    assert r["sent"] is False and r["body"]["symbol"] == "BTCUSDT" and r["body"]["pricetype"] == "LIMIT"
