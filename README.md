# Vector Supply Chain Intelligence System

A three-stage manufacturing priority and deployment analysis engine that transforms raw demand, inventory, and machine data into a sequenced production action plan — fully automated with manual strategic override capability.

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Data Directory Layout](#data-directory-layout)
- [Stage 1: Demand Prioritization](#stage-1-demand-prioritization)
- [Stage 2: Frontend / Manual Integration](#stage-2-frontend--manual-integration)
- [Stage 3: Manual Strategic Override (Hybrid Synthesis)](#stage-3-manual-strategic-override-hybrid-synthesis)
- [Key Formulas](#key-formulas)
- [Column Reference](#column-reference)
- [Configuration](#configuration)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)

---

## Overview

The system processes daily manufacturing data through three sequential stages:

| Stage                                            | Module                            | Output File                                      |
| ------------------------------------------------ | --------------------------------- | ------------------------------------------------ |
| **Stage 1** – Demand Prioritization              | `demand_processor.py`             | `combined_vector_demand_<DDMMYYYY>.xlsx`         |
| **Stage 2** – Frontend / Manual Integration      | `frontend_processor.py`           | `vector_frontend_demand_<DDMMYYYY>.xlsx`         |
| **Stage 3** – Manual Strategic Override (Hybrid) | `manual_integration_processor.py` | `vector_frontend_running_demand_<DDMMYYYY>.xlsx` |

Each stage enriches the data further. Stage 3 is the final, actionable production sequence delivered to the plant floor.

> **Design note:** `deployment_processor.py` continues to run as a background component inside Stage 3 to compute mould health metrics (`MachineCount`, `AvgMouldHealth`, `ProxyPenetration`, etc.). It is no longer a standalone Stage 2 output module.

---

## Project Structure

```
Vector_Project/
├── config.py                       # Stage 1 configuration (reads config_input.xlsx)
├── config_stage2.py                # Stage 2 / 3 shared scoring configuration
├── demand_processor.py             # Stage 1 processing logic
├── frontend_processor.py           # Stage 2 manual integration engine
├── deployment_processor.py         # Mould/machine analysis (used as Stage 3 input)
├── manual_integration_processor.py # Stage 3 hybrid synthesis engine
├── app.py                          # Stage 1 standalone runner
├── app_stage2.py                   # Stage 1 + 2 integrated runner
├── app_stage3.py                   # Full pipeline runner (Stage 1 + 2 + 3)
├── create_config_excel.py          # One-time script to generate config_input.xlsx
├── config_input.xlsx               # Master configuration file (Excel)
├── PROCESS_DOCUMENTATION.md        # Detailed process & formula documentation
├── requirements.txt                # Python dependencies
├── .gitignore
├── CTP/                            # CTP (Cure Time Process) reference data
│   ├── SKU_List.xlsx               # CTP SKU master list
│   ├── cure_cycletime 1.xlsx       # Cure cycle time reference
│   └── vector_data_split/         # Split vector data for CTP processing
└── data/                           # Data directory (not tracked by git)
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
│   └── Daily Mould Report/          # Stage 3 mould data
│       └── DDMMYYYY MouldDetails.csv
├── DISPATCH1.csv                    # Static dispatch data (ASP source)
├── curing_cycletime.csv             # Static curing cycle times per SKU
└── manual_frontend_demand.xlsx      # Stage 2 & 3 manual override input
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
BOR / BMR  →  Strategic Norm Adjustment (config multipliers)  →  PriorityScore (demand)
BPR        →  PriorityScore_Inventory
BOR hist.  →  HistoryPenetrationScore (consecutive black streak, last N days)
DISPATCH   →  ASP  (grouped by Material × Market_Group)
Curing     →  daily_cure  →  rev_pot  →  price_priority

PriorityScore + NormInventoryScore + price_priority + NormHistoryPenetrationScore
    →  ConsolidatedPriorityScore
```

### Output

**File:** `combined_vector_demand_<DDMMYYYY>.xlsx` — one sheet per date processed (end date used in filename).

---

## Stage 2: Frontend / Manual Integration

**Runner:** `python app_stage2.py` or `python app_stage3.py`  
**Module:** `frontend_processor.py`

Stage 2 merges manually-entered CPT (Customer/Planner) demand from `manual_frontend_demand.xlsx` with the Stage 1 automated output. Manual entries are scored using a principled **4-step weighted pipeline** and are guaranteed to outrank all automated SKUs.

> **Output filename:** `vector_frontend_demand_<DDMMYYYY>.xlsx` — date-stamped per run.

### Manual Input File

**File:** `data/manual_frontend_demand.xlsx`

| Column             | Type         | Description                                    |
| ------------------ | ------------ | ---------------------------------------------- |
| `SKU Code`         | string       | SKU identifier                                 |
| `SKU Description`  | string       | Optional description                           |
| `Market`           | string       | OE / OE10 / ST / EXP / OTR / RE                |
| `Quantity`         | number       | Required production quantity (CPT demand)      |
| `Target Date`      | date         | When this quantity is needed (defaults: today) |
| `Highest Priority` | int (0 or 1) | 1 = absolute top of queue                      |

### 4-Step Manual Scoring Pipeline

```
Step 1 — weighted_score
    Weighted sum of three min-max normalised inputs:
        market_score  (from MARKET_SCORE map in config_stage2.py)
        quantity      (larger qty = more urgent)
        target_date   (closer date = more urgent, inverted)

    weighted_score = W_MARKET × norm_market
                   + W_QTY    × norm_qty
                   + W_DATE   × (1 − norm_days_remaining)
    Range: [0, 1]

Step 2 — Identify HighestPriority = 1 sub-group
    Rank HP=1 rows by weighted_score ASCENDING within the HP=1 block.
    rank 1 = lowest ws (smallest boost); rank P = highest ws (largest boost).

Step 3 — modified_priority_score
    max_ws = max(weighted_score) across ALL manual rows.
    For HP=1 rows:
        modified_priority_score = max_ws × (1 + priority_rank / P)
        Range: (max_ws, 2 × max_ws]  → always above ALL HP=0 scores
    For HP=0 rows:
        modified_priority_score = weighted_score  (unchanged)

Step 4 — ConsolidationPriorityScore  (FINAL STAGE 2 SCORE)
    overall_rank = rank by modified_priority_score ASCENDING
                   (rank 1 = lowest, rank N = most urgent)
    max_auto = max(ConsolidatedPriorityScore) from Stage 1 automated rows
    ConsolidationPriorityScore = max_auto × (1 + overall_rank / N)
    Range: (max_auto, 2 × max_auto]  → all manual rows above all automated rows ✓
```

### Supersede Logic

Manual entries supersede automated rows using a **(SKUCode, Market)** composite key:

- A `Govt`-market manual entry does **not** remove `RE` or `OE` automated rows for the same SKU.
- If the manual `Quantity` equals the automated `Requirement` for the same (SKU, Market), **both rows are kept** side by side.

### Output Column Structure (A → Z)

| Group                   | Columns                                                                           | Description                          |
| ----------------------- | --------------------------------------------------------------------------------- | ------------------------------------ |
| **A** — Rank            | `Rank_ConsolidationPriorityScore`                                                 | Final Stage 2 rank (1 = most urgent) |
| **B–D** — ID            | `SKUCode`, `SKU Description`, `size`                                              | SKU identity                         |
| **E–H** — Inputs        | `Source`, `HighestPriority`, `Target Date`, `Quantity`                            | Manual inputs                        |
| **I–K** — Intermediates | `weighted_score`, `modified_priority_score`, `manual_rank`                        | Scoring steps                        |
| **L** — Market          | `Market`                                                                          | Market segment                       |
| **M–O** — Targets       | `Norm`, `Virtual Norm`, `Adjusted_Target`                                         | Production norms                     |
| **P–V** — Demand        | `Stock`, `Vector_Requirement`, `CPT_Requirement`, `Requirement`, `Penetration`... | Demand signals                       |
| **W–Y** — Attributes    | `TopSKUFlag`, `MarketWeight`, `priority`                                          | SKU attributes                       |
| **Z–AA** — Inventory    | `PriorityScore_Inventory`, `NormInventoryScore`                                   | Inventory signals                    |
| **AB–AC** — History     | `HistoryPenetrationScore`, `NormHistoryPenetrationScore`                          | Black-day streak                     |
| **AD–AF** — Revenue     | `ASP`, `Cure Time`, `price_priority`                                              | Revenue efficiency                   |
| **AG** — Stage 1 Score  | `PriorityScore`                                                                   | Raw Stage 1 demand score             |
| **AH ✅** — Final       | `ConsolidationPriorityScore`                                                      | **Canonical Stage 2 final score**    |

**File:** `vector_frontend_demand_<DDMMYYYY>.xlsx`

---

## Stage 3: Manual Strategic Override (Hybrid Synthesis)

**Runner:** `python app_stage3.py`  
**Module:** `manual_integration_processor.py`

Stage 3 uses the **same 4-step weighted pipeline** as Stage 2 to score manual entries, ensuring full consistency. It additionally attaches mould/machine deployment metrics from `deployment_processor.py`.

> **Output filename:** `vector_frontend_running_demand_<DDMMYYYY>.xlsx` — date-stamped per run.

### Processing Flow

```
Stage 2 output  →  max_auto = max(ConsolidatedPriorityScore)
Manual entries  →  4-step weighted scoring (identical to Stage 2)
                →  ConsolidationPriorityScore > max_auto (guaranteed)

Supersede automated rows by (SKUCode, Market) match
Attach mould metrics (MachineCount, AvgMouldHealth) to manual rows
Set Penetration = 100.0 for all manual rows (fully buffer-depleted)
Concat manual + automated  →  sort by ConsolidationPriorityScore DESC
Final Rank = row index + 1
```

### Final Output Order (guaranteed)

```
1st  →  Manual SKUs with HighestPriority = 1  (ordered by ConsolidationPriorityScore desc)
2nd  →  Manual SKUs with HighestPriority = 0  (ordered by ConsolidationPriorityScore desc)
3rd  →  Automated SKUs                         (ordered by ConsolidationPriorityScore desc)
```

### Output Column Structure (A → AT)

| Group                   | Columns                                                                                                                          | Description                       |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| **A** — Rank            | `Final Rank`                                                                                                                     | Definitive production sequence    |
| **B–D** — ID            | `SKUCode`, `SKU Description`, `size`                                                                                             | SKU identity                      |
| **E–H** — Inputs        | `Source`, `HighestPriority`, `Target Date`, `Quantity`                                                                           | Manual inputs                     |
| **I–K** — Intermediates | `weighted_score`, `modified_priority_score`, `manual_rank`                                                                       | Scoring steps                     |
| **L** — Market          | `Market`                                                                                                                         | Market segment                    |
| **M–O** — Targets       | `Norm`, `Virtual Norm`, `Adjusted_Target`                                                                                        | Production norms                  |
| **P–W** — Demand        | `Stock`, `Vector_Requirement`, `CPT_Requirement`, `Requirement`, `Updated_Requirement`, `Penetration`...                         | Demand signals                    |
| **X–Z** — Attributes    | `TopSKUFlag`, `MarketWeight`, `priority`                                                                                         | SKU attributes                    |
| **AA–AB** — Inventory   | `PriorityScore_Inventory`, `NormInventoryScore`                                                                                  | Inventory signals                 |
| **AC–AD** — History     | `HistoryPenetrationScore`, `NormHistoryPenetrationScore`                                                                         | Black-day streak                  |
| **AE–AL** — Deployment  | `MachineCount`, `AvgMouldHealth`, `ProxyPenetration`, `ProxyRank`, `CriticalGap`, `ExcessProduction`, `MouldAlert`, `IsGhostSKU` | Stage 3-only                      |
| **AM–AQ** — Revenue     | `ASP`, `Cure Time`, `daily_cure`, `rev_pot`, `price_priority`                                                                    | Revenue efficiency                |
| **AR** — Stage 1 Raw    | `PriorityScore`                                                                                                                  | Raw Stage 1 demand score          |
| **AS** — Stage 1 Final  | `ConsolidatedPriorityScore`                                                                                                      | Stage 1 automated baseline        |
| **AT ✅** — Final       | `ConsolidationPriorityScore`                                                                                                     | **Canonical Stage 3 final score** |

**File:** `final_hybrid_deployment_report.xlsx`

---

## Key Formulas

### Stage 1 Formulas

#### `Adjusted_Target`

Strategic norm adjustment based on market type. Each market's multiplier is configurable via `config_input.xlsx`. Default is **100% of Virtual Norm** for all markets.

```
Adjusted_Target = Virtual Norm × RE_NORM_MULTIPLIER    (if Market == 'RE')   [default: 1.0]
Adjusted_Target = Virtual Norm × OE_NORM_MULTIPLIER    (if Market == 'OE')   [default: 1.0]
Adjusted_Target = Virtual Norm × ST_NORM_MULTIPLIER    (if Market == 'ST')   [default: 1.0]
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

Percentage of Virtual Norm that has been depleted from stock. **Always uses 100% of Virtual Norm** as the baseline — regardless of market type. Values > 100% indicate overstock.

```
Penetration = (Virtual Norm − Stock) / Virtual Norm × 100

             = 0    (if Virtual Norm == 0, to avoid division by zero)
```

---

#### `NormPenetration` / `NormRequirement`

Min-max normalisation across all SKUs in the same date batch.

```
NormPenetration  = (Penetration  − min(Penetration))  / (max(Penetration)  − min(Penetration))
NormRequirement  = (Requirement  − min(Requirement))  / (max(Requirement)  − min(Requirement))

# Both return 1.0 everywhere when max == min (avoids division by zero)
```

---

#### `PriorityScore_Inventory`

Weighted count of Red and Black stockout indicators across warehouse location types.

```
PriorityScore_Inventory = Σ  [BlackCount(loc) × LocationWeight(loc) × INVENTORY_BLACK_FACTOR
                              + RedCount(loc) × LocationWeight(loc) × INVENTORY_RED_FACTOR]
```

**Location Weights (default):**

| Location       | Weight |
| -------------- | ------ |
| JIT            | 5      |
| Depot          | 4      |
| Depot Mobility | 3      |
| Feeder         | 2      |
| PWH            | 1      |

> `INVENTORY_BLACK_FACTOR` (default `1.0`) and `INVENTORY_RED_FACTOR` (default `0.5`) are configurable via `config_input.xlsx`.

---

#### `PriorityScore` (Demand Score)

Composite demand urgency score using normalized sub-scores.

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
| OE10   | 4      | OE (10-inch) — same priority as OE    |
| ST     | 3      | Stock Transfer                        |
| EXP    | 2      | Export                                |
| OTR    | 2      | Other (configurable)                  |
| RE     | 1      | Replacement — lowest priority         |

**TopSKUFlag:** `1` if the SKU is flagged as a Top SKU in the BPR report, else `0`.

---

#### `NormInventoryScore`

Min-max normalises raw inventory score to [0, 1].

```
NormInventoryScore = (PriorityScore_Inventory − min(PriorityScore_Inventory))
                   / (max(PriorityScore_Inventory) − min(PriorityScore_Inventory))

# Returns 1.0 everywhere when max == min
```

---

#### `HistoryPenetrationScore`

Counts how many **consecutive days from today backward** a SKU was in **Black** status, reading past BOR files up to `HISTORY_PENETRATION_N` days.

- **Red today** → score = `0` (regardless of history)
- **Black today** → score = consecutive black days ending today (minimum 1, maximum N)

```
HistoryPenetrationScore = 0                        (if SKU is Red today)
HistoryPenetrationScore = consecutive black days   (if SKU is Black today, capped at N)

NormHistoryPenetrationScore = (HistoryPenetrationScore − min) / (max − min)
# Returns 1.0 everywhere when max == min
```

**Example (N = 10):**

| Status (10 days, newest→oldest) | Score |
| ------------------------------- | ----- |
| Black for all 10 days           | 10    |
| Black for 5 days, Red on day 6  | 5     |
| Black only today                | 1     |
| Red today                       | 0     |

---

#### `ConsolidatedPriorityScore` (Stage 1 Final Score)

Single unified score combining demand urgency, inventory criticality, revenue potential, and historical black-day streak. This is the **raw automated baseline** carried through to Stage 2 and 3.

```
ConsolidatedPriorityScore = (PriorityScore               × CONSOLIDATED_demand_priority)      [default: 0.35]
                           + (NormInventoryScore          × CONSOLIDATED_inventory_priority)   [default: 0.25]
                           + (price_priority              × CONSOLIDATED_price_priority)       [default: 0.25]
                           + (NormHistoryPenetrationScore × CONSOLIDATED_history_penetration)  [default: 0.15]
```

> Setting `CONSOLIDATED_history_penetration = 0` disables streak scoring entirely.  
> Setting `CONSOLIDATED_price_priority = 0` gives pure Demand + Inventory + History scoring.

---

#### `daily_cure` (Daily Machine Capacity per SKU)

```
daily_cure = ⌈ (1440 minutes / (Cure Time + 2.5)) × EFFICIENCY_FACTOR ⌉
```

> `+2.5` minutes accounts for the standard loading/unloading buffer.

---

#### `rev_pot` (Revenue Potential)

```
rev_pot = ASP × daily_cure
```

> `ASP` (Average Selling Price) is computed from `DISPATCH1.csv` as `Amt.in loc.cur. / Quantity`, grouped by **(Material, Market_Group)** for Plant 1300.
>
> - **OE/OE10 market** SKUs use the OE-channel ASP.
> - **All other markets** (RE, ST, OTR, EXP) share the RE-channel ASP.
> - Falls back to `DEFAULT_ASP` when no dispatch history exists for a (SKU, market group) pair.

---

#### `price_priority`

Min-max normalised revenue potential.

```
price_priority = (rev_pot − min(rev_pot)) / (max(rev_pot) − min(rev_pot))
# Returns 1.0 everywhere when max == min
```

---

#### `size`

```
size = characters at position [8:10] of SKUCode  (converted to integer)
```

---

### Stage 2 Formulas

#### `weighted_score`

Step 1 of the manual scoring pipeline (range: [0, 1]).

```
market_score   = MARKET_SCORE[Market]               (from config_stage2.py)
norm_market    = minmax(market_score)
norm_qty       = minmax(Quantity)
norm_date      = 1 − minmax(days_remaining_to_Target_Date)  ← inverted: closer = higher

weighted_score = W_MARKET × norm_market
              + W_QTY    × norm_qty
              + W_DATE   × norm_date
```

**Default weights (config_stage2.py):**

| Weight          | Default | Controls                         |
| --------------- | ------- | -------------------------------- |
| `W_MARKET`      | 0.30    | Market urgency contribution      |
| `W_QTY`         | 0.40    | Quantity urgency contribution    |
| `W_TARGET_DATE` | 0.30    | Target date urgency contribution |

---

#### `modified_priority_score`

Step 3: Boosts `HighestPriority = 1` rows above all HP=0 rows.

```
max_ws = max(weighted_score)   # across ALL manual rows

For HP=1 rows:
    modified_priority_score = max_ws × (1 + priority_rank / P)
    Range: (max_ws, 2 × max_ws]

For HP=0 rows:
    modified_priority_score = weighted_score   (unchanged)
```

---

#### `ConsolidationPriorityScore` (Stage 2 / 3 Final Score)

Step 4: Lifts all manual rows above all automated rows.

```
max_auto  = max(ConsolidatedPriorityScore)   # from Stage 1 automated output
overall_rank = rank by modified_priority_score ASCENDING  (1 = lowest, N = most urgent)

ConsolidationPriorityScore = max_auto × (1 + overall_rank / N)
Range: (max_auto, 2 × max_auto]  → all manual rows above all automated rows ✓
```

This is the **canonical final score** for both Stage 2 and Stage 3 output.

---

### Stage 3 (Deployment) Formulas

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

Adjusts priority downward for SKUs already in active production (more machines = lower urgency).

```
penalty_factor   = max(0,  1 − (MachineCount × MACHINE_COUNT_PENALTY))   [default penalty: 0.05]
ProxyPenetration = ConsolidatedPriorityScore × penalty_factor
```

**Example:** A SKU on 4 machines → factor = `1 − (4 × 0.05) = 0.80` → ProxyPenetration = 80% of original priority.

#### `ProxyRank`

Re-ranks all SKUs by `ProxyPenetration` descending. Lower rank = higher urgency after deployment adjustment.

---

#### Gap Flags

| Flag               | Formula                                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| `CriticalGap`      | `Rank_ConsolidatedPriorityScore ≤ CRITICAL_GAP_RANK` **AND** `MachineCount == 0`                        |
| `ExcessProduction` | `Rank_ConsolidatedPriorityScore > EXCESS_PRODUCTION_RANK` **AND** `MachineCount > EXCESS_MACHINE_COUNT` |
| `MouldAlert`       | `AvgMouldHealth > MOULD_LIFE_THRESHOLD`                                                                 |

**Defaults:** `CRITICAL_GAP_RANK = 50`, `EXCESS_PRODUCTION_RANK = 200`, `EXCESS_MACHINE_COUNT = 2`, `MOULD_LIFE_THRESHOLD = 0.9`

#### `Updated_Requirement` (Yield Factor)

Adjusts the production requirement to account for manufacturing yield loss.

```
For OE, OE10, EXP markets:
    Updated_Requirement = ⌈ Requirement / yield_factor + k ⌉

For RE, ST, OTR and other markets:
    Updated_Requirement = Requirement  (yield factor = 100%, no adjustment)
```

> `yield_factor` and `k` (extra units buffer) are configurable.

#### `Final Rank`

```
Final Rank = row index + 1   (after all sorting by ConsolidationPriorityScore DESC)
```

---

## Column Reference

### Group A — Primary Sequence

| Column                            | Stage | Description                                             |
| --------------------------------- | ----- | ------------------------------------------------------- |
| `Final Rank`                      | 3     | Definitive production sequence number (1 = most urgent) |
| `Rank_ConsolidationPriorityScore` | 2     | Stage 2 rank (1 = most urgent)                          |

### Group B — SKU Identification

| Column            | Description                                 |
| ----------------- | ------------------------------------------- |
| `SKUCode`         | Unique product identifier                   |
| `SKU Description` | Human-readable product name                 |
| `size`            | Rim size extracted from SKUCode (chars 8–9) |

### Group C — Source & Manual Inputs

| Column            | Description                                       |
| ----------------- | ------------------------------------------------- |
| `Source`          | `Manual` or `Automated`                           |
| `HighestPriority` | `1` = flagged as highest priority in manual input |
| `Target Date`     | When the CPT quantity is needed                   |
| `Quantity`        | CPT / manual production quantity                  |

### Group D — Manual Scoring Intermediates

| Column                    | Description                                                           |
| ------------------------- | --------------------------------------------------------------------- |
| `weighted_score`          | Step 1: Weighted input score (market + qty + date urgency, range 0–1) |
| `modified_priority_score` | Step 3: HP=1 boosted score (range: (max_ws, 2×max_ws])                |
| `manual_rank`             | Rank within manual block only (1 = most urgent manual SKU)            |

### Group E — Market & Targets

| Column            | Description                                                              |
| ----------------- | ------------------------------------------------------------------------ |
| `Market`          | `OE`, `OE10`, `ST`, `EXP`, `OTR`, or `RE`                                |
| `Norm `           | Original production norm                                                 |
| `Virtual Norm`    | Adjusted norm used as baseline                                           |
| `Adjusted_Target` | Virtual Norm × market multiplier (configurable; default 1.0 all markets) |

### Group F — Demand Signals

| Column                | Description                                                                                  |
| --------------------- | -------------------------------------------------------------------------------------------- |
| `Stock`               | Current on-hand stock                                                                        |
| `Vector_Requirement`  | Stage 1 automated requirement (before any override), keyed by (SKUCode, Market)              |
| `CPT_Requirement`     | Manual override quantity                                                                     |
| `Requirement`         | Final requirement used for calculations                                                      |
| `Updated_Requirement` | Yield-adjusted requirement for OE/EXP: `⌈Req / yield_factor + k⌉`; = `Requirement` otherwise |
| `Penetration`         | `(Virtual Norm − Stock) / Virtual Norm × 100` (always 100% of Virtual Norm)                  |
| `NormPenetration`     | Min-max of Penetration                                                                       |
| `NormRequirement`     | Min-max of Requirement                                                                       |

### Group G — SKU Attributes

| Column         | Description                                                                |
| -------------- | -------------------------------------------------------------------------- |
| `TopSKUFlag`   | Binary: `1` if Top SKU (from BPR), else `0`                                |
| `MarketWeight` | Numeric weight for market (OE/OE10=4, ST=3, EXP/OTR=2, RE=1)               |
| `priority`     | Sortable tuple: `(−MarketWeight, −Penetration, −Requirement, −TopSKUFlag)` |

### Group H — Inventory Signals

| Column                    | Description                                              |
| ------------------------- | -------------------------------------------------------- |
| `PriorityScore_Inventory` | Weighted sum of Red/Black stockouts across all locations |
| `NormInventoryScore`      | Min-max of `PriorityScore_Inventory`                     |

### Group I — History Penetration

| Column                        | Description                               |
| ----------------------------- | ----------------------------------------- |
| `HistoryPenetrationScore`     | Consecutive black days from today (0 – N) |
| `NormHistoryPenetrationScore` | Min-max of `HistoryPenetrationScore`      |

### Group J — Deployment Metrics & Flags (Stage 3 only)

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

### Group K — Revenue & Efficiency

| Column           | Description                                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `ASP`            | Avg Selling Price from dispatch, grouped by **(Material, Market_Group)** — OE or RE-channel |
| `Cure Time`      | Curing cycle time from static file (minutes)                                                |
| `daily_cure`     | `⌈(1440 / (Cure Time + 2.5)) × Efficiency_Factor⌉` — units per day per machine              |
| `rev_pot`        | `ASP × daily_cure` — daily revenue potential per machine (₹)                                |
| `price_priority` | Min-max of `rev_pot` — normalised revenue score                                             |

### Group L — Scoring Summary (always last columns)

| Column                       | Stage  | Description                                                                            |
| ---------------------------- | ------ | -------------------------------------------------------------------------------------- |
| `PriorityScore`              | 1+     | Demand-only score: weighted market + penetration + requirement + TopSKU                |
| `ConsolidatedPriorityScore`  | 1+     | Stage 1 unified score (automated baseline): demand + inventory + revenue + history     |
| `ConsolidationPriorityScore` | 2/3 ✅ | **Final canonical score** for Stage 2 & 3. All manual rows guaranteed > all automated. |

---

## Configuration

All Stage 1 parameters are stored in `config_input.xlsx`. Run `python create_config_excel.py` once to generate this file.  
Stage 2 / 3 manual scoring weights are stored in `config_stage2.py`.

### Stage 1 Config (`Stage1_Config` sheet in `config_input.xlsx`)

| Parameter                          | Default | Description                                                                         |
| ---------------------------------- | ------- | ----------------------------------------------------------------------------------- |
| `MARKET_WEIGHTS_OE`                | 4       | OE market weight                                                                    |
| `MARKET_WEIGHTS_ST`                | 3       | ST market weight                                                                    |
| `MARKET_WEIGHTS_EXP`               | 2       | EXP market weight                                                                   |
| `MARKET_WEIGHTS_RE`                | 1       | RE market weight                                                                    |
| `LOCATION_WEIGHTS_JIT`             | 5       | JIT warehouse weight                                                                |
| `LOCATION_WEIGHTS_Depot`           | 4       | Depot weight                                                                        |
| `LOCATION_WEIGHTS_Depot_Mobility`  | 3       | Depot Mobility weight                                                               |
| `LOCATION_WEIGHTS_Feeder`          | 2       | Feeder weight                                                                       |
| `LOCATION_WEIGHTS_PWH`             | 1       | PWH weight                                                                          |
| `RE_NORM_MULTIPLIER`               | 1.0     | Fraction of Virtual Norm used as Adjusted_Target for RE market (1.0 = 100%)         |
| `OE_NORM_MULTIPLIER`               | 1.0     | Fraction of Virtual Norm used as Adjusted_Target for OE market                      |
| `ST_NORM_MULTIPLIER`               | 1.0     | Fraction of Virtual Norm used as Adjusted_Target for ST market                      |
| `SCORING_market_weightage`         | 0.25    | Market % in PriorityScore                                                           |
| `SCORING_penetration_weightage`    | 0.35    | Penetration % in PriorityScore                                                      |
| `SCORING_requirement_weightage`    | 0.30    | Requirement % in PriorityScore                                                      |
| `SCORING_top_sku_weightage`        | 0.10    | Top SKU % in PriorityScore                                                          |
| `INVENTORY_BLACK_FACTOR`           | 1.0     | Score multiplier for Black stockout (critical)                                      |
| `INVENTORY_RED_FACTOR`             | 0.5     | Score multiplier for Red stockout (warning)                                         |
| `CONSOLIDATED_demand_priority`     | 0.35    | Demand % in ConsolidatedPriorityScore                                               |
| `CONSOLIDATED_inventory_priority`  | 0.25    | Inventory % in ConsolidatedPriorityScore                                            |
| `CONSOLIDATED_price_priority`      | 0.25    | Revenue % in ConsolidatedPriorityScore (set to 0 for Demand+Inventory+History only) |
| `CONSOLIDATED_history_penetration` | 0.15    | History streak % in ConsolidatedPriorityScore (set to 0 to disable)                 |
| `HISTORY_PENETRATION_N`            | 10      | Lookback window in days for consecutive black streak scoring                        |
| `EFFICIENCY_FACTOR`                | 0.90    | Machine efficiency for daily_cure                                                   |
| `DEFAULT_ASP`                      | 3000    | Fallback ASP when no dispatch history                                               |
| `DEFAULT_CURE_TIME`                | 15      | Fallback cure time (minutes)                                                        |

### Stage 2 / 3 Config (`config_stage2.py`)

| Parameter       | Default   | Description                                                   |
| --------------- | --------- | ------------------------------------------------------------- |
| `W_MARKET`      | 0.30      | Weight for market urgency in `weighted_score` (must sum to 1) |
| `W_QTY`         | 0.40      | Weight for quantity in `weighted_score`                       |
| `W_TARGET_DATE` | 0.30      | Weight for target date urgency in `weighted_score`            |
| `MARKET_SCORE`  | see below | Maps market codes → numeric urgency scores                    |

**`MARKET_SCORE` defaults:**

| Market | Score |
| ------ | ----- |
| OE     | 4     |
| OE10   | 4     |
| ST     | 3     |
| EXP    | 2     |
| OTR    | 2     |
| RE     | 1     |

### Stage 3 Deployment Config (`Stage2_Config` sheet in `config_input.xlsx`)

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

Output: `vector_frontend_running_demand_<DDMMYYYY>.xlsx`

### Run Stage 1 + 2 Only

```bash
python app_stage2.py
```

Output: `vector_frontend_demand_<DDMMYYYY>.xlsx`

### Run Stage 1 Only (date range)

```bash
python app.py
```

You will be prompted for:

- **Start date** (DD.MM.YYYY)
- **End date** (DD.MM.YYYY)

Output: `combined_vector_demand_<DDMMYYYY>.xlsx` (one sheet per date, filename uses end date)

---

## Troubleshooting

| Problem                                  | Cause                                 | Fix                                                                                |
| ---------------------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------- |
| `config_input.xlsx not found`            | Config file not generated             | Run `python create_config_excel.py`                                                |
| `Missing files` warning for a date       | Input CSVs/XLSXs absent for that date | Check file naming and the `data/` directory structure                              |
| All SKUs show `MachineCount = 0`         | Mould report file not found           | Verify `DDMMYYYY MouldDetails.csv` exists in `data/Vectordata/Daily Mould Report/` |
| Empty merge results                      | SKUCode type mismatch                 | All SKUCode columns are auto-cast to `str` — check source file encoding            |
| Manual entries not appearing at top      | `manual_frontend_demand.xlsx` missing | Create `data/manual_frontend_demand.xlsx` with required columns                    |
| Govt-market manual entry gets wrong Req  | Cross-market contamination (fixed)    | Lookup now uses **(SKUCode, Market)** composite key — no cross-market inheritance  |
| `W_MARKET + W_QTY + W_TARGET_DATE ≠ 1.0` | Config weights don't sum to 1         | Edit `config_stage2.py` — three weights must sum exactly to 1.0                    |

---

_Built for optimizing manufacturing operations through data-driven insights._
