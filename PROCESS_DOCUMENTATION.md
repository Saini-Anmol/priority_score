# Vector Supply Chain Intelligence System

## Process Documentation — BTP (All Stages) + CTP (Stage 1)

---

## Overview

This system automates production priority ranking. It has two independent pipelines:

| Pipeline | Plant | Tyre Types | Coverage       |
| -------- | ----- | ---------- | -------------- |
| **BTP**  | 1300  | PCR        | Stages 1, 2, 3 |
| **CTP**  | 1900  | PCR + TBR  | Stage 1 only   |

BTP runs across **three progressive stages**; CTP runs Stage 1 independently:

| Stage           | Name                       | Runner           | Output File                                    |
| --------------- | -------------------------- | ---------------- | ---------------------------------------------- |
| **BTP Stage 1** | Demand Scoring             | `app.py`         | `combined_vector_demand_DDMMYYYY.xlsx`         |
| **BTP Stage 2** | Machine Deployment         | `app_stage2.py`  | `vector_frontend_demand_DDMMYYYY.xlsx`         |
| **BTP Stage 3** | Manual Strategic Override  | `app_stage3.py`  | `vector_frontend_running_demand_DDMMYYYY.xlsx` |
| **CTP Stage 1** | Demand Scoring (PCR + TBR) | `CTP/ctp_app.py` | `CTP/CTP_combined_vector_demand_DDMMYYYY.xlsx` |

---

## BTP Stage 1: Demand Scoring

### Input Sources

All daily files from `./data/Vectordata/`:

| Report   | File Pattern                                       | Columns Used                                                                      |
| -------- | -------------------------------------------------- | --------------------------------------------------------------------------------- |
| **BOR**  | `BOR/BORColorBandwiseReport__DD-MM-YYYY.csv`       | Location Code, SKUCode, Virtual Norm, Stock, Norm                                 |
| **BMR**  | `BMR/Prod_OverAll_BMReport__DD_MM_YYYY.xlsx`       | Plant Code, Item Code → SKUCode, Pending CCR Qty → Requirement, BPP → Penetration |
| **BPR**  | `BPR/BufferPenetrationReport__DD-MM-YYYY.csv`      | SKUCode, Location Code, Location Type, On hand Inv. Color, Top SKU                |
| **SPOR** | `SPOR/Single_Production_Order_Report_DDMMYYYY.csv` | Existence check only (date gate) — no columns read                                |

> **Market mapping from BOR Location Code:**  
> `FG10 → RE` | `OE10 → OE` | `ST10 → ST` | `OTR10 → OTR` | BMR rows → `EXP`

> **Key:** One SKU appearing in multiple markets produces **separate rows per (SKUCode, Market)**. All scores are computed independently per row.

### Configuration (`config.py` loaded from `config_input.xlsx → Stage1_Config`)

| Parameter                   | Default                                                       | Description                                  |
| --------------------------- | ------------------------------------------------------------- | -------------------------------------------- |
| `MARKET_WEIGHTS`            | OE=4, ST=3, EXP=2, OTR=2, RE=1                                | Market importance                            |
| `LOCATION_WEIGHTS`          | JIT=5, Depot=4, DepotMobility=3, Feeder=2, PWH=1              | Warehouse urgency                            |
| `INVENTORY_SCORE_FACTORS`   | black=1.0, red=0.5                                            | Black/Red stockout multipliers               |
| `SCORING_PARAMS`            | market=0.25, penetration=0.35, requirement=0.30, top_sku=0.10 | PriorityScore weights                        |
| `CONSOLIDATED_WEIGHTS`      | demand=0.35, inventory=0.25, price=0.25, history=0.15         | Final score weights                          |
| `NORM_MULTIPLIERS`          | RE=1.0, OE=1.0, ST=1.0, OTR=1.0                               | Virtual Norm fraction for Adjusted_Target    |
| `HISTORY_PENETRATION_N`     | 10                                                            | Lookback window (days); max history score    |
| `HISTORY_PENETRATION_BLACK` | 100                                                           | Penetration % threshold for a "black" day    |
| `EFFICIENCY_FACTOR`         | 0.90                                                          | Machine efficiency for daily_cure calc       |
| `DEFAULT_ASP`               | 3000                                                          | Fallback ASP (₹) if SKU absent from dispatch |
| `DEFAULT_CURE_TIME`         | 15                                                            | Fallback cure time (min)                     |

