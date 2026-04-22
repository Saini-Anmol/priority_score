# Vector Supply Chain Intelligence System

### Modular In-Memory Architecture — V1

The **Requirement Summary** module is the core engine of the Vector Supply Chain Intelligence System. It consolidates raw demand signals, live machine deployment data, historical sales, and manual planner overrides into a single, prioritised daily production plan (`requirement_summary_DDMMYYYY.xlsx`) and pushes the same result to the `btp_requirement` MySQL table consumed by the front-end planning dashboard.

The pipeline is organised as five sequential in-memory stages chained by a single orchestrator — no intermediate Excel hand-offs, no disk I/O between stages — making each run fast, reproducible, and easy to reason about.

---

## 1. Key Capabilities

- **Unified Demand View** — fuses Buffer Order Report (BOR), Buffer Penetration Report (BPR), Book Management Report (BMR), Dispatch history, OE dispatch orders, and average-sales baselines into one ranked output.
- **Configurable Prioritisation** — every weight, threshold, multiplier, and default is driven by `config_input.xlsx` so business users can retune the model without touching Python.
- **Machine Deployment Awareness** — live Daily Mould Reports feed Proxy Penetration scoring, Critical-Gap detection, Excess-Production detection, Mould-Health alerts, and Ghost-SKU discovery.
- **Manual Override Integration (CPT)** — planner-entered demands from the `btp_demand_tracker` table are lifted above automated demand via a 4-step weighted scoring pipeline that guarantees manual SKUs rank first.
- **Yield Redistribution** — OE / EXP requirements are inflated by a yield factor, with the increase subtracted from the same SKU's RE row to prevent double-counting.
- **Dual Output** — identical data is written to Excel (for audit / local review) and pushed to MySQL (for the live dashboard) in one run.

---

## 2. Repository Layout

```
requirement_summary/
│
├── main.py                           # Entry point — prompts for date, launches orchestrator
├── create_config_excel.py            # One-time generator for config_input.xlsx
├── config_input.xlsx                 # Tunable business parameters (Stage1_Config sheet)
├── requirements.txt                  # Python dependencies
├── .env                              # Credentials & paths (DB_*, BASE_DATA_PATH)
│
├── V1/
│   ├── Routes/
│   │   └── btp_pipeline.py           # Orchestrator — chains Stages 1 → 5 in memory
│   │
│   ├── Reports/                      # Business-logic stages
│   │   ├── stage1_demand.py          # Demand scoring  (BOR + BPR + BMR + Dispatch + Curing)
│   │   ├── stage2_deployment.py      # Machine deployment & Ghost-SKU detection
│   │   ├── stage3_refinement.py      # Max-demand refinement with OE + avg-sales baselines
│   │   ├── stage4_manual.py          # CPT manual override & hybrid synthesis
│   │   └── stage5_yield.py           # Yield-factor adjustment & RE redistribution
│   │
│   ├── Setups/                       # Bootstrap layer
│   │   ├── config.py                 # Loads config_input.xlsx into typed constants
│   │   └── connection.py             # SQLAlchemy engine factory (reads .env)
│   │
│   └── Utilities/                    # Shared helpers
│       ├── data_loaders.py           # avg_sales.csv, oe_demand.csv, historical BOR
│       ├── math_utils.py             # minmax_normalize, extract_rim_size
│       ├── excel_writer.py           # Final .xlsx writer (+ history tabs)
│       └── db_writer.py              # TRUNCATE + INSERT upload to btp_requirement
│
├── data/                             # Input data root (path is overridable via .env)
│   ├── VectorData/                   # BOR / BPR / BMR / SPOR / Daily Mould Report
│   ├── DISPATCH1.csv                 # Dispatch transactions (ASP calculation)
│   ├── curing_cycletime.csv          # Per-SKU cure times (minutes)
│   ├── avg_sales.csv                 # Historical average sales baseline
│   ├── oe_demand.csv                 # Live OE dispatch orders
│   └── manual_frontend_demand.xlsx   # Legacy manual-demand Excel (fallback)
│
└── requirement_summary_<DDMMYYYY>.xlsx    # Generated output files
```

---

## 3. The 5-Stage Pipeline

The orchestrator [V1/Routes/btp_pipeline.py](V1/Routes/btp_pipeline.py) drives the stages below, passing the previous stage's DataFrame into the next — there is no intermediate Excel serialisation.

### Stage 1 — Demand Scoring
[V1/Reports/stage1_demand.py](V1/Reports/stage1_demand.py)

