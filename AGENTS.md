# Agent_Fund_Quant — Institutional Dual-Agent Quantitative Workspace

Institutional dual-agent quantitative research, multi-bot orchestration, and execution system engineered for the **Agent_Fund_Quant** repository.

---

## I. INTEGRATED INSTITUTIONAL QUANT LIBRARIES

The workspace embeds nine core quantitative repositories:

| Repository | Directory | Role & Specialized Focus |
|---|---|---|
| **ArcticDB** | `ArcticDB/` | Ultra-fast columnar DataFrame & tick/bar database (B-tree on LMDB/S3/NVMe). |
| **Nautilus Trader** | `nautilus_trader/` | High-frequency, event-driven backtest & live execution engine (Rust core, order book depth, explicit latency). |
| **QuantConnect LEAN** | `Lean/` | Institutional multi-asset event-driven engine (QCAlgorithm lifecycle, 5-model framework, reality models). |
| **Microsoft Qlib** | `qlib/` | AI-oriented alpha platform: Alpha158/Alpha360 expressions, GBDT models, MLflow recorders. |
| **vectorbt** | `vectorbt/` | Numba-accelerated vectorized backtesting, indicator factory, parameter grids, walk-forward splits. |
| **Riskfolio-Lib** | `Riskfolio-Lib/` | Institutional portfolio optimization: Hierarchical Risk Parity (HRP), CVaR/CDaR, Kelly criterion, Black-Litterman. |
| **MLFinLab** | `mlfinlab/` | Marcos López de Prado's machine learning finance toolset: Triple-barrier labeling, fractional differentiation, purged CV. |
| **RD-Agent** | `RD-Agent/` | Autonomous quantitative R&D agent framework for signal extraction and hypothesis evolution. |
| **OpenAlgo** | `openalgo/` | Multi-broker gateway, REST/WebSocket interfaces, order execution, and live trade operations. |

---

## II. THE DUAL-AGENT OPERATING SYSTEM

### 🏗️ Quant Builder (`quant-builder`)
- **Role**: Chief Quantitative Systems Engineer & Bot Builder
- **Triggers**: `@builder`, `/builder`, `build strategy`, `scaffold pod`, `optimize parameters`, `generate pipeline`, `deploy bot`
- **Responsibilities**:
  1. **Alpha Mining**: Triple-barrier labeling, fractional differentiation (MLFinLab), Qlib Alpha158/Alpha360 expressions.
  2. **Fast Screening**: Vectorized parameter sweeps via `vectorbt` with strict cost floors (>= 10 bps round-trip).
  3. **Event-Driven Parity**: Microstructure execution and fill validation on `NautilusTrader` and `Lean`.
  4. **Portfolio Allocation**: Sizing via `Riskfolio-Lib` (HRP, Risk Parity) and multi-pod capital allocation in `FleetOrchestrator`.
  5. **Production Deployment**: Pod execution via `orchestration/builder_core/`, CCXT/OpenAlgo gateway, state persistence (SQLite/Redis), and reconciliation loops.
- **Skills Owned**: `quant-builder`, `vectorbt-backtest`, `lean-algorithm-builder`, `qlib-alpha-mining`, `ml-for-trading`, `mindshub-orchestrator`, `quant-data-pipeline`, `alpha-research-workflow`, `portfolio-construction-risk`, `execution-costs-microstructure`, `live-deployment-monitoring`.
- **Rules File**: [`.agents/rules/quant_builder.md`](.agents/rules/quant_builder.md)

### 🎓 Quant Mentor (`quant-mentor`)
- **Role**: Chief Risk Officer (CRO), Lead Institutional Auditor & Quant Educator (Strictly Read-Only)
- **Triggers**: `@mentor`, `/mentor`, `audit strategy`, `check overfitting`, `deflated sharpe`, `lookahead bias`, `review risk`, `explain concept`
- **Responsibilities**:
  1. **6-Step Audit**: Provenance (PIT) $\to$ Timing (lag) $\to$ Costs ($\ge 10$ bps) $\to$ Selection ($K$ trials) $\to$ Significance (DSR/PBO) $\to$ Fragility (+1 bar lag, 2x cost, regime split).
  2. **7 Deadly Sins Enforcement**: Zero tolerance for lookahead bias, survivorship bias, or zero-cost simulations.
  3. **Central Risk Engine Oversight**: Aladdin-style VaR/CVaR limits, fleet-wide drawdown ladders, and soft/hard circuit breaker trips (`orchestration/mentor_core/`).
  4. **Syllabus Teaching**: Deep methodology education citing specific equations and repository source files (`file:line`).
  5. **Dispute Arbitration**: Rulings strictly governed by the Evidence Boundary.