### Scoring Formulas

#### A — Inventory Score (from BPR)

```
InventoryScore =
    Σ Black_Count_[Loc] × Location_Weight_[Loc] × 1.0   (Black factor)
  + Σ Red_Count_[Loc]   × Location_Weight_[Loc] × 0.5   (Red factor)
```

`[Loc]` = JIT, Depot, Depot Mobility, Feeder, PWH

#### B — Demand Signals (from BOR and BMR)

**BOR rows (RE / OE / ST / OTR):**

```
Adjusted_Target = Virtual Norm × NORM_MULTIPLIER[Market]
Requirement     = max(0, Adjusted_Target − Stock)
Penetration     = (Virtual Norm − Stock) / Virtual Norm × 100
```

**BMR rows (EXP only — no Virtual Norm):**

```
Requirement = Pending CCR Qty    (taken directly)
Penetration = BPP                (taken directly)
```

#### C — Price Score (from Dispatch + Cure Time)

```
ASP         = Amt.in loc.cur. / Quantity  grouped by (Material, Market_Group)
              where OE10 → 'OE' channel, all others → 'RE' channel
daily_cure  = ceil((1440 / (Cure Time + 2.5)) × EFFICIENCY_FACTOR)
rev_pot     = ASP × daily_cure
PriceScore  = min-max normalise(rev_pot)  →  [0, 1]
```

#### D — History Penetration Score (from historical BOR files)

Scored **independently per (SKUCode, Market)**. An RE row and OE row for the same SKU get separate streak counts.

```
For each (SKUCode, Market):
  If today's Penetration < HISTORY_PENETRATION_BLACK  →  score = 0
  Else: walk back day by day (oldest = today):
    • Missing BOR file (holiday) → continue (streak intact)
    • Penetration ≥ threshold   → streak += 1
    • Penetration < threshold   → break
  HistoryPenetrationScore = streak   (integer, range [0, N])
```

`NormHistoryPenetrationScore` = min-max normalise(HistoryPenetrationScore)

#### E — Priority Score (demand-only composite)

```
NormPenetration  = min-max normalise(Penetration)
NormRequirement  = min-max normalise(Requirement)

PriorityScore =
    MarketWeight     × 0.25
  + NormPenetration  × 0.35
  + NormRequirement  × 0.30
  + TopSKUFlag       × 0.10
```

#### F — Consolidated Priority Score (final Stage 1 score)

```
NormInventoryScore = min-max normalise(InventoryScore)

ConsolidatedPriorityScore =
    PriorityScore               × 0.35
  + NormInventoryScore          × 0.25
  + PriceScore                  × 0.25
  + NormHistoryPenetrationScore × 0.15
```

### Stage 1 Output Columns

| Group          | Columns                                                                        |
| -------------- | ------------------------------------------------------------------------------ |
| Identification | `SKUCode`, `SKU Description`, `size`                                           |
| Targets        | `Market`, `Norm`, `Virtual Norm`, `Adjusted_Target`                            |
| Demand Signals | `Stock`, `Requirement`, `Penetration`                                          |
| SKU Attributes | `TopSKUFlag`                                                                   |
| Inventory      | `InventoryScore`                                                               |
| Revenue        | `ASP`, `Cure Time`, `PriceScore`                                               |
| History        | `HistoryPenetrationScore`                                                      |
| Scoring        | `PriorityScore`, `ConsolidatedPriorityScore`, `Rank_ConsolidatedPriorityScore` |