Consumes BOR, BPR, BMR, Dispatch, and Curing data and produces a base `ConsolidatedPriorityScore` for every (SKU, Market) row.

- **Requirement** = `max(0, Virtual Norm × Market Multiplier − Stock)`
- **Penetration** = `(Virtual Norm − Stock) / Virtual Norm × 100`  (always computed at 100% of Virtual Norm)
- **InventoryScore** — weighted sum of Black / Red hits across JIT, Depot, Depot Mobility, Feeder, PWH
- **PriorityScore** — linear combination of market weight, normalised penetration, normalised requirement, and Top-SKU flag
- **ASP** — market-aware Average Selling Price (OE channel vs. all-others channel) from `DISPATCH1.csv`
- **PriceScore** — normalised `ASP × daily_cure`, where `daily_cure = ceil(1440 / (CureTime + 2.5) × Efficiency)`
- **HistoryPenetrationScore** — streak of consecutive days where `Penetration ≥ HISTORY_PENETRATION_BLACK` (default 60%), computed *independently* per (SKU, Market) using the previous N days of BOR files; missing weekend / holiday files keep the streak intact.
- **ConsolidatedPriorityScore** — weighted blend of PriorityScore, Inventory, Price, and History Penetration scores (see `CONSOLIDATED_*` weights).

### Stage 2 — Machine Deployment Analysis
[V1/Reports/stage2_deployment.py](V1/Reports/stage2_deployment.py)

Merges Stage 1 with the Daily Mould Report.

- **MachineCount** — unique work-centres running the SKU
- **AvgMouldHealth** — mean of `Mould life / Target life` across running moulds
- **Proxy Penetration** = `ConsolidatedPriorityScore × (1 − 0.05 × MachineCount)` — penalises SKUs that are already saturated on machines
- **Ghost SKUs** — moulds running a SKU with zero Vector demand; injected as new rows with a score below the lowest real SKU. Their market is auto-corrected from `RE → OE` when they appear in `oe_demand.csv`.
- **Flags** — `CriticalGap` (top-50 rank with zero machines), `ExcessProduction` (rank > 200 with > 2 machines), `MouldAlert` (`AvgMouldHealth > 0.9`).

### Stage 3 — Max-Demand Refinement
[V1/Reports/stage3_refinement.py](V1/Reports/stage3_refinement.py)

Replaces Vector's raw `Requirement` with an `Updated_Requirement` that respects every demand signal available:

| Market | Rule |
|--------|------|
| `OE`   | `max(0, ceil(max(oe_demand[SKU] − Stock, Requirement − Stock)))` |
| `RE`   | `max(0, ceil(max(avg_sales[SKU, RE] − Stock, Requirement − Stock)))` |
| others | `ceil(Requirement)` (unchanged) |

The `oe_demand_qty` and `avg_sales_qty` reference values are also attached for audit transparency.

### Stage 4 — Manual Override & Hybrid Synthesis
[V1/Reports/stage4_manual.py](V1/Reports/stage4_manual.py)

Pulls pending rows from `jkplanningV1.btp_demand_tracker` (where `changesIncorporated = 0`) and scores them through a 4-step pipeline:

1. **`weighted_score`** = `W_MARKET × market_norm + W_QTY × qty_norm + W_TARGET_DATE × date_urgency_norm`  (weights 0.30 / 0.40 / 0.30)
2. **Pre-rank** rows with `HighestPriority = 1`
3. **`modified_priority_score`** — boost HP=1 rows by `max_weighted_score × (1 + rank / P)`
4. **`ConsolidationPriorityScore`** = `max_automated_score × (1 + overall_rank / N)` — ceiling-based lift that *guarantees every manual SKU sits above every automated SKU*

Manual rows supersede matching (SKU, Market) pairs from the automated set, then the two sets are concatenated. Final output order:

1. Manual SKUs with `HighestPriority = 1` (by `ConsolidationPriorityScore` desc)
2. Manual SKUs with `HighestPriority = 0` (by `ConsolidationPriorityScore` desc)
3. Automated SKUs (by `ProxyRank`)

### Stage 5 — Yield Factor Adjustment
[V1/Reports/stage5_yield.py](V1/Reports/stage5_yield.py)

For every `OE` / `EXP` row with positive `Updated_Requirement`:

- `Updated_Requirement ← ceil(Updated_Requirement / YIELD_FACTOR)`  (default 0.95)
- The resulting **increase** is subtracted from the same SKU's `RE` row (floored at 0) — unless the RE row is a CPT manual override, which is never touched.