- **Skills Owned**: `quant-mentor`, `backtest-risk-audit`, `awesome-quant-curator`, `ml-for-trading`, `qlib-alpha-mining`, `quant-data-pipeline`, `alpha-research-workflow`, `portfolio-construction-risk`, `execution-costs-microstructure`, `live-deployment-monitoring`.
- **Rules File**: [`.agents/rules/quant_mentor.md`](.agents/rules/quant_mentor.md)

---

## III. SUITE-WIDE NON-NEGOTIABLE GUARDS

1. **Transaction Cost Floor**: Minimum 5 bps fee + 5 bps slippage (10 bps round-trip). No friction-free claims.
2. **Zero Lookahead**: Signals at $t$ strictly use data knowable at $t-1$, or fills execute at $t+1$ open.
3. **Purged Walk-Forward CV**: Time series cross-validation must purge overlapping holding periods and include an embargo.
4. **Train-Only Transforms**: All scalers, rankers, and PCA models are fit solely on training folds.
5. **Sealed Holdout**: Out-of-sample holdouts are touched exactly once.
6. **Multiple Testing Control**: Every trial ($K$) is logged for Deflated Sharpe Ratio calculation.
7. **Crash-Resistant State**: All pods persist state per bar and reconcile against exchange balances periodically.

---

## IV. REPOSITORY ORCHESTRATION DUAL-CORE ARCHITECTURE

The repository code is organized into two symmetrical, institutional subsystems under `orchestration/`:

### 1. `builder_core/` — Alpha & Execution Subsystem
- **`feed/`**: `bar_feed.py`, `arctic_store.py` (PointInTimeStore, zero lookahead enforcement).
- **`pods/`**: `base_pod.py`, `sample_pod.py` (Isolated pod lifecycle & strategy logic).
- **`execution/`**: `ccxt_gateway.py` (CCXT execution & slippage bounds), `order_manager.py` (In-memory mark-to-market position tracker).
- **`allocation/`**: `portfolio_hrp.py` (Hierarchical Risk Parity dynamic pod weighting).
- **`fleet/`**: `fleet_orchestrator.py` (Multi-pod concurrent runner & fund exposure ledger).

### 2. `mentor_core/` — Risk, Oversight & Safeguards Subsystem
- **`risk_engine/`**: `central_risk.py` (Centralized Aladdin risk monitoring, portfolio VaR/CVaR, leverage caps).
- **`circuit_breakers/`**: `circuit_breaker.py` (Two-tier soft & hard circuit breaker state machines).
- **`persistence/`**: `state_store.py` (SQLite / Redis crash-recovery snapshots per bar/fill).
- **`reconciliation/`**: `reconciliation_loop.py` (Background worker preventing state drift against exchange balances).
- **`guards/`**: `rate_limit.py` (Token-bucket rate limiter & bounded exponential-backoff retries).
- **`telemetry/`**: `dispatcher.py` (Section IV JSONL audit log & TradingView marker emitter).

### 3. Backward-Compatibility Facades
For zero breaking changes across existing callers and test suites, legacy import paths (`orchestration.fleet_orchestrator`, `orchestration.data.*`, `orchestration.pod.*`, `orchestration.risk.*`, `orchestration.execution.*`, etc.) are fully maintained via transparent re-export facades.

---

## MCP TOOL LAYER (quant-builder / quant-mentor)

Both agents are MCP **clients**; the servers do not know which agent calls them, so the safety boundary is the tool list each agent is granted, generated from a single manifest.

| Piece | Location | Role |
|---|---|---|
| Manifest (source of truth) | `mcp/manifest.yaml` | Servers, quant-server tool groups (`read`, `build`, `audit`), per-agent grants, forbidden patterns |
| Generator | `mcp/generate_configs.py` | Writes `.mcp.json` (Claude Code), `.agents/mcp.json` (Antigravity / generic hosts) and the `MCP TOOL ACCESS` block in each agent file. `--check` fails when outputs drift. |
| quant-server | `mcp/quant_server/server.py` | 13 deterministic tools over `orchestration/`: Central Risk Engine sizing and hard stops, HRP/CVaR, point-in-time reads, paper simulation, declared-grid sweeps, Deflated Sharpe, look-ahead scan, review log |
| Reference servers | `mcp/servers/` (submodule of `modelcontextprotocol/servers`) | `filesystem`, `git`, `fetch`, `memory`; launched from the published packages via `npx` / `uvx` |

Grants: **quant-builder** = `read` + `build`, read-write filesystem. **quant-mentor** = `read` + `audit`, read-only filesystem. No MCP tool places, sends or cancels orders; `openalgo_build_order` only renders the request body.

```
python mcp/generate_configs.py          # after editing the manifest
python mcp/generate_configs.py --check  # CI guard
pytest tests/test_mcp_quant_server.py   # tool + boundary tests
```