> `NormPenetration`, `NormRequirement`, `NormInventoryScore`, `NormHistoryPenetrationScore`, `daily_cure`, `rev_pot`, `market_weight` are used internally but **excluded from output**.

---

## BTP Stage 2: Machine Deployment Analysis

### Input Sources

| Source             | File                                                      | Key Columns Used                                             |
| ------------------ | --------------------------------------------------------- | ------------------------------------------------------------ |
| Stage 1 output     | `combined_vector_demand_DDMMYYYY.xlsx`                    | All Stage 1 columns                                          |
| Daily Mould Report | `Vectordata/Daily Mould Report/DDMMYYYY MouldDetails.csv` | Sapcode (SKUCode), WCNAME (machine), Mould life, Target life |

### Configuration (`config_stage2.py`)

| Parameter                | Default | Description                                         |
| ------------------------ | ------- | --------------------------------------------------- |
| `MOULD_LIFE_THRESHOLD`   | 0.9     | MouldAlert if `AvgMouldHealth > 0.9`                |
| `MACHINE_COUNT_PENALTY`  | 0.05    | Priority reduction per machine already running (5%) |
| `CRITICAL_GAP_RANK`      | 50      | CriticalGap if Rank ≤ 50 and MachineCount = 0       |
| `EXCESS_PRODUCTION_RANK` | 200     | ExcessProduction if Rank > 200 and MachineCount ≥ 2 |

### Scoring Formulas

**Mould metrics (per SKU):**

```
MachineCount   = count(distinct machines running this SKU)
AvgMouldHealth = mean(Mould life / Target life) across all machines
```

**Ghost SKUs** (in Mould Report but absent from Stage 1 demand):

- `ConsolidatedPriorityScore = min(existing scores) × 0.5`
- `IsGhostSKU = True`
- Placed at the bottom of the ranked list

**Proxy Penetration (machine-adjusted priority):**

```
penalty_factor   = max(0, 1 − MachineCount × MACHINE_COUNT_PENALTY)
ProxyPenetration = ConsolidatedPriorityScore × penalty_factor
ProxyRank        = rank(ProxyPenetration, descending)
```

**Gap flags:**
| Flag | Condition |
|---|---|
| `CriticalGap` | `Rank ≤ CRITICAL_GAP_RANK AND MachineCount = 0` |
| `ExcessProduction` | `Rank > EXCESS_PRODUCTION_RANK AND MachineCount ≥ EXCESS_MACHINE_COUNT` |
| `MouldAlert` | `AvgMouldHealth > MOULD_LIFE_THRESHOLD` |

### Stage 2 Output File

`vector_frontend_demand_DDMMYYYY.xlsx`

Adds to Stage 1 columns: `MachineCount`, `AvgMouldHealth`, `ProxyPenetration`, `ProxyRank`, `CriticalGap`, `ExcessProduction`, `MouldAlert`, `IsGhostSKU`

---

## BTP Stage 3: Manual Strategic Override

### Input Sources

| Source         | File                                   | Key Columns                                               |
| -------------- | -------------------------------------- | --------------------------------------------------------- |
| Stage 2 output | `vector_frontend_demand_DDMMYYYY.xlsx` | All Stage 2 columns                                       |
| Manual demand  | `data/manual_frontend_demand.xlsx`     | SKU Code, Market, Quantity, Target Date, Highest Priority |

### 4-Step Manual Scoring Pipeline