---

## 4. Final Output

### 4.1  Excel — `requirement_summary_<DDMMYYYY>.xlsx`

Written by [V1/Utilities/excel_writer.py](V1/Utilities/excel_writer.py). Sheets:

| Sheet | Contents |
|-------|----------|
| `DDMMYYYY` (main) | Final ranked plan — 36 columns covering SKU identity, market, stock, vector / CPT / final requirements, penetration, deployment metrics, gap flags, revenue, yield, and the final `ConsolidatedPriorityScore` |
| `DD-MM-YYYY` (per-day history) | Raw BOR penetration for each of the last `HISTORY_PENETRATION_N` days, with `SKU Description` back-mapped from the main tab |

### 4.2  MySQL — `btp_requirement`

Written by [V1/Utilities/db_writer.py](V1/Utilities/db_writer.py). Strategy:

1. `TRUNCATE TABLE btp_requirement` — clears rows and resets auto-increment id (schema is **never** dropped)
2. Renames DataFrame columns to the DB schema via `_COLUMN_MAP`
3. Normalises BIT columns (`True/False → 1/0`) and coerces `Target Date → DATETIME`
4. Stamps `createdAt` and `createdBy = "AI Plan"`
5. Inserts with `pandas.to_sql(..., if_exists='append', chunksize=1000)`

---

## 5. Configuration

All tunable business logic lives in **`config_input.xlsx`** (sheet `Stage1_Config`). The file is loaded once at startup by [V1/Setups/config.py](V1/Setups/config.py); the `User_Input` column overrides the `Default_Value` column when non-empty.

| Group | Parameter examples | Purpose |
|-------|--------------------|---------|
| Market Weights        | `MARKET_WEIGHTS_OE=5`, `..._RE=1` | Priority of each market in base scoring |
| Market Priority       | `MARKET_PRIORITY_OE=1` | Tie-breaker ordering |
| Location Weights      | `LOCATION_WEIGHTS_JIT=5` | Inventory hit multiplier by location |
| Scoring Weightage     | `SCORING_penetration_weightage=0.35` | Mix of base PriorityScore components |
| Inventory Factors     | `INVENTORY_BLACK_FACTOR=2.0` | Severity multipliers for Black / Red |
| Norm Multipliers      | `RE_NORM_MULTIPLIER=1.0` | Strategic buffer-target scaling per market |
| Yield Factors         | `YIELD_FACTOR_OE=0.95` | Stage 5 OE / EXP yield assumption |
| Consolidated Weights  | `CONSOLIDATED_demand_priority=0.40` | Final score component mix |
| History Penetration   | `HISTORY_PENETRATION_N=10`, `..._BLACK=60.0` | Streak window and threshold |
| Defaults              | `EFFICIENCY_FACTOR=0.85`, `DEFAULT_ASP=2500`, `DEFAULT_CURE_TIME=20` | Fallbacks |

Stage 4 manual-scoring weights (`W_MARKET=0.30`, `W_QTY=0.40`, `W_TARGET_DATE=0.30`) live inline in `config.py` — change them there if the manual balance needs retuning.

Regenerate the template any time with:

```bash
python create_config_excel.py
```

---

## 6. Environment (.env)

Create a `.env` file at the module root with:

```ini
BASE_DATA_PATH=./data

DB_SERVER=<host-or-ip>
DB_DATABASE=jkplanningV1
DB_USERNAME=<user>
DB_PASSWORD=<password>
```

If any DB_* variable is missing the pipeline still runs — Stage 4 will raise, so the orchestrator falls back to an automated-only result and the MySQL upload step is skipped.

---

## 7. Input Data Contract

Paths are resolved relative to `BASE_DATA_PATH`.

