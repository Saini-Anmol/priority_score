# Vector Supply Chain Intelligence System

A three-stage manufacturing priority and deployment analysis engine that transforms raw demand, inventory, and machine data into a sequenced production action plan — fully automated with manual strategic override capability.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Data Directory Layout](#data-directory-layout)
- [Stage 1: Demand Prioritization](#stage-1-demand-prioritization)
- [Stage 2: Machine Deployment Analysis](#stage-2-machine-deployment-analysis)
- [Stage 3: Manual Strategic Override](#stage-3-manual-strategic-override)
- [Key Formulas](#key-formulas)
- [Column Reference](#column-reference)
- [Configuration](#configuration)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)

---

## Overview

The system processes daily manufacturing data through three sequential stages:

| Stage                                     | Module                            | Output File                           |
| ----------------------------------------- | --------------------------------- | ------------------------------------- |
| **Stage 1** – Demand Prioritization       | `demand_processor.py`             | `combined_data_output.xlsx`           |
| **Stage 2** – Machine Deployment Analysis | `deployment_processor.py`         | `deployment_analysis_report.xlsx`     |
| **Stage 3** – Manual Strategic Override   | `manual_integration_processor.py` | `final_hybrid_deployment_report.xlsx` |

Each stage enriches the data further. Stage 3 is the final, actionable production sequence delivered to the plant floor.

---

## Project Structure

```
Vector_Project/
├── config.py                      # Stage 1 configuration (reads config_input.xlsx)
├── config_stage2.py               # Stage 2 configuration (reads config_input.xlsx)
├── demand_processor.py            # Stage 1 processing logic
├── deployment_processor.py        # Stage 2 processing logic
├── manual_integration_processor.py# Stage 3 manual override logic
├── app.py                         # Stage 1 standalone runner
├── app_stage2.py                  # Stage 1 + 2 integrated runner
├── app_stage3.py                  # Stage 1 + 2 + 3 integrated runner (full pipeline)
├── create_config_excel.py         # One-time script to generate config_input.xlsx
├── config_input.xlsx              # Master configuration file (Excel)
├── requirements.txt               # Python dependencies
├── .gitignore
└── data/                          # Data directory (not tracked by git)
```

---

## Installation

### Prerequisites

- Python 3.8+
- pip

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/Saini-Anmol/priority_score.git
cd priority_score

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate the configuration Excel file (run once)
python create_config_excel.py
```

**Required packages:**

- `pandas >= 2.0.0`
- `numpy >= 1.24.0`
- `openpyxl >= 3.0.0`

---

## Data Directory Layout

```
data/
├── Vectordata/
│   ├── SPOR/                        # Single Production Order Reports
│   │   └── Single_Production_Order_Report_DDMMYYYY.csv
│   ├── BOR/                         # BOR Color Band Reports
│   │   └── BORColorBandwiseReport__DD-MM-YYYY.csv
│   ├── BMR/                         # BM Reports (Export market data)
│   │   └── Prod_OverAll_BMReport__DD_MM_YYYY.xlsx
│   ├── BPR/                         # Buffer Penetration Reports
│   │   └── BufferPenetrationReport__DD-MM-YYYY.csv
│   └── Daily Mould Report/          # Stage 2 mould data
│       └── DDMMYYYY MouldDetails.csv
├── DISPATCH1.csv                    # Static dispatch data (ASP source)
├── curing_cycletime.csv             # Static curing cycle times per SKU
└── manual_frontend_demand.xlsx      # Stage 3 manual override input
```

---

## Stage 1: Demand Prioritization

**Runner:** `python app.py` or `python app_stage2.py` or `python app_stage3.py`

Stage 1 reads four daily reports and two static files per date to produce a ranked list of SKUs by production urgency.

### Input Files (per date)

| File                                          | Source | Purpose                                   |
| --------------------------------------------- | ------ | ----------------------------------------- |
| `BORColorBandwiseReport__DD-MM-YYYY.csv`      | BOR    | OE / RE / ST demand, stock, norms         |
| `Prod_OverAll_BMReport__DD_MM_YYYY.xlsx`      | BMR    | Export (EXP) market demand                |
| `BufferPenetrationReport__DD-MM-YYYY.csv`     | BPR    | Inventory color (Red/Black) by location   |
| `Single_Production_Order_Report_DDMMYYYY.csv` | SPOR   | (loaded, available for extension)         |
| `DISPATCH1.csv`                               | Static | Average Selling Price (ASP) per SKU       |
| `curing_cycletime.csv`                        | Static | Cure time per SKU for revenue calculation |

### Processing Flow

```
BOR / BMR  →  Strategic Norm Adjustment  →  PriorityScore (demand)
BPR        →  PriorityScore_Inventory
DISPATCH   →  ASP
Curing     →  daily_cure  →  rev_pot  →  price_priority

PriorityScore + NormInventoryScore  →  ConsolidatedPriorityScore  (Tier 1)
PriorityScore + NormInventoryScore + price_priority  →  ConsolidatedPriorityScore_p  (Tier 2)
```

### Output

**File:** `combined_data_output.xlsx` — one sheet per date processed.

---

## Stage 2: Machine Deployment Analysis

**Runner:** `python app_stage2.py` or `python app_stage3.py`

Stage 2 cross-references Stage 1 output with the Daily Mould Report to identify manufacturing gaps and calculate adjusted priorities.

### Input Files (per date)

- All Stage 1 inputs (see above)
- `DDMMYYYY MouldDetails.csv` — mould health and machine assignment data

### Key Concepts

| Concept               | Meaning                                                   |
| --------------------- | --------------------------------------------------------- |
| **Ghost SKU**         | A SKU running on machines but absent from Vector demand   |
| **Critical Gap**      | High-priority SKU (rank ≤ 50) with zero machines assigned |
| **Excess Production** | Low-priority SKU (rank > 200) consuming > 2 machines      |
| **Mould Alert**       | SKU whose average mould health > 90% of target life       |

### Output

**File:** `deployment_analysis_report.xlsx` — Stage 1 columns + deployment metrics.

---

## Stage 3: Manual Strategic Override

**Runner:** `python app_stage3.py`

Stage 3 allows production planners to inject manual SKU demands that **always outrank** the automated output. Manual entries are immune to the overstock penalty.

### Manual Input File

**File:** `data/manual_frontend_demand.xlsx`

| Column             | Type         | Description                  |
| ------------------ | ------------ | ---------------------------- |
| `SKU Code`         | string       | SKU identifier               |
| `SKU Description`  | string       | Optional description         |
| `Market`           | string       | OE / ST / EXP / RE           |
| `Quantity`         | number       | Required production quantity |
| `Highest Priority` | int (0 or 1) | 1 = absolute top of queue    |

### Processing Flow

```
Manual entries  →  Super-Boost Score  →  sorted at top
Stage 2 output  →  automated rows below (ProxyRank offset)
Both merged     →  StrategicPriorityScore  →  Overstock Penalty  →  Final Rank
```

### Output

**File:** `final_hybrid_deployment_report.xlsx` — complete hybrid report with `Final Rank` as the first column.

---

## Key Formulas

This section documents the exact formulas used for every important derived column.

---

### Stage 1 Formulas

#### `Adjusted_Target`

Strategic norm adjustment based on market type. RE (Replacement) market uses 50% of Virtual Norm to reflect the strategic de-prioritization of replacement buffers.

```
Adjusted_Target = Virtual Norm × 0.5    (if Market == 'RE')
Adjusted_Target = Virtual Norm × 1.0    (if Market == 'OE', 'ST', or 'EXP')
```

> **Note:** For EXP (Export) data from BMR, `Adjusted_Target` is `NaN` because BMR does not provide a Virtual Norm. BMR's Requirement and Penetration are taken as-is.

---

#### `Requirement`

Pending unfulfilled demand. Cannot go negative.

```
Requirement = max(0,  Adjusted_Target − Stock)
```

---

#### `Penetration`

Percentage of the adjusted target that has been depleted from stock. Values > 100% indicate overstock.

```
Penetration = (Adjusted_Target − Stock) / Adjusted_Target × 100

             = 0    (if Adjusted_Target == 0, to avoid division by zero)
```

---

#### `NormPenetration` / `NormRequirement`

Min-max normalisation across all SKUs in the same date batch, so each metric contributes equally to the score regardless of scale.

```
NormPenetration  = Penetration  / max(Penetration)   [across all SKUs]
NormRequirement  = Requirement  / max(Requirement)   [across all SKUs]
```

---

#### `PriorityScore_Inventory`

Weighted count of Red and Black stockout indicators across warehouse location types.

```
PriorityScore_Inventory = Σ  [BlackCount(loc) × LocationWeight(loc)
                              + RedCount(loc) × LocationWeight(loc) × 0.5]
```

**Location Weights (default):**

| Location       | Weight |
| -------------- | ------ |
| JIT            | 5      |
| Depot          | 4      |
| Depot Mobility | 3      |
| Feeder         | 2      |
| PWH            | 1      |

> Black stockouts are weighted at full location weight. Red stockouts are weighted at **50%** of the location weight (warning state, not critical).

---

#### `PriorityScore` (Demand Score)

Composite demand urgency score. Uses normalized sub-scores so that a raw large quantity doesn't dominate unfairly.

```
PriorityScore = (MarketWeight        × market_weightage)     [default: 0.25]
              + (NormPenetration     × penetration_weightage) [default: 0.35]
              + (NormRequirement     × requirement_weightage) [default: 0.30]
              + (TopSKUFlag          × top_sku_weightage)     [default: 0.10]
```

**Market Weights (default):**

| Market | Weight | Description                           |
| ------ | ------ | ------------------------------------- |
| OE     | 4      | Original Equipment — highest priority |
| ST     | 3      | Stock Transfer                        |
| EXP    | 2      | Export                                |
| RE     | 1      | Replacement — lowest priority         |

**TopSKUFlag:** `1` if the SKU is flagged as a Top SKU in the BPR report, else `0`.

---

#### `NormInventoryScore`

Normalises the raw inventory score to the same [0, 1] range as `PriorityScore`.

```
NormInventoryScore = PriorityScore_Inventory / max(PriorityScore_Inventory)  [across all SKUs]
```

---

#### `ConsolidatedPriorityScore` — **Tier 1**

Balances demand urgency with inventory criticality. Used as the primary ranking score.

```
ConsolidatedPriorityScore = (PriorityScore      × TIER1_demand_priority)    [default: 0.60]
                          + (NormInventoryScore  × TIER1_inventory_priority) [default: 0.40]
```

---

#### `daily_cure` (Daily Machine Capacity per SKU)

Number of tires a single machine can cure in a full 24-hour day, accounting for an efficiency factor.

```
daily_cure = ⌈ (1440 minutes / (Cure Time + 2.5)) × EFFICIENCY_FACTOR ⌉
```

> `+2.5` minutes accounts for the standard loading/unloading buffer added to every cycle.

---

#### `rev_pot` (Revenue Potential)

Daily revenue a single machine generates for this SKU.

```
rev_pot = ASP × daily_cure
```

> `ASP` (Average Selling Price) is computed from DISPATCH1.csv as `Amt.in loc.cur. / Quantity` per material, averaged over all dispatches for Plant 1300. Default ASP is used when no dispatch history exists for a SKU.

---

#### `price_priority`

Normalised revenue potential.

```
price_priority = rev_pot / max(rev_pot)   [across all SKUs]
```

---

#### `ConsolidatedPriorityScore_p` — **Tier 2**

Adds revenue potential to the Tier 1 score. Balances urgency with financial value.

```
ConsolidatedPriorityScore_p = (PriorityScore      × TIER2_demand_priority)    [default: 0.40]
                            + (NormInventoryScore  × TIER2_inventory_priority) [default: 0.30]
                            + (price_priority      × TIER2_price_priority)     [default: 0.30]
```

---

#### `size`

Rim size extracted from the SKU code.

```
size = characters at position [8:10] of SKUCode  (converted to integer)
```

---

### Stage 2 Formulas

#### `MouldHealth` (per machine row)

```
MouldHealth = Mould life / Target life
```

#### `AvgMouldHealth` (per SKU)

```
AvgMouldHealth = mean(MouldHealth)  across all machines running this SKU
```

#### `MachineCount` (per SKU)

```
MachineCount = count of unique machine names (WCNAME) running this SKU
```

#### `ProxyPenetration`

Adjusts the Tier 1 priority score downward for SKUs already in active production. More machines running = lower urgency.

```
penalty_factor   = max(0,  1 − (MachineCount × MACHINE_COUNT_PENALTY))   [default penalty: 0.05]
ProxyPenetration = ConsolidatedPriorityScore × penalty_factor
```

**Example:** A SKU running on 4 machines gets a penalty factor of `1 − (4 × 0.05) = 0.80`, so its Proxy score is 80% of its original priority.

#### `ProxyRank`

Re-ranks all SKUs based on `ProxyPenetration` (descending). Lower rank = higher urgency after deployment adjustment.

---

#### Gap Flags

| Flag               | Formula                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| `CriticalGap`      | `Rank_ConsolidatedPriorityScore ≤ CRITICAL_GAP_RANK` **AND** `MachineCount == 0`                        |
| `ExcessProduction` | `Rank_ConsolidatedPriorityScore > EXCESS_PRODUCTION_RANK` **AND** `MachineCount > EXCESS_MACHINE_COUNT` |
| `MouldAlert`       | `AvgMouldHealth > MOULD_LIFE_THRESHOLD`                                                                 |

**Defaults:** `CRITICAL_GAP_RANK = 50`, `EXCESS_PRODUCTION_RANK = 200`, `EXCESS_MACHINE_COUNT = 2`, `MOULD_LIFE_THRESHOLD = 0.9`

---

### Stage 3 Formulas

#### `ManualPriorityScore` (Super-Boost)

Assigns a score guaranteed to exceed any automated Tier 2 score (automated max ≈ 1.0).

```
ManualPriorityScore = BOOST_BASE + (HighestPriority × BOOST_MULTIPLIER)
                    = 10.0      + (1 or 0           × 1.0)
```

| `HighestPriority` | `ManualPriorityScore` | Effect                                              |
| ----------------- | --------------------- | --------------------------------------------------- |
| 1                 | 11.0                  | Absolute top of queue                               |
| 0                 | 10.0                  | Top of manual block, below Highest Priority entries |

---

#### `StrategicPriorityScore` (Unified Score)

A single consolidated score for the entire hybrid report regardless of source.

```
StrategicPriorityScore = ManualPriorityScore          (if Source == 'Manual')
                       = ConsolidatedPriorityScore_p   (if Source == 'Automated')
```

---

#### Overstock Penalty

SKUs with `Penetration > 100%` (already overstocked) are moved to the bottom of the report. **Manual entries are immune.**

```
is_overstock = (Penetration > 100%) AND (Source != 'Manual')

StrategicPriorityScore[is_overstock] = StrategicPriorityScore × OVERSTOCK_PENALTY_FACTOR
                                     = 0  (default → collapses to zero, always last)
```

Overstock rows are then sorted by `Penetration ascending` (least overstocked first within the penalty partition).

---

#### `Final Rank`

Continuous integer sequence (1, 2, 3, …) assigned after all sorting and penalties are applied. This is the definitive production sequence.

```
Final Rank = row index + 1   (after all sorting is complete)
```

---

## Column Reference

### Group 0 — Primary Sequence

| Column       | Description                                                  |
| ------------ | ------------------------------------------------------------ |
| `Final Rank` | **Stage 3 only.** The definitive production sequence number. |

### Group 1 — Identification

| Column            | Description                                 |
| ----------------- | ------------------------------------------- |
| `SKUCode`         | Unique product identifier                   |
| `SKU Description` | Human-readable product name                 |
| `size`            | Rim size extracted from SKUCode (chars 8–9) |

### Group 2 — Source & Override (Stage 3)

| Column                   | Description                                       |
| ------------------------ | ------------------------------------------------- |
| `Source`                 | `Manual` or `Automated`                           |
| `HighestPriority`        | `1` = flagged as highest priority in manual input |
| `ManualPriorityScore`    | Super-Boost score (10.0 or 11.0)                  |
| `ManualRank`             | Rank within manual block only                     |
| `StrategicPriorityScore` | Unified score used for final sorting              |

### Group 3 — Targets

| Column            | Description                                                  |
| ----------------- | ------------------------------------------------------------ |
| `Market`          | `OE`, `ST`, `EXP`, or `RE`                                   |
| `Norm `           | Original production norm                                     |
| `Virtual Norm`    | Adjusted norm used as baseline                               |
| `Adjusted_Target` | Virtual Norm × market multiplier (0.5 for RE, 1.0 otherwise) |

### Group 4 — Demand Signals

| Column               | Description                                           |
| -------------------- | ----------------------------------------------------- |
| `Stock`              | Current on-hand stock                                 |
| `Vector_Requirement` | Stage 1/2 automated requirement (before any override) |
| `CPT_Requirement`    | Manual override quantity (Stage 3 only)               |
| `Requirement`        | Final requirement used for calculations               |
| `Penetration`        | `(Adjusted_Target − Stock) / Adjusted_Target × 100`   |
| `NormPenetration`    | `Penetration / max(Penetration)`                      |
| `NormRequirement`    | `Requirement / max(Requirement)`                      |

### Group 5 — SKU Attributes

| Column         | Description                                                                |
| -------------- | -------------------------------------------------------------------------- |
| `Top SKU`      | `T` if flagged as a Top SKU in BPR, else blank                             |
| `TopSKUFlag`   | Binary: `1` if Top SKU, else `0`                                           |
| `MarketWeight` | Numeric weight for market (OE=4, ST=3, EXP=2, RE=1)                        |
| `priority`     | Sortable tuple: `(−MarketWeight, −Penetration, −Requirement, −TopSKUFlag)` |

### Group 6 — Inventory Signals

| Column                    | Description                                              |
| ------------------------- | -------------------------------------------------------- |
| `PriorityScore_Inventory` | Weighted sum of Red/Black stockouts across all locations |
| `NormInventoryScore`      | `PriorityScore_Inventory / max(PriorityScore_Inventory)` |

### Group 7 — Deployment Metrics & Flags (Stage 2+)

| Column             | Description                                                       |
| ------------------ | ----------------------------------------------------------------- |
| `MachineCount`     | Number of unique machines currently running this SKU              |
| `AvgMouldHealth`   | Average `Mould life / Target life` across all assigned machines   |
| `ProxyPenetration` | `ConsolidatedPriorityScore × max(0, 1 − MachineCount × 0.05)`     |
| `ProxyRank`        | Rank based on `ProxyPenetration` descending                       |
| `CriticalGap`      | `True` if high-priority (rank ≤ 50) and `MachineCount == 0`       |
| `ExcessProduction` | `True` if low-priority (rank > 200) and `MachineCount > 2`        |
| `MouldAlert`       | `True` if `AvgMouldHealth > 0.9`                                  |
| `IsGhostSKU`       | `True` for SKUs running on machines but absent from Vector demand |

### Group 8 — Revenue & Efficiency

| Column           | Description                                                                    |
| ---------------- | ------------------------------------------------------------------------------ |
| `ASP`            | Average Selling Price from dispatch data (₹ per unit)                          |
| `Cure Time`      | Curing cycle time from static file (minutes)                                   |
| `daily_cure`     | `⌈(1440 / (Cure Time + 2.5)) × Efficiency_Factor⌉` — units per day per machine |
| `rev_pot`        | `ASP × daily_cure` — daily revenue potential per machine (₹)                   |
| `price_priority` | `rev_pot / max(rev_pot)` — normalised revenue score                            |

### Group 9 — Scoring & Ranking

| Column                             | Description                                                                  |
| ---------------------------------- | ---------------------------------------------------------------------------- |
| `PriorityScore`                    | Demand-only score: weighted sum of market, penetration, requirement, top SKU |
| `ConsolidatedPriorityScore`        | **Tier 1:** `PriorityScore × 0.6 + NormInventoryScore × 0.4`                 |
| `Rank_ConsolidatedPriorityScore`   | Tier 1 rank (lower = higher priority)                                        |
| `ConsolidatedPriorityScore_p`      | **Tier 2:** Tier 1 + revenue component                                       |
| `Rank_ConsolidatedPriorityScore_p` | Tier 2 rank (lower = higher priority)                                        |

---

## Configuration

All parameters are stored in `config_input.xlsx`. Run `python create_config_excel.py` once to generate this file, then edit it as needed. **No code changes are required to tune the system.**

### Stage 1 Config (`Stage1_Config` sheet)

| Parameter                         | Default | Description                           |
| --------------------------------- | ------- | ------------------------------------- |
| `MARKET_WEIGHTS_OE`               | 4       | OE market weight                      |
| `MARKET_WEIGHTS_ST`               | 3       | ST market weight                      |
| `MARKET_WEIGHTS_EXP`              | 2       | EXP market weight                     |
| `MARKET_WEIGHTS_RE`               | 1       | RE market weight                      |
| `LOCATION_WEIGHTS_JIT`            | 5       | JIT warehouse weight                  |
| `LOCATION_WEIGHTS_Depot`          | 4       | Depot weight                          |
| `LOCATION_WEIGHTS_Depot_Mobility` | 3       | Depot Mobility weight                 |
| `LOCATION_WEIGHTS_Feeder`         | 2       | Feeder weight                         |
| `LOCATION_WEIGHTS_PWH`            | 1       | PWH weight                            |
| `SCORING_market_weightage`        | 0.25    | Market % in PriorityScore             |
| `SCORING_penetration_weightage`   | 0.35    | Penetration % in PriorityScore        |
| `SCORING_requirement_weightage`   | 0.30    | Requirement % in PriorityScore        |
| `SCORING_top_sku_weightage`       | 0.10    | Top SKU % in PriorityScore            |
| `TIER1_demand_priority`           | 0.60    | Demand % in Tier 1 score              |
| `TIER1_inventory_priority`        | 0.40    | Inventory % in Tier 1 score           |
| `TIER2_demand_priority`           | 0.40    | Demand % in Tier 2 score              |
| `TIER2_inventory_priority`        | 0.30    | Inventory % in Tier 2 score           |
| `TIER2_price_priority`            | 0.30    | Revenue % in Tier 2 score             |
| `EFFICIENCY_FACTOR`               | 0.85    | Machine efficiency for daily_cure     |
| `DEFAULT_ASP`                     | 3000    | Fallback ASP when no dispatch history |
| `DEFAULT_CURE_TIME`               | 20      | Fallback cure time (minutes)          |

### Stage 2 Config (`Stage2_Config` sheet)

| Parameter                | Default | Description                                   |
| ------------------------ | ------- | --------------------------------------------- |
| `MACHINE_COUNT_PENALTY`  | 0.05    | Priority reduction per running machine (5%)   |
| `CRITICAL_GAP_RANK`      | 50      | Rank threshold for Critical Gap flag          |
| `EXCESS_PRODUCTION_RANK` | 200     | Rank threshold for Excess Production flag     |
| `EXCESS_MACHINE_COUNT`   | 2       | Machine count threshold for Excess Production |
| `MOULD_LIFE_THRESHOLD`   | 0.9     | Mould health % that triggers an alert         |

---

## Usage

### Run Full Pipeline (Stages 1 + 2 + 3)

```bash
python app_stage3.py
```

You will be prompted for:

- **Analysis date** (DD.MM.YYYY)

Output: `final_hybrid_deployment_report.xlsx`

### Run Stage 1 + 2 Only

```bash
python app_stage2.py
```

Output: `deployment_analysis_report.xlsx`

### Run Stage 1 Only (date range)

```bash
python app.py
```

You will be prompted for:

- **Start date** (DD.MM.YYYY)
- **End date** (DD.MM.YYYY)

Output: `combined_data_output.xlsx` (one sheet per date)

---

## Troubleshooting

| Problem                             | Cause                                 | Fix                                                                                |
| ----------------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------- |
| `config_input.xlsx not found`       | Config file not generated             | Run `python create_config_excel.py`                                                |
| `Missing files` warning for a date  | Input CSVs/XLSXs absent for that date | Check file naming and the `data/` directory structure                              |
| All SKUs show `MachineCount = 0`    | Mould report file not found           | Verify `DDMMYYYY MouldDetails.csv` exists in `data/Vectordata/Daily Mould Report/` |
| Empty merge results                 | SKUCode type mismatch                 | All SKUCode columns are auto-cast to `str` — check source file encoding            |
| Manual entries not appearing at top | `manual_frontend_demand.xlsx` missing | Create `data/manual_frontend_demand.xlsx` with required columns                    |

---

_Built for optimizing manufacturing operations through data-driven insights._