```
Step 1 — weighted_score  (range [0, 1])
    norm_market   = min-max normalise(MARKET_SCORE[Market])
    norm_qty      = min-max normalise(Quantity)
    norm_date     = 1 − min-max normalise(days_remaining)   ← closer date = higher score
    weighted_score = W_MARKET×norm_market + W_QTY×norm_qty + W_TARGET_DATE×norm_date

Step 2 — modified_priority_score
    For HP=1 rows:  modified = max_ws × (1 + priority_rank / P)   ← always > HP=0
    For HP=0 rows:  modified = weighted_score

Step 3 — ConsolidationPriorityScore  (guarantees all manual > all automated)
    overall_rank = rank by modified_priority_score ascending
    ConsolidationPriorityScore = max_auto × (1 + overall_rank / N)
    where max_auto = max(ConsolidatedPriorityScore) from Stage 2

Step 4 — Final Rank
    Sort all rows (manual + automated) by ConsolidatedPriorityScore desc
    Order guaranteed: HP=1 manual → HP=0 manual → Automated
```

### Multi-Source Requirement Transparency

| Column               | Source                            | Purpose                                   |
| -------------------- | --------------------------------- | ----------------------------------------- |
| `Vector_Requirement` | Stage 1/2 calculated              | What automated analysis demanded          |
| `CPT_Requirement`    | Manual `Quantity` input           | What planner specified (takes precedence) |
| `Requirement`        | = CPT_Requirement for manual rows | Used downstream                           |

Lookup is keyed by **(SKUCode, Market)** — Govt-market manual entry does not inherit RE/OE quantities.

### Yield Adjustment (OE and EXP only)

```
Updated_Requirement = ceil(Requirement / yield_factor + k)
```

RE / ST / OTR: `Updated_Requirement = Requirement` (no adjustment)

### Stage 3 Output File

`vector_frontend_running_demand_DDMMYYYY.xlsx`  
Includes 7–10 historical BOR tabs for the last 10 calendar days.

**Key output columns (in order):**

| Column                                                 | Description                                    |
| ------------------------------------------------------ | ---------------------------------------------- |
| `Final Rank`                                           | Absolute production sequence (1 = most urgent) |
| `Source`                                               | "Manual" or "Automated"                        |
| `HighestPriority`                                      | 1 = HP override, 0 = normal                    |
| `weighted_score`                                       | Step 1 manual score                            |
| `modified_priority_score`                              | Step 2 HP-boosted score                        |
| `manual_rank`                                          | Rank within manual block                       |
| `Vector_Requirement`, `CPT_Requirement`, `Requirement` | Multi-source demand                            |
| `Updated_Requirement`                                  | Yield-adjusted final requirement               |
| `IsGhostSKU`                                           | True if running with no Vector demand          |
| `CriticalGap`, `ExcessProduction`, `MouldAlert`        | Gap flags from Stage 2                         |
| `PriorityScore`                                        | Stage 1 demand-only score                      |
| `ConsolidatedPriorityScore`                            | **Final Stage 3 score** (always last column)   |

---

## CTP Stage 1: Demand Scoring (Plant 1900)

### Differences from BTP Stage 1

| Aspect       | BTP                                    | CTP                                                                         |
| ------------ | -------------------------------------- | --------------------------------------------------------------------------- |
| Plant filter | `startswith('1300')`                   | `startswith('1900')`                                                        |
| Tyre types   | PCR only                               | PCR + TBR                                                                   |
| ASP source   | `DISPATCH1.csv` (filter Plant=1300)    | `CTP/CTP TYRE DESPATCH DEC 24 TO NOV 25.XLSX` (already Plant 1900)          |
| Cure time    | Single `data/curing_cycletime.csv`     | Merged: `CTP/PCR Curing cycle time.xlsx` + `CTP/TBR curing cycle time.xlsx` |
| SKU split    | None (all PCR)                         | `CTP/SKU_List.xlsx` → PCR SKUs; all others = TBR                            |
| Config       | `config.py` (Excel-driven)             | `CTP/ctp_config.py` (hardcoded)                                             |
| SPOR check   | Required as date gate                  | Not required                                                                |
| Output       | Single DataFrame                       | `(pcr_df, tbr_df)` tuple → 2 sheets                                         |
| Output file  | `combined_vector_demand_DDMMYYYY.xlsx` | `CTP/CTP_combined_vector_demand_DDMMYYYY.xlsx`                              |
| Runner       | `app.py`                               | `CTP/ctp_app.py`                                                            |