| File | Format | Purpose | Required? |
|------|--------|---------|-----------|
| `Vectordata/BOR/BORColorBandwiseReport__DD-MM-YYYY.csv`            | CSV    | Buffer Order Report — Virtual Norm, Stock, Market | **Yes (Stage 1)** |
| `Vectordata/BPR/BufferPenetrationReport__DD-MM-YYYY.csv`           | CSV    | Buffer Penetration per (SKU, Location) — Black/Red bands | **Yes (Stage 1)** |
| `Vectordata/BMR/Prod_OverAll_BMReport__DD_MM_YYYY.xlsx`            | Excel  | Book Management — EXP demand, Pending CCR Qty | **Yes (Stage 1)** |
| `Vectordata/SPOR/Single_Production_Order_Report_DDMMYYYY.csv`      | CSV    | Single Production Orders | Optional |
| `Vectordata/Daily Mould Report/DDMMYYYY MouldDetails.csv`          | CSV    | Live mould / machine occupancy | Optional (Stage 2 warns & skips) |
| `DISPATCH1.csv`                                                    | CSV (latin-1) | Dispatch transactions → ASP | **Yes (Stage 1)** |
| `curing_cycletime.csv`                                             | CSV    | Per-SKU cure time (minutes) | **Yes (Stage 1)** |
| `avg_sales.csv`                                                    | CSV (latin-1) | Historical average sales per (SKU, Market) | **Yes (Stage 3)** |
| `oe_demand.csv`                                                    | CSV (latin-1) | Live OE dispatch plan | **Yes (Stage 3)** |

Previous N-day BOR files (controlled by `HISTORY_PENETRATION_N`) are expected in the same BOR folder for the streak calculation and history sheets.

---

## 8. Installation

```bash
# From the project root
cd requirement_summary

# (recommended) create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# One-time: generate the config template
python create_config_excel.py

# One-time: create .env with DB credentials & data path
# (see section 6)
```

---

## 9. Running the Pipeline

```bash
python main.py
```

You will be prompted for the target date in `DD.MM.YYYY` format. The orchestrator then logs each stage's progress, writes `requirement_summary_<DDMMYYYY>.xlsx`, and uploads the result to `btp_requirement` if the DB connection succeeded.

```
======================================================================
  Vector Supply Chain Intelligence System - BTP Pipeline
  Modular In-Memory Architecture (V1)
======================================================================

Enter date (DD.MM.YYYY): 07.04.2026

🚀 Initiating BTP Pipeline Orchestration for 07042026...
☁️ Initializing database connection...
[Stage 1] Processing raw demand signals …
[Stage 2] Starting deployment analysis …
[Stage 3] Running Max-Demand Refinement …
[Stage 4] Starting Manual Override Integration …
[Stage 5] Applying Yield Factor Adjustment …
💾 Formatting and writing final output to requirement_summary_07042026.xlsx …
  ✅ Data uploaded successfully to MySQL table 'btp_requirement'! (N rows)

✅ Pipeline executed successfully for 07.04.2026.
```

---

## 10. Design Notes

- **No intermediate files** — every stage receives and returns a `pandas.DataFrame`; disk is touched only once for the final Excel and once for the MySQL upload. This removes a historical class of bugs where a stale stage-N workbook silently fed stage N+1.
- **Config-first** — business levers (weights, thresholds, yields) are never hard-coded; every constant traces back to `config_input.xlsx` or `.env`.
- **Stage isolation** — each stage file imports only from `V1.Setups`, `V1.Utilities`, and the shared config. There are no cross-stage imports, making individual stages unit-testable in isolation.
- **Safe DB upload** — `TRUNCATE + INSERT` preserves schema, indexes, and foreign keys. The auto-increment `id` resets cleanly each run. BIT columns and DATETIME coercion are handled centrally so downstream consumers never see type surprises.
- **Graceful degradation** — missing optional inputs (SPOR, Daily Mould Report, DB credentials) emit warnings and skip the affected logic rather than aborting the run.

---

## 11. Dependencies

See [requirements.txt](requirements.txt).

- `pandas >= 2.0.0`
- `numpy >= 1.24.0`
- `openpyxl >= 3.1.2`
- `python-dotenv >= 1.0.0`
- `sqlalchemy >= 2.0.0`
- `pymysql` — required at runtime by the `mysql+pymysql://` connection string

Install with: `pip install -r requirements.txt pymysql`

---

## 12. Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `❌ ERROR: 'config_input.xlsx' not found` | Run `python create_config_excel.py` at the module root |
| `Stage 1 failed to generate demand data` | One of BOR / BPR / BMR is missing for that date — check the filename convention in Section 7 |
| `[WARN] Database credentials missing` | Populate all four `DB_*` variables in `.env`; the run continues but the MySQL upload is skipped |
| Manual rows not appearing in output | Confirm rows exist in `jkplanningV1.btp_demand_tracker` with `changesIncorporated = 0` |
| History tabs missing in Excel | Historical BOR files for those dates aren't in `Vectordata/BOR/` — the tab is skipped (weekend / holiday behaviour is intentional) |
| `Invalid YIELD_FACTOR` error in Stage 5 | `YIELD_FACTOR_OE` in the config must be `> 0` and `<= 1` |