**Scoring logic is identical** — same formulas, weights, and min-max normalization as BTP Stage 1. HistoryPenetrationScore is also scored independently per (SKUCode, Market).

### CTP Stage 1 Output

Two sheets per output file:

- `PCR_DDMMYYYY` — PCR SKUs ranked by ConsolidatedPriorityScore
- `TBR_DDMMYYYY` — TBR SKUs ranked by ConsolidatedPriorityScore

Column structure identical to BTP Stage 1.

---

## Data Flow Diagram

```
./data/Vectordata/                         CTP/
  BOR, BMR, BPR, SPOR                   BOR, BMR, BPR (same files, Plant 1900)
  (Plant 1300)                           + PCR/TBR Cure Times + SKU_List.xlsx
       │                                        │
       ▼                                        ▼
  [BTP Stage 1]                          [CTP Stage 1]
  demand_processor.py                    ctp_demand_processor.py
  app.py                                 CTP/ctp_app.py
       │                                        │
       ▼                                        ▼
combined_vector_demand_DDMMYYYY.xlsx    CTP_combined_vector_demand_DDMMYYYY.xlsx
       │                               (PCR sheet + TBR sheet)
       ▼
  data/Vectordata/Daily Mould Report/
       │
       ▼
  [BTP Stage 2]
  deployment_processor.py + frontend_processor.py
  app_stage2.py
       │
       ▼
vector_frontend_demand_DDMMYYYY.xlsx
       │
       ▼
  data/manual_frontend_demand.xlsx
       │
       ▼
  [BTP Stage 3]
  manual_integration_processor.py
  app_stage3.py
       │
       ▼
vector_frontend_running_demand_DDMMYYYY.xlsx
  + History BOR tabs (last 10 days)
```

---

## Key Column Glossary

| Column                       | Definition                                                                               |
| ---------------------------- | ---------------------------------------------------------------------------------------- |
| `SKUCode`                    | SAP material code                                                                        |
| `Market`                     | OE / RE / EXP / ST / OTR                                                                 |
| `Virtual Norm`               | Buffer norm target stock level                                                           |
| `Adjusted_Target`            | `Virtual Norm × NORM_MULTIPLIER[Market]`                                                 |
| `Requirement`                | `max(0, Adjusted_Target − Stock)` (BOR); `Pending CCR Qty` (BMR/EXP)                     |
| `Penetration`                | `(Virtual Norm − Stock) / VN × 100` (BOR); `BPP` (BMR/EXP)                               |
| `InventoryScore`             | Weighted Black/Red stockout count across warehouse types                                 |
| `PriceScore`                 | Min-max normalised daily revenue potential                                               |
| `HistoryPenetrationScore`    | Consecutive "black" day streak per (SKUCode, Market), range [0, N]                       |
| `PriorityScore`              | Demand-only composite (market + penetration + requirement + top SKU)                     |
| `ConsolidatedPriorityScore`  | Final combined score (demand + inventory + price + history)                              |
| `MachineCount`               | Distinct machines currently producing this SKU                                           |
| `ProxyPenetration`           | Machine-penalised priority score                                                         |
| `CriticalGap`                | High-rank SKU with no machines assigned                                                  |
| `IsGhostSKU`                 | Running in machine but absent from Vector demand                                         |
| `ConsolidationPriorityScore` | Stage 3 internal manual scoring variable (maps to `ConsolidatedPriorityScore` in output) |
| `Vector_Requirement`         | Automated Stage 1/2 calculated requirement                                               |
| `CPT_Requirement`            | Planner-entered quantity (overrides Vector)                                              |
| `Updated_Requirement`        | Yield-adjusted final requirement (OE/EXP only)                                           |
| `Final Rank`                 | Absolute production sequence rank across all Stage 3 rows                                |
